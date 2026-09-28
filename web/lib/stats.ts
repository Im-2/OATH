import snapshot from "@/data/stats-snapshot.json";

/** The three hero numbers. Always real: live from the OATH API, else the chain snapshot. */
export type HeroStats = {
  revealed: number;
  completeness: string | null; // "1" = 100%
  volumeUsd: string;
  source: "live" | "snapshot";
  asOf: string;
};

export const SNAPSHOT: HeroStats = {
  revealed: snapshot.revealed,
  completeness: snapshot.completeness,
  volumeUsd: snapshot.volume_usd,
  source: "snapshot",
  asOf: snapshot.as_of,
};

export const API_BASE = (process.env.NEXT_PUBLIC_OATH_API_URL || "").replace(/\/+$/, "");

export async function fetchLiveStats(timeoutMs = 4000): Promise<HeroStats | null> {
  if (!API_BASE) return null;
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(`${API_BASE}/v1/stats`, { signal: ctl.signal, cache: "no-store" });
    if (!r.ok) return null;
    const s = await r.json();
    if (typeof s.revealed !== "number" || typeof s.volume_usd !== "string") return null;
    return { revealed: s.revealed, completeness: s.completeness ?? null, volumeUsd: s.volume_usd,
             source: "live", asOf: s.indexed_at };
  } catch {
    return null;
  } finally {
    clearTimeout(t);
  }
}

export function fmtCompleteness(c: string | null) {
  if (c === null || c === undefined) return "—";
  const pct = Number(c) * 100;
  return `${Number.isInteger(pct) ? pct : pct.toFixed(1)}%`;
}

export function fmtUsd(v: string) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n >= 1000
    ? `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
    : `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
