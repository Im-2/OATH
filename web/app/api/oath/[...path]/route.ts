/**
 * Read-only caching proxy in front of the OATH API (which runs on a laptop behind a Cloudflare quick
 * tunnel). Visitors read from here; Vercel's CDN keeps each answer for a few seconds and refreshes it in
 * the background, so the tunnel sees a handful of requests however many people are watching.
 * Only GETs of known public endpoints are forwarded. The sandbox POST goes to the API directly
 * (so its per-visitor rate limit sees the visitor's IP).
 */
import type { NextRequest } from "next/server";

export const maxDuration = 30;

const ORIGIN = (process.env.OATH_API_URL || process.env.NEXT_PUBLIC_OATH_API_URL || "").replace(/\/+$/, "");

// path -> seconds the CDN may serve it before refreshing in the background
const ROUTES: [RegExp, number][] = [
  [/^v1\/live$/, 8],
  [/^v1\/(health|stats|feed|decisions|positions)$/, 8],
  [/^v1\/positions\/\d{1,9}$/, 8],
  [/^v1\/theses\/\d{1,9}$/, 30],
  [/^v1\/(verify|agent)$/, 30],
];
const QUERY = new Set(["limit", "offset", "status"]);

export async function GET(req: NextRequest, ctx: RouteContext<"/api/oath/[...path]">) {
  const { path } = await ctx.params;
  const p = path.join("/");
  const rule = ROUTES.find(([re]) => re.test(p));
  if (!rule) return Response.json({ error: "not found" }, { status: 404 });
  if (!ORIGIN) return Response.json({ error: "api not configured" }, { status: 503, headers: { "Cache-Control": "no-store" } });

  const q = new URLSearchParams();
  req.nextUrl.searchParams.forEach((v, k) => {
    if (QUERY.has(k) && /^[a-z0-9_]{1,20}$/i.test(v)) q.set(k, v);
  });
  const url = `${ORIGIN}/${p}${q.size ? `?${q}` : ""}`;
  const t0 = Date.now();
  try {
    const r = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(25_000), headers: { Accept: "application/json" } });
    const body = await r.text();
    const ok = r.ok;
    return new Response(body, {
      status: r.status,
      headers: {
        "Content-Type": "application/json",
        // CDN: serve for `rule[1]`s, then keep serving the last answer while one refresh runs in the background
        "Cache-Control": ok ? `public, s-maxage=${rule[1]}, stale-while-revalidate=300` : "no-store",
        "X-Oath-Upstream-Ms": String(Date.now() - t0),
      },
    });
  } catch {
    return Response.json({ error: "api unreachable" }, { status: 502, headers: { "Cache-Control": "no-store" } });
  }
}
