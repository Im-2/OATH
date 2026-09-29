/**
 * Verify OATH's whole record in the browser from Solana alone (no OATH API).
 * Mirrors oath_core/verify.py: read every tx signed by the notary, parse its oath1: memos,
 * recompute every sha256, check seq contiguity, slot ordering, swap signers and sizes.
 */
import { canonicalJson, isCanonical, oathDigest, type Thesis } from "./canonical";

/**
 * Public RPCs to read from, in order. api.mainnet-beta.solana.com answers 403 "Access forbidden" to any
 * request carrying a browser Origin (checked 2026-09-29), so a CORS-friendly public RPC goes first.
 * NEXT_PUBLIC_SOLANA_RPC, when set, is tried before both.
 */
export const RPC_URLS = [
  ...(process.env.NEXT_PUBLIC_SOLANA_RPC ? [process.env.NEXT_PUBLIC_SOLANA_RPC.replace(/\/+$/, "")] : []),
  "https://solana-rpc.publicnode.com",
  "https://solana.api.pocket.network",
  "https://api.mainnet-beta.solana.com",
];
// Free browser-friendly RPCs keep only ~2 days of history (minimumLedgerSlot). Oaths older than every
// source's horizon are reported as out of reach, never as missing; a full-history RPC sees them all.
export const RPC_URL = RPC_URLS[0];
const MEMO_PROGRAMS = new Set(["MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"]);
const SOL_MINT = "So11111111111111111111111111111111111111112";
const MAX_HORIZON_MIN = 360;
const REVEAL_GRACE_MIN = 30;
const SIZE_TOLERANCE = 0.01;

export type LogLine = { tone: "ok" | "bad" | "info" | "dim"; text: string };
export type SeqResult = { seq: number; status: string; ok: boolean; problems: string[] };
export type ChainReport = {
  notary: string;
  txs: number;
  memos: number;
  seqs: SeqResult[];
  verified: number;
  total: number;
  pass: boolean;
  issues: string[];
  /** seqs older than every RPC's history horizon: not checkable from this browser with these RPCs */
  outOfReach: number[];
  horizonSlot: number | null;
  sources: string[];
};

/* ---------- RPC with backoff ---------- */

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

class Refused extends Error {}

export class RpcClient {
  calls = 0;
  private i = 0;
  constructor(private urls: string[], private onWait: (msg: string) => void, private signal?: AbortSignal) {}

  get url() {
    return this.urls[this.i];
  }

  /** Same call, moving to the next RPC in the list when one refuses browsers (401/403). */
  async call<T>(method: string, params: unknown[]): Promise<T> {
    for (;;) {
      try {
        return await this.callOne<T>(method, params);
      } catch (e) {
        if (!(e instanceof Refused) || this.i >= this.urls.length - 1) throw e;
        this.onWait(`${new URL(this.url).host} refused the browser (${e.message}), switching to ${new URL(this.urls[this.i + 1]).host}`);
        this.i++;
      }
    }
  }

  private async callOne<T>(method: string, params: unknown[]): Promise<T> {
    let delay = 800;
    for (let attempt = 0; attempt < 7; attempt++) {
      if (this.signal?.aborted) throw new Error("cancelled");
      this.calls++;
      let status = 0;
      try {
        const r = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ jsonrpc: "2.0", id: this.calls, method, params }),
          signal: this.signal,
        });
        status = r.status;
        if (r.ok) {
          const j = await r.json();
          if (j.error) {
            // -32429 / 429-style JSON-RPC errors are rate limits too
            if (String(j.error.code).includes("429") || /rate|too many/i.test(j.error.message ?? "")) status = 429;
            else if (j.error.code === 403 || j.error.code === 401 || /forbidden|unauthori[sz]ed|api key/i.test(j.error.message ?? "")) throw new Refused(String(j.error.message ?? j.error.code));
            else throw new Error(`${method}: ${j.error.message ?? JSON.stringify(j.error)}`);
          } else {
            return j.result as T;
          }
        }
      } catch (e) {
        if (this.signal?.aborted) throw new Error("cancelled");
        if (e instanceof Refused || (e instanceof Error && e.message.startsWith(method))) throw e;
        status = status || -1; // network error: retry
      }
      if (status === 401 || status === 403) throw new Refused(`HTTP ${status}`);
      if (status !== 429 && status !== -1 && status < 500) throw new Error(`${method}: HTTP ${status}`);
      this.onWait(`${status === 429 ? "rate limited by the public RPC" : "RPC unavailable"}, retrying in ${(delay / 1000).toFixed(1)}s…`);
      await sleep(delay);
      delay = Math.min(delay * 2, 12_000);
    }
    throw new Error(`${method}: gave up after retries`);
  }
}

/* ---------- memo parsing (oath_core/memo.py, strict) ---------- */

const HEX64 = /^[0-9a-f]{64}$/;
const CODE = /^[a-z0-9_]{1,32}$/;
const UINT = /^(0|[1-9][0-9]*)$/;
const B58 = /^[1-9A-HJ-NP-Za-km-z]+$/;
const isPubkey = (s: string) => B58.test(s) && s.length >= 32 && s.length <= 44;
const isSig = (s: string) => B58.test(s) && s.length >= 64 && s.length <= 88;
const EXIT_REASONS = new Set(["tp", "stop", "expiry", "manual", "exec_failed"]);

export type Memo =
  | { kind: "c"; agent: string; seq: number; digest: string; bond: number }
  | { kind: "b"; agent: string; seq: number; digest: string; reason: string }
  | { kind: "o"; agent: string; seq: number; swapSig: string }
  | { kind: "r"; agent: string; seq: number; salt: string; exitSig: string; exitReason: string }
  | { kind: "s"; agent: string; seq: number; reason: string }
  | { kind: "t"; seq: number; thesis: string }
  | { kind: "h"; agent: string; txSig: string; reason: string };

function seqOf(s: string): number | null {
  return UINT.test(s) && Number(s) >= 1 ? Number(s) : null;
}

export function parseMemo(s: string): Memo | null {
  if (!s.startsWith("oath1:")) return null;
  const head = s.split(":");
  const kind = head[1];
  if (kind === "t") {
    const i = s.indexOf(":", 8);
    const seq = seqOf(s.slice(8, i));
    return i > 0 && seq ? { kind: "t", seq, thesis: s.slice(i + 1) } : null;
  }
  const p = head;
  const agent = p[2];
  if (!agent || !isPubkey(agent)) return null;
  if (kind === "h") return p.length === 5 && isSig(p[3]) && CODE.test(p[4]) ? { kind: "h", agent, txSig: p[3], reason: p[4] } : null;
  const arity: Record<string, number> = { c: 6, b: 6, o: 5, r: 7, s: 5 };
  if (!(kind in arity) || p.length !== arity[kind]) return null;
  const seq = seqOf(p[3]);
  if (!seq) return null;
  if (kind === "c") return HEX64.test(p[4]) && UINT.test(p[5]) ? { kind, agent, seq, digest: p[4], bond: Number(p[5]) } : null;
  if (kind === "b") return HEX64.test(p[4]) && CODE.test(p[5]) ? { kind, agent, seq, digest: p[4], reason: p[5] } : null;
  if (kind === "o") return isSig(p[4]) ? { kind, agent, seq, swapSig: p[4] } : null;
  if (kind === "r") {
    const [salt, exitSig, reason] = [p[4], p[5], p[6]];
    const sigOk = isSig(exitSig) || (exitSig === "none" && reason === "exec_failed");
    return HEX64.test(salt) && EXIT_REASONS.has(reason) && sigOk ? { kind, agent, seq, salt, exitSig, exitReason: reason } : null;
  }
  return CODE.test(p[4]) ? { kind: "s", agent, seq, reason: p[4] } : null;
}

/* ---------- tx helpers ---------- */

type ParsedTx = {
  slot: number;
  blockTime: number | null;
  meta: {
    err: unknown; fee: number; preBalances: number[]; postBalances: number[];
    preTokenBalances?: TokBal[]; postTokenBalances?: TokBal[];
  };
  transaction: {
    signatures: string[];
    message: { accountKeys: { pubkey: string; signer: boolean }[]; instructions: { programId: string; parsed?: unknown }[] };
  };
};
type TokBal = { owner?: string; mint: string; uiTokenAmount: { amount: string } };

const signersOf = (tx: ParsedTx) => tx.transaction.message.accountKeys.filter((k) => k.signer).map((k) => k.pubkey);

function tokenDelta(tx: ParsedTx, owner: string, mint: string) {
  const tot = (xs?: TokBal[]) => (xs ?? []).filter((b) => b.owner === owner && b.mint === mint)
    .reduce((a, b) => a + BigInt(b.uiTokenAmount.amount), BigInt(0));
  return tot(tx.meta.postTokenBalances) - tot(tx.meta.preTokenBalances);
}

/** Raw delta of `mint` for `owner` (SOL: native lamports gross of fee + wSOL), as fills.py. */
function assetDelta(tx: ParsedTx, owner: string, mint: string): bigint {
  if (mint !== SOL_MINT) return tokenDelta(tx, owner, mint);
  const keys = tx.transaction.message.accountKeys.map((k) => k.pubkey);
  const i = keys.indexOf(owner);
  if (i < 0) return BigInt(0);
  const paid = keys[0] === owner ? BigInt(tx.meta.fee) : BigInt(0);
  return BigInt(tx.meta.postBalances[i]) - BigInt(tx.meta.preBalances[i]) + paid + tokenDelta(tx, owner, SOL_MINT);
}

/* ---------- the run ---------- */

type Rec<M> = M & { sig: string; slot: number; time: number | null };
type SeqMemos = { c?: Rec<Extract<Memo, { kind: "c" }>>; b?: Rec<Extract<Memo, { kind: "b" }>>; o?: Rec<Extract<Memo, { kind: "o" }>>; r?: Rec<Extract<Memo, { kind: "r" }> & { thesis?: string }>; s?: Rec<Extract<Memo, { kind: "s" }>>; dup: boolean };

const hostOf = (u: string) => {
  try {
    return new URL(u).host;
  } catch {
    return u;
  }
};

export async function verifyFromChain(
  notary: string,
  log: (l: LogLine) => void,
  progress: (done: number, total: number) => void,
  signal?: AbortSignal,
  urls: string[] = RPC_URLS,
): Promise<ChainReport> {
  const wait = (m: string) => log({ tone: "dim", text: `  … ${m}` });
  const clients = urls.map((u) => new RpcClient([u], wait, signal));
  log({ tone: "info", text: `$ oath verify --notary ${notary}` });
  log({ tone: "dim", text: `  rpcs: ${urls.map(hostOf).join(", ")} (public Solana RPCs; the OATH API is not used)` });

  // 1. every signature for the notary, merged across every RPC that answers (each keeps its own history)
  type SigInfo = { signature: string; err: unknown; slot: number };
  const bySig = new Map<string, SigInfo>();
  const sources: RpcClient[] = [];
  let horizonSlot: number | null = null;
  for (const c of clients) {
    try {
      let before: string | undefined;
      let n = 0;
      for (;;) {
        const page = await c.call<SigInfo[]>("getSignaturesForAddress", [notary, { limit: 1000, ...(before ? { before } : {}) }]);
        page.forEach((x) => bySig.set(x.signature, x));
        n += page.length;
        if (page.length < 1000) break;
        before = page[page.length - 1].signature;
      }
      sources.push(c);
      let min: number | null = null;
      try {
        min = await c.call<number>("minimumLedgerSlot", []);
      } catch {
        min = null;
      }
      // the oldest slot ANY source still keeps = how far back this run can reach
      horizonSlot = horizonSlot === null ? min ?? 0 : Math.min(horizonSlot, min ?? 0);
      log({ tone: "dim", text: `  ${hostOf(c.url)}: ${n} notary txs${min ? `, history from slot ${min.toLocaleString("en-US")}` : ""}` });
    } catch (e) {
      log({ tone: "dim", text: `  ${hostOf(c.url)}: unavailable (${e instanceof Error ? e.message : String(e)})` });
    }
  }
  if (!sources.length) throw new Error("no RPC answered");
  const ok = [...bySig.values()].filter((x) => !x.err).sort((a, b) => a.slot - b.slot);
  log({ tone: "info", text: `  found ${bySig.size} notary transactions (${ok.length} successful)` });

  // 2. fetch + parse memos (oldest first)
  const bySeq = new Map<string, Map<number, SeqMemos>>(); // agent -> seq -> memos
  const disclosures: { agent: string; txSig: string; reason: string }[] = [];
  let memoTxs = 0;
  let memoCount = 0;
  // a tx one RPC has pruned may still be on another: try each source in turn
  const getTx = async (sig: string) => {
    for (const c of sources) {
      try {
        const tx = await c.call<ParsedTx | null>("getTransaction", [sig, { encoding: "jsonParsed", maxSupportedTransactionVersion: 0, commitment: "confirmed" }]);
        if (tx) return tx;
      } catch {
        /* next source */
      }
    }
    return null;
  };
  const txCache = new Map<string, ParsedTx | null>();
  const fetchTx = async (sig: string) => {
    if (!txCache.has(sig)) txCache.set(sig, await getTx(sig));
    return txCache.get(sig) ?? null;
  };

  for (let i = 0; i < ok.length; i++) {
    progress(i, ok.length);
    const sig = ok[i].signature;
    const tx = await fetchTx(sig);
    if (!tx || tx.meta.err !== null || !signersOf(tx).includes(notary)) continue;
    const texts = tx.transaction.message.instructions
      .filter((ix) => MEMO_PROGRAMS.has(ix.programId) && typeof ix.parsed === "string")
      .map((ix) => ix.parsed as string);
    const memos = texts.map(parseMemo).filter((m): m is Memo => m !== null);
    if (!memos.length) continue;
    memoTxs++;
    memoCount += memos.length;
    const theses = new Map(memos.filter((m) => m.kind === "t").map((m) => [m.seq, (m as Extract<Memo, { kind: "t" }>).thesis]));
    for (const m of memos) {
      if (m.kind === "t") continue;
      if (m.kind === "h") {
        disclosures.push({ agent: m.agent, txSig: m.txSig, reason: m.reason });
        log({ tone: "dim", text: `  slot ${tx.slot}  h  operator disclosure: ${m.reason} (not a trade)` });
        continue;
      }
      const agentMap = bySeq.get(m.agent) ?? new Map<number, SeqMemos>();
      bySeq.set(m.agent, agentMap);
      const e = agentMap.get(m.seq) ?? { dup: false };
      agentMap.set(m.seq, e);
      const rec = { ...m, sig, slot: tx.slot, time: tx.blockTime };
      if (m.kind === "c" || m.kind === "b") {
        if (e.c || e.b) e.dup = true;
        else if (m.kind === "c") e.c = rec as SeqMemos["c"];
        else e.b = rec as SeqMemos["b"];
      } else if (m.kind === "o") e.o ??= rec as SeqMemos["o"];
      else if (m.kind === "r") e.r ??= { ...(rec as SeqMemos["r"])!, thesis: theses.get(m.seq) };
      else if (m.kind === "s") e.s ??= rec as SeqMemos["s"];
      log({ tone: "dim", text: `  slot ${tx.slot}  ${m.kind}  seq ${m.seq}` });
    }
  }
  progress(ok.length, ok.length);
  log({ tone: "info", text: `  ${memoTxs} transactions carry ${memoCount} oath1 memos` });

  // 3. per-seq checks
  const issues: string[] = [];
  const seqs: SeqResult[] = [];
  const outOfReach: number[] = [];
  const now = Date.now() / 1000;
  for (const [agent, map] of bySeq) {
    log({ tone: "info", text: `\n  agent ${agent.slice(0, 4)}…${agent.slice(-4)}` });
    const numbered = [...map.entries()].filter(([, e]) => e.c || e.b).map(([s]) => s).sort((a, b) => a - b);
    const max = numbered.length ? numbered[numbered.length - 1] : 0;
    const gaps = Array.from({ length: max }, (_, i) => i + 1).filter((s) => !numbered.includes(s));
    // Seqs below the first visible one, when every RPC's history starts after the oldest notary tx it
    // returned, are simply too old for these RPCs. A hole ABOVE the first visible seq is always a real gap.
    const first = numbered[0] ?? 1;
    const oldestSeen = ok.length ? ok[0].slot : 0;
    const truncated = horizonSlot !== null && horizonSlot > 0 && oldestSeen >= horizonSlot;
    const prefix = truncated ? gaps.filter((s) => s < first) : [];
    const realGaps = gaps.filter((s) => !prefix.includes(s));
    outOfReach.push(...prefix);
    if (prefix.length) {
      const which = prefix.length > 1 ? `${prefix[0]}…${prefix[prefix.length - 1]}` : String(prefix[0]);
      log({ tone: "dim", text: `  · seq ${which} is older than these RPCs keep (history from slot ${horizonSlot!.toLocaleString("en-US")}): not checked here` });
    }
    if (realGaps.length) {
      issues.push(`sequence gaps ${realGaps.join(", ")}`);
      log({ tone: "bad", text: `  ✗ sequence has gaps: missing ${realGaps.join(", ")}` });
    } else if (numbered.length) {
      log({ tone: "ok", text: `  ✓ sequence ${first}…${max} is contiguous, no gaps${prefix.length ? " (within reach)" : ""}` });
    }
    const orphans = [...map.keys()].filter((s) => !numbered.includes(s));
    const realOrphans = orphans.filter((s) => !prefix.includes(s)); // a prefix orphan's commit is beyond the horizon
    if (realOrphans.length) issues.push(`memos with no commitment: seq ${realOrphans.join(", ")}`);

    for (const seq of numbered) {
      const e = map.get(seq)!;
      const p: string[] = [];
      let status = "committed";
      const say = (tone: LogLine["tone"], t: string) => log({ tone, text: `  ${tone === "ok" ? "✓" : tone === "bad" ? "✗" : "·"} seq ${seq}  ${t}` });
      if (e.dup) p.push("duplicate commitment");
      if (e.b) {
        status = "blocked";
        say("ok", `blocked by the firewall before trading (${e.b.reason}), slot ${e.b.slot}`);
      } else if (e.c) {
        const c = e.c;
        let swap: ParsedTx | null = null;
        if (e.o) {
          swap = await fetchTx(e.o.swapSig);
          if (!swap) p.push("entry swap tx not found");
          else {
            if (!(swap.slot > c.slot)) p.push(`swap slot ${swap.slot} is not after commit slot ${c.slot}`);
            else say("ok", `commit slot ${c.slot.toLocaleString("en-US")} < swap slot ${swap.slot.toLocaleString("en-US")}`);
            if (!signersOf(swap).includes(agent)) p.push("entry swap not signed by the agent wallet");
          }
          if (!(e.o.slot > c.slot)) p.push("open memo did not land after commit");
        }
        if (!e.r) {
          const ref = swap?.blockTime ?? c.time ?? now;
          const deadline = ref + (MAX_HORIZON_MIN + REVEAL_GRACE_MIN) * 60;
          if (now > deadline) {
            status = "unrevealed";
            p.push("reveal deadline passed without reveal (counted as a loss)");
          } else {
            status = e.o ? "open" : "committed";
            say("info", `sealed: thesis stays secret until reveal (deadline ${new Date(deadline * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC)`);
          }
        } else {
          const r = e.r;
          status = "revealed";
          if (!(r.slot > c.slot)) p.push("reveal did not land after commit");
          const raw = r.thesis ?? "";
          if (!raw) p.push("reveal carries no thesis memo");
          else if (!isCanonical(raw)) p.push("revealed thesis is not canonical JSON");
          else {
            const got = await oathDigest(raw, r.salt);
            if (got !== c.digest) p.push("sha256(thesis ‖ salt) ≠ committed digest");
            else say("ok", `sha256(thesis ‖ salt) = ${got.slice(0, 12)}…${got.slice(-6)} matches the commit`);
            const t = JSON.parse(raw) as Thesis;
            if (canonicalJson(t) !== raw) p.push("re-encoded thesis differs");
            if (t.seq !== String(seq) || t.agent !== agent) p.push("revealed thesis seq/agent does not match memo");
            if (swap) {
              const spent = -assetDelta(swap, agent, t.in_mint);
              const got2 = assetDelta(swap, agent, t.out_mint);
              const size = Number(t.size_usd) * 1e6;
              if (spent <= BigInt(0) || got2 <= BigInt(0)) p.push("entry swap does not move the thesis mints");
              else if (Math.abs(Number(spent) - size) > size * SIZE_TOLERANCE) p.push(`entry spent ${spent} raw vs committed size ${t.size_usd}`);
              else say("ok", `swap signed by the agent; spent ${(Number(spent) / 1e6).toFixed(6)} USDC = committed size ${t.size_usd}`);
            }
            if (r.exitReason !== "exec_failed" && r.exitSig !== "none") {
              const ex = await fetchTx(r.exitSig);
              if (!ex) p.push("exit swap tx not found");
              else {
                if (!signersOf(ex).includes(agent)) p.push("exit swap not signed by the agent wallet");
                if (swap && !(ex.slot > swap.slot)) p.push("exit did not land after entry");
                if (!(r.slot > ex.slot)) p.push("reveal did not land after the exit swap");
              }
            }
          }
        }
      }
      for (const x of p) say("bad", x);
      if (!p.length && status === "revealed") say("ok", "oath kept: committed → traded → revealed, all consistent");
      p.forEach((x) => issues.push(`seq ${seq}: ${x}`));
      seqs.push({ seq, status, ok: p.length === 0, problems: p });
    }
  }
  const verified = seqs.filter((s) => s.ok).length;
  const calls = clients.reduce((n, c) => n + c.calls, 0);
  log({ tone: "dim", text: `\n  ${calls} RPC calls · ${disclosures.length} operator disclosure(s) listed, not counted as trades` });
  const reach = outOfReach.length ? ` · ${outOfReach.length} older oath(s) beyond these RPCs' history` : "";
  log(issues.length
    ? { tone: "bad", text: `  FAIL: ${issues.length} problem(s)` }
    : { tone: "ok", text: `  PASS: independently verified ${verified}/${seqs.length} oaths${reach}` });
  return { notary, txs: ok.length, memos: memoCount, seqs, verified, total: seqs.length, pass: !issues.length && seqs.length > 0,
           issues, outOfReach, horizonSlot: outOfReach.length ? horizonSlot : null, sources: sources.map((c) => c.url) };
}
