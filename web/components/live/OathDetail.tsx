"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { EXIT_LABEL, SNAPSHOT_DATA, fetchPosition, fmtPnl, fmtTime, trimAmount, type Position } from "@/lib/api";
import { thesisDigest } from "@/lib/canonical";
import { slot } from "@/lib/featured";
import { useNow } from "@/lib/useNow";
import { CheckIcon, CopyHash, CrossIcon, LockIcon, Panel, Tag, TxLink, VerifiedCheck } from "./ui";

type Source = "live" | "snapshot";

function usePosition(seq: number) {
  const snap = SNAPSHOT_DATA.positions.find((p) => p.seq === seq) ?? null;
  const [pos, setPos] = useState<Position | null>(snap);
  const [source, setSource] = useState<Source>("snapshot");
  const [missing, setMissing] = useState(false);
  const [ready, setReady] = useState(false);

  const tick = useCallback(async () => {
    const r = await fetchPosition(seq);
    if (r === "missing") {
      setMissing(true);
      setPos(null);
      setSource("live");
    } else if (r) {
      setMissing(false);
      setPos(r);
      setSource("live");
    } else {
      setSource("snapshot");
    }
    setReady(true);
  }, [seq]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    let timer0: ReturnType<typeof setTimeout> | null = null;
    const start = () => {
      if (timer) return;
      void tick();
      timer = setInterval(() => void tick(), 10_000);
    };
    const stop = () => {
      if (timer) clearInterval(timer);
      timer = null;
    };
    const onVis = () => (document.visibilityState === "visible" ? start() : stop());
    // always read once on mount (even in a background tab), then poll only while visible
    if (document.visibilityState === "visible") start();
    else timer0 = setTimeout(() => void tick(), 0);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      if (timer0) clearTimeout(timer0);
      stop();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [tick]);

  return { pos, source, missing, ready };
}

/* ---------- timeline ---------- */

type Step = { key: string; label: string; done: boolean; slot?: number; time?: number | null; sig?: string; sigLabel: string; note?: React.ReactNode; tone: "amber" | "white" | "green" | "red" };

function steps(p: Position): Step[] {
  if (p.status === "blocked") {
    return [{ key: "blocked", label: "Blocked by the firewall", done: true, sig: p.blocked_sig, sigLabel: "block memo", tone: "red",
              note: <span className="font-mono text-[#FF5A4E]/85">{p.reason_code}</span> }];
  }
  return [
    { key: "c", label: "Committed", done: !!p.commit_sig, slot: p.commit_slot, time: p.commit_time, sig: p.commit_sig, sigLabel: "commit tx", tone: "amber",
      note: "Salted hash of the full plan, on-chain before any money moved." },
    { key: "o", label: "Opened", done: !!p.swap_sig, slot: p.swap_slot, time: p.entry?.block_time ?? p.swap_time, sig: p.swap_sig, sigLabel: "swap tx", tone: "white",
      note: p.entry ? <>{trimAmount(p.entry.spent, 2)} → {trimAmount(p.entry.received)} at {trimAmount(p.entry.fill_price, 2)}</> : undefined },
    { key: "x", label: "Closed", done: !!p.exit_sig, slot: p.exit_slot, time: p.exit?.block_time, sig: p.exit_sig, sigLabel: "exit tx", tone: "white",
      note: p.exit ? <>{EXIT_LABEL[p.exit_reason ?? ""] ?? p.exit_reason} · {trimAmount(p.exit.spent)} → {trimAmount(p.exit.received, 2)}</> : undefined },
    { key: "r", label: "Revealed", done: !!p.reveal_sig, slot: p.reveal_slot, time: p.reveal_time, sig: p.reveal_sig, sigLabel: "reveal tx",
      tone: p.digest_ok === false ? "red" : "green", note: p.reveal_sig ? "Thesis and salt published; anyone can re-hash them." : undefined },
  ];
}

function Timeline({ p }: { p: Position }) {
  const list = steps(p);
  const dot = { amber: "bg-[#F2C14E] shadow-[0_0_10px_rgba(242,193,78,0.6)]", white: "bg-white", green: "bg-[#A8D86E] shadow-[0_0_12px_rgba(61,255,110,0.7)]", red: "bg-[#FF5A4E]" };
  return (
    <ol className="relative">
      {list.map((s, i) => (
        <li key={s.key} className="relative flex gap-4 pb-6 last:pb-0">
          {i < list.length - 1 && (
            <span aria-hidden="true" className={`absolute left-[7px] top-5 bottom-0 w-px ${list[i + 1].done ? "bg-white/20" : "bg-white/[0.07]"}`} />
          )}
          <span className={`relative mt-[5px] h-[15px] w-[15px] shrink-0 rounded-full border-2 border-[#0B0B0C] ${s.done ? dot[s.tone] : "bg-white/10"}`} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <span className={`text-[15px] ${s.done ? "text-white" : "text-white/35"}`}>{s.label}</span>
              {s.done ? <TxLink sig={s.sig} label={s.sigLabel} /> : <span className="text-[12px] text-white/30">pending</span>}
            </div>
            {s.done && (s.slot || s.time) && (
              <div className="mt-0.5 font-mono text-[12px] text-white/45">
                {s.slot ? <span className="whitespace-nowrap">slot {slot(s.slot)}</span> : null}{s.slot && s.time ? " · " : ""}{s.time ? <span className="whitespace-nowrap">{fmtTime(s.time)}</span> : ""}
              </div>
            )}
            {s.done && s.note && <div className="mt-1 text-[13px] text-white/55">{s.note}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

/* ---------- revealed: thesis + grade + in-browser verify ---------- */

const THESIS_ORDER = ["mkt", "side", "size_usd", "entry", "stop", "tp", "horizon_min", "conf", "strat", "why", "ts", "seq", "agent", "in_mint", "out_mint", "v"];
const THESIS_LABEL: Record<string, string> = {
  mkt: "Market", side: "Side", size_usd: "Size", entry: "Entry", stop: "Stop", tp: "Take-profit", horizon_min: "Horizon",
  conf: "Confidence", strat: "Strategy", why: "Why", ts: "Written at", seq: "Seq", agent: "Agent", in_mint: "Pays with", out_mint: "Buys", v: "Format",
};

const MINT_SYM: Record<string, string> = {
  So11111111111111111111111111111111111111112: "SOL",
  EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v: "USDC",
};

function thesisValue(k: string, v: string, levels?: Record<string, string>): React.ReactNode {
  if (k === "size_usd") return levels?.size ?? `${v} USD`;
  if (k === "entry" || k === "stop" || k === "tp") return levels?.[k] ?? v;
  if (k === "horizon_min") return levels?.horizon ?? `${v} min`;
  if (k === "in_mint" || k === "out_mint") return MINT_SYM[v] ? <>{MINT_SYM[v]} <span className="text-white/35">{v}</span></> : v;
  return v;
}

function ThesisTable({ p }: { p: Position }) {
  const t = p.thesis!;
  const keys = [...THESIS_ORDER.filter((k) => k in t), ...Object.keys(t).filter((k) => !THESIS_ORDER.includes(k))];
  return (
    <dl className="divide-y divide-white/[0.05]">
      {keys.map((k) => (
        <div key={k} className="grid grid-cols-[110px_minmax(0,1fr)] gap-3 py-2 text-[13px] sm:grid-cols-[140px_minmax(0,1fr)]">
          <dt className="text-white/45">{THESIS_LABEL[k] ?? k}</dt>
          <dd className={`break-words ${k === "why" ? "text-white/85" : "font-mono text-[12.5px] text-white/80"}`}>{thesisValue(k, t[k], p.levels)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Check({ ok, label, na }: { ok: boolean | null | undefined; label: string; na?: string }) {
  const unknown = ok === null || ok === undefined;
  return (
    <div className="flex items-center gap-2.5 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5 text-[13px]">
      {unknown ? <span className="h-3.5 w-3.5 rounded-full border border-white/20" /> : ok ? <CheckIcon className="h-3.5 w-3.5" /> : <CrossIcon className="h-3.5 w-3.5" />}
      <span className="text-white/75">{label}</span>
      <span className="ml-auto font-mono text-[12px] text-white/40">{unknown ? na ?? "n/a" : ok ? "yes" : "no"}</span>
    </div>
  );
}

const HONOURED: Record<string, string> = { stop_honoured: "Stop honoured", tp_honoured: "Take-profit honoured", expiry_honoured: "Horizon honoured" };

function Grade({ p }: { p: Position }) {
  const g = p.result;
  if (!g) return <p className="text-[13px] text-white/45">No grade yet (fills not indexed).</p>;
  const n = Number(g.pnl_usd);
  const checks = Object.entries(g.adherence?.checks ?? {});
  return (
    <div>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {[
          { l: "Net P&L", v: fmtPnl(g.pnl_usd), c: n < 0 ? "#FF5A4E" : n > 0 ? "#A8D86E" : undefined },
          { l: "R-multiple", v: g.r_multiple ? `${g.r_multiple}R` : "—" },
          { l: "Entry fill", v: g.entry_px ? Number(g.entry_px).toFixed(2) : "—" },
          { l: "Exit fill", v: g.exit_px ? Number(g.exit_px).toFixed(2) : "—" },
        ].map((x) => (
          <div key={x.l} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
            <div className="text-[11.5px] text-white/40">{x.l}</div>
            <div className="mt-0.5 font-mono text-[17px] text-white" style={x.c ? { color: x.c } : undefined}>{x.v}</div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11.5px] text-white/35">
        Gross {fmtPnl(g.gross_pnl_usd)}, fees {fmtPnl(g.fees_usd ? `-${g.fees_usd}` : null)}. Fills are USDC per SOL, measured from on-chain balance changes.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <Check ok={g.size_ok} label="Size within the committed plan" />
        <Check ok={g.qty_match} label="Exit sold the exact quantity bought" />
        {checks.length ? (
          checks.map(([k, v]) => <Check key={k} ok={v} label={HONOURED[k] ?? k.replace(/_/g, " ")} />)
        ) : (
          <Check ok={null} label="Exit honoured" na={p.exit_reason === "manual" ? "manual close" : "n/a"} />
        )}
      </div>
    </div>
  );
}

function VerifyButton({ p }: { p: Position }) {
  const [state, setState] = useState<{ status: "idle" | "busy" | "ok" | "bad"; hash?: string }>({ status: "idle" });
  const run = async () => {
    setState({ status: "busy" });
    // Re-encode the thesis fields ourselves (shared with /try) instead of trusting served bytes.
    const { canonical, digest: h } = await thesisDigest(p.thesis!, p.salt_hex!);
    setState({ status: h === p.digest && (!p.canonical || canonical === p.canonical) ? "ok" : "bad", hash: h });
  };
  return (
    <div className="rounded-2xl border border-white/[0.08] bg-black/30 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={run}
          disabled={state.status === "busy"}
          className="rounded-full bg-white px-4 py-2 text-[14px] font-medium text-black transition-transform hover:scale-[1.02] disabled:opacity-60"
        >
          {state.status === "busy" ? "Hashing…" : "Verify in your browser"}
        </button>
        {state.status === "ok" && (
          <span className="flex items-center gap-2 text-[14px] text-[#A8D86E]"><VerifiedCheck size={22} /> Matches the on-chain commit</span>
        )}
        {state.status === "bad" && (
          <span className="flex items-center gap-2 text-[14px] text-[#FF5A4E]">
            <span className="grid h-[22px] w-[22px] place-items-center rounded-full bg-[#FF5A4E]"><CrossIcon className="h-3 w-3" color="#fff" /></span>
            Does not match: tampered
          </span>
        )}
      </div>
      <p className="mt-3 text-[12px] leading-[18px] text-white/45">
        Encodes the thesis canonically and computes <span className="font-mono text-white/65">sha256(thesis ‖ salt)</span> right here with Web Crypto and compares it with the hash committed at slot {slot(p.commit_slot)}.
      </p>
      <div className="mt-3 space-y-1.5 font-mono text-[11.5px] leading-[17px]">
        <div className="break-all text-white/55"><span className="text-white/35">committed </span>{p.digest}</div>
        {state.hash && (
          <div className={`break-all ${state.status === "ok" ? "text-[#A8D86E]" : "text-[#FF5A4E]"}`}><span className="text-white/35">computed  </span>{state.hash}</div>
        )}
      </div>
    </div>
  );
}

/* ---------- page ---------- */

export function OathDetail({ seq }: { seq: number }) {
  const { pos: p, source, missing, ready } = usePosition(seq);
  const now = useNow();

  if (!p) {
    return (
      <div className="mx-auto max-w-[900px] px-4 pb-24 pt-10 sm:px-8">
        <Link href="/live" className="text-[13px] text-white/50 hover:text-white">← Live</Link>
        <h1 className="mt-6 text-[40px] font-medium tracking-[-0.03em] text-white">Oath #{seq}</h1>
        <p className="mt-3 text-white/55">{!ready ? "Loading…" : missing ? "No oath with this number is on record." : "Not in the last snapshot, and the live API is unreachable."}</p>
      </div>
    );
  }

  const revealed = !!(p.thesis && p.canonical && p.salt_hex && p.status === "revealed");
  const sealed = p.status === "committed" || p.status === "open" || p.status === "unrevealed";
  const deadline = p.reveal_deadline ? Date.parse(p.reveal_deadline) : NaN;
  const statusTag = revealed
    ? <Tag tone={p.digest_ok === false ? "red" : "green"}>{p.digest_ok === false ? "hash mismatch" : "revealed · verified"}</Tag>
    : p.status === "blocked" ? <Tag tone="red">blocked</Tag>
    : p.status === "unrevealed" ? <Tag tone="red">reveal overdue</Tag>
    : sealed ? <Tag tone="amber"><LockIcon className="h-3 w-3" /> sealed</Tag>
    : <Tag tone="red">{p.status}</Tag>;

  return (
    <div className="mx-auto w-full max-w-[1100px] px-4 pb-24 pt-6 sm:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3 text-[13px]">
        <Link href="/live" className="text-white/50 transition-colors hover:text-white">← Live</Link>
        <span className={source === "live" ? "text-white/40" : "text-[#FF5A4E]/80"}>
          {source === "live" ? "Live from the OATH API" : `Offline — last snapshot from ${fmtTime(Date.parse(SNAPSHOT_DATA.asOf) / 1000)}`}
        </span>
      </div>

      <header className="mt-7">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="headline-gradient text-[44px] font-medium leading-none tracking-[-0.035em] sm:text-[60px]">Oath #{p.seq}</h1>
          {statusTag}
        </div>
        {p.digest && (
          <div className="mt-4 flex flex-wrap items-center gap-2 text-[13px] text-white/50">commit hash <CopyHash value={p.digest} head={10} tail={10} /></div>
        )}
        {!!p.problems?.length && (
          <ul className="mt-3 space-y-1 text-[13px] text-[#FF5A4E]">{p.problems.map((x) => <li key={x}>• {x}</li>)}</ul>
        )}
      </header>

      <div className="mt-8 grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)] lg:items-start">
        <Panel className="p-5">
          <h2 className="mb-4 text-[15px] font-medium text-white">Timeline</h2>
          <Timeline p={p} />
        </Panel>

        <div className="flex min-w-0 flex-col gap-4">
          {revealed && (
            <>
              <Panel className="p-5">
                <div className="mb-2 flex items-center justify-between">
                  <h2 className="text-[15px] font-medium text-white">The thesis, as committed</h2>
                  <Tag tone="green">public since reveal</Tag>
                </div>
                <ThesisTable p={p} />
                <div className="mt-3 text-[12.5px] text-white/45">salt</div>
                <div className="mt-1 break-all font-mono text-[12px] text-white/70">{p.salt_hex}</div>
              </Panel>
              <Panel className="p-5">
                <h2 className="mb-3 text-[15px] font-medium text-white">Grade</h2>
                <Grade p={p} />
              </Panel>
              <VerifyButton p={p} />
            </>
          )}

          {sealed && (
            <Panel className="relative overflow-hidden border-[#F2C14E]/20 p-5">
              <div aria-hidden="true" className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-[#F2C14E]/[0.07] blur-3xl" />
              <div className="relative">
                <div className="flex items-center gap-2.5">
                  <span className="grid h-8 w-8 place-items-center rounded-full border border-[#F2C14E]/30 bg-[#F2C14E]/10"><LockIcon /></span>
                  <h2 className="text-[16px] font-medium text-white">Thesis sealed</h2>
                </div>
                <p className="mt-3 max-w-[560px] text-[13.5px] leading-[20px] text-white/55">
                  Entry, size, stop, target, horizon and reasoning are locked behind the hash above. They are published, with the salt, in the reveal after the trade closes. Changing a single character would change the hash.
                </p>
                <div aria-hidden="true" className="mt-4 space-y-2">
                  {[78, 64, 88, 52, 70].map((w, i) => <div key={i} className="h-3 rounded bg-white/[0.05]" style={{ width: `${w}%` }} />)}
                </div>
                {Number.isFinite(deadline) && (
                  <p className="mt-4 font-mono text-[12.5px] text-white/55">
                    reveal deadline {fmtTime(deadline / 1000)}
                    {now > 0 && <span className={deadline - now <= 0 ? " text-[#FF5A4E]" : " text-[#F2C14E]"}> · {deadline - now <= 0 ? "overdue" : `${Math.ceil((deadline - now) / 60000)} min left`}</span>}
                  </p>
                )}
              </div>
            </Panel>
          )}

          {p.status === "blocked" && (
            <Panel className="border-[#FF5A4E]/20 p-5">
              <h2 className="text-[15px] font-medium text-white">Stopped before any money moved</h2>
              <p className="mt-2 text-[13.5px] text-white/55">
                The firewall rejected this plan (<span className="font-mono text-[#FF5A4E]">{p.reason_code}</span>) and recorded the refusal on-chain. No swap was made.
              </p>
              {p.thesis && p.digest_matches_chain && (
                <div className="mt-4"><ThesisTable p={p} /></div>
              )}
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
