"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import snap from "@/data/api-snapshot.json";
import { API_BASE } from "./stats";

/** Shapes of the OATH API responses (oath_server/app.py). Every value is real chain/ledger data. */
export type Fill = {
  summary: string;
  spent: string;
  received: string;
  fill_price: string;
  network_fee: string;
  tx: string;
  slot: number;
  block_time?: number | null;
};

export type Grade = {
  pnl_usd: string | null;
  gross_pnl_usd?: string | null;
  fees_usd?: string | null;
  r_multiple?: string | null;
  entry_px?: string | null;
  exit_px?: string | null;
  qty_match?: boolean | null;
  size_ok?: boolean | null;
  adherence?: { ok: boolean; checks: Record<string, boolean> } | null;
  volume_usd?: string | null;
};

export type Position = {
  seq: number;
  status: "committed" | "open" | "unrevealed" | "revealed" | "blocked" | "invalid" | string;
  digest?: string;
  digest_ok?: boolean;
  commit_sig?: string;
  commit_slot?: number;
  commit_time?: number;
  open_sig?: string;
  open_time?: number;
  swap_sig?: string;
  swap_slot?: number;
  swap_time?: number;
  exit_sig?: string;
  exit_slot?: number;
  exit_reason?: string;
  reveal_sig?: string;
  reveal_slot?: number;
  reveal_time?: number;
  reveal_deadline?: string;
  blocked_sig?: string;
  reason_code?: string;
  problems?: string[];
  thesis?: Record<string, string>;
  levels?: Record<string, string>;
  canonical?: string;
  salt_hex?: string;
  digest_matches_chain?: boolean;
  entry?: Fill;
  exit?: Fill;
  result?: Grade;
};

export type Signal = { name: string; reading: string; agrees: boolean };

export type FeedItem = {
  kind: "commit" | "blocked" | "open" | "reveal" | "slash" | "operator_disclosure" | "stand_aside" | string;
  seq?: number | null;
  sig?: string;
  slot?: number;
  block_time: number;
  digest?: string;
  swap_sig?: string;
  exit_sig?: string;
  exit_reason?: string;
  reason?: string;
  reason_code?: string;
  tx_sig?: string;
  id?: number;
  ts?: string;
  why?: string;
  evidence?: { signals?: Signal[]; agreeing?: number; needs?: number; against?: number; backfilled?: boolean } & Record<string, unknown>;
  source?: string;
};

export type Decision = {
  id: number;
  ts: string;
  kind: string;
  mkt: string;
  reason_code: string;
  why: string;
  evidence: FeedItem["evidence"];
  backfilled: boolean;
};

export type Stats = {
  committed: number;
  open: number;
  closed: number;
  revealed: number;
  unrevealed: number;
  completeness: string | null;
  realised_pnl_usd: string;
  volume_usd: string;
  blocked: number;
  adherence_violations: number;
  verify_pass: boolean;
  stand_asides: number;
  disclosed_operator_actions?: number;
  indexed_at: string;
};

export type Health = {
  ok: boolean;
  notary: string;
  indexed_at: string | null;
  index_age_s: number | null;
  last_error: string | null;
  monitor?: { online: boolean; last_tick_age_s: number | null };
};

export type LiveData = {
  health: Health;
  stats: Stats;
  feed: FeedItem[];
  positions: Position[];
  decisions: Decision[];
  source: "live" | "snapshot";
  /** when this data was produced: fetch time (live) or the snapshot's index time */
  asOf: string;
};

export const SNAPSHOT_DATA: LiveData = {
  health: snap.health as Health,
  stats: snap.stats as unknown as Stats,
  feed: snap.feed.items as FeedItem[],
  positions: snap.positions.items as unknown as Position[],
  decisions: snap.decisions.items as unknown as Decision[],
  source: "snapshot",
  asOf: snap.generated_at,
};

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { signal, cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json() as Promise<T>;
}

/** One consistent read of the live API, or null (unreachable / not configured). */
export async function fetchLive(timeoutMs = 6000): Promise<LiveData | null> {
  if (!API_BASE) return null;
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const [health, stats, feed, positions, decisions] = await Promise.all([
      getJson<Health>("/v1/health", ctl.signal),
      getJson<Stats>("/v1/stats", ctl.signal),
      getJson<{ items: FeedItem[] }>("/v1/feed?limit=200", ctl.signal),
      getJson<{ items: Position[] }>("/v1/positions?limit=200", ctl.signal),
      getJson<{ items: Decision[] }>("/v1/decisions?limit=50", ctl.signal),
    ]);
    if (!health.ok || typeof stats.committed !== "number") return null;
    return { health, stats, feed: feed.items, positions: positions.items, decisions: decisions.items,
             source: "live", asOf: new Date().toISOString() };
  } catch {
    return null;
  } finally {
    clearTimeout(t);
  }
}

export async function fetchPosition(seq: number, timeoutMs = 6000): Promise<Position | null | "missing"> {
  if (!API_BASE) return null;
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(`${API_BASE}/v1/positions/${seq}`, { signal: ctl.signal, cache: "no-store" });
    if (r.status === 404) return "missing";
    if (!r.ok) return null;
    return (await r.json()) as Position;
  } catch {
    return null;
  } finally {
    clearTimeout(t);
  }
}

/**
 * Poll every `intervalMs` while the tab is visible (paused when hidden, refreshed on return).
 * Starts from the snapshot; `ready` flips once the first live attempt settles.
 */
export function useLiveData(intervalMs = 10_000) {
  const [data, setData] = useState<LiveData>(SNAPSHOT_DATA);
  const [ready, setReady] = useState(false);
  const [lastAttempt, setLastAttempt] = useState<number | null>(null);
  const busy = useRef(false);

  const tick = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const live = await fetchLive();
      // Offline keeps the last good data we had (a previous live read beats the older snapshot).
      setData((prev) => live ?? (prev.source === "live" ? { ...prev, source: "snapshot" } : SNAPSHOT_DATA));
      setLastAttempt(Date.now());
      setReady(true);
    } finally {
      busy.current = false;
    }
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    const start = () => {
      if (timer) return;
      void tick();
      timer = setInterval(() => void tick(), intervalMs);
    };
    const stop = () => {
      if (timer) clearInterval(timer);
      timer = null;
    };
    const onVis = () => (document.visibilityState === "visible" ? start() : stop());
    // always read once on mount (even in a background tab), then poll only while visible
    if (document.visibilityState === "visible") start();
    else void tick();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [tick, intervalMs]);

  return { data, ready, lastAttempt };
}

/* ---------- formatting ---------- */

export const SOLSCAN_ACCOUNT = (a: string) => `https://solscan.io/account/${a}`;

export function fmtTime(sec: number | null | undefined, withDate = true) {
  if (typeof sec !== "number") return "—";
  const d = new Date(sec * 1000);
  const t = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC" });
  if (!withDate) return `${t} UTC`;
  const day = d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  return `${day}, ${t} UTC`;
}

export function fmtAgo(sec: number, now: number) {
  const s = Math.max(0, Math.round(now / 1000 - sec));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function fmtPnl(v: string | null | undefined) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  const s = abs < 0.01 && abs > 0 ? abs.toFixed(4) : abs.toFixed(2);
  return `${n < 0 ? "−" : n > 0 ? "+" : ""}$${s}`;
}

/** "0.008113454 SOL" -> "0.008113 SOL" (display only; the full value is in the title/tooltip). */
export function trimAmount(a: string | undefined, dp = 6) {
  if (!a) return "—";
  const [num, unit] = a.split(" ");
  const n = Number(num);
  if (!Number.isFinite(n)) return a;
  return `${n.toFixed(Math.min(dp, (num.split(".")[1] || "").length))} ${unit ?? ""}`.trim();
}

export const EXIT_LABEL: Record<string, string> = {
  stop: "stop hit",
  tp: "take-profit hit",
  expiry: "horizon expired",
  manual: "closed manually",
};

export const REASON_LABEL: Record<string, string> = {
  INSUFFICIENT_SIGNALS: "Insufficient signals",
};

export function humanCode(code: string | undefined) {
  if (!code) return "—";
  return REASON_LABEL[code] ?? code.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}
