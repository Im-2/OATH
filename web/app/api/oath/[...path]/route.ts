/**
 * Read-only caching proxy in front of the OATH API (which runs on a laptop behind a Cloudflare quick
 * tunnel). Visitors read from here; Vercel's CDN keeps each answer for a few seconds and refreshes it in
 * the background, so the tunnel sees a handful of requests however many people are watching.
 * Only GETs of known public endpoints are forwarded, plus the sandbox POST (never cached), which carries
 * the visitor's IP and a shared secret so the API can still rate-limit per visitor. The browser therefore
 * only ever talks to this site (on a laptop inside the tailnet, a direct call to the *.ts.net name would
 * resolve to a private 100.x address, which browsers block from public pages).
 */
import type { NextRequest } from "next/server";

export const maxDuration = 120; // the sandbox can take ~60 s on a cold start

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
    const r = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(25_000), headers: { Accept: "application/json", "ngrok-skip-browser-warning": "1" } });
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

export async function POST(req: NextRequest, ctx: RouteContext<"/api/oath/[...path]">) {
  const { path } = await ctx.params;
  if (path.join("/") !== "v1/sandbox") return Response.json({ error: "not found" }, { status: 404 });
  if (!ORIGIN) return Response.json({ error: "resting", message: "OATH is resting. Try Break it instead." }, { status: 503 });
  const body = await req.text();
  if (body.length > 4000) return Response.json({ error: "too long" }, { status: 413 });
  // Vercel sets x-forwarded-for to the real client; the first entry is the visitor
  const visitor = (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || req.headers.get("x-real-ip") || "";
  const headers: Record<string, string> = { "Content-Type": "application/json", "ngrok-skip-browser-warning": "1" };
  if (process.env.OATH_PROXY_SECRET && visitor) {
    headers["X-Oath-Proxy-Key"] = process.env.OATH_PROXY_SECRET;
    headers["X-Oath-Visitor-IP"] = visitor;
  }
  try {
    const r = await fetch(`${ORIGIN}/v1/sandbox`, { method: "POST", body, headers, cache: "no-store", signal: AbortSignal.timeout(115_000) });
    return new Response(await r.text(), {
      status: r.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...(r.headers.get("retry-after") ? { "Retry-After": r.headers.get("retry-after")! } : {}) },
    });
  } catch {
    return Response.json({ error: "resting", message: "OATH is resting. Try Break it instead." }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
