import type { FeedItem, Position } from "@/lib/api";

/** One row of the tape. "close" rows come from each position's exit fill (a real on-chain swap). */
export type TapeRow = {
  key: string;
  kind: FeedItem["kind"] | "close";
  seq: number | null;
  time: number;
  item: FeedItem | null;
  pos: Position | null;
};

export type Filter = "all" | "trades" | "blocked" | "stood_aside";

export const TRADE_KINDS = new Set(["commit", "open", "close", "reveal", "slash"]);

export function buildTape(feed: FeedItem[], positions: Position[]): TapeRow[] {
  const bySeq = new Map(positions.map((p) => [p.seq, p]));
  const rows: TapeRow[] = feed.map((it) => ({
    key: `${it.kind}:${it.sig ?? it.id ?? `${it.seq}:${it.block_time}`}`,
    kind: it.kind,
    seq: typeof it.seq === "number" ? it.seq : null,
    time: it.block_time,
    item: it,
    pos: typeof it.seq === "number" ? bySeq.get(it.seq) ?? null : null,
  }));
  for (const p of positions) {
    if (p.exit_sig && p.exit) {
      rows.push({
        key: `close:${p.exit_sig}`,
        kind: "close",
        seq: p.seq,
        time: p.exit.block_time ?? p.reveal_time ?? 0,
        item: null,
        pos: p,
      });
    }
  }
  // newest first; within one second keep the lifecycle order (reveal after close after open after commit)
  const order: Record<string, number> = { commit: 0, blocked: 0, open: 1, close: 2, reveal: 3, slash: 3 };
  return rows.sort((a, b) => b.time - a.time || (order[b.kind] ?? 0) - (order[a.kind] ?? 0));
}

export function matchFilter(r: TapeRow, f: Filter) {
  if (f === "all") return true;
  if (f === "trades") return TRADE_KINDS.has(r.kind);
  if (f === "blocked") return r.kind === "blocked";
  return r.kind === "stand_aside";
}

/** Open (sealed) oaths: committed on-chain, thesis not yet revealed. */
export function sealedPositions(positions: Position[]) {
  return positions
    .filter((p) => p.status === "committed" || p.status === "open" || p.status === "unrevealed")
    .sort((a, b) => b.seq - a.seq);
}
