"use client";

import Link from "next/link";
import { fmtTime, humanCode, type LiveData, type Signal } from "@/lib/api";
import { fmtCompleteness } from "@/lib/stats";
import { CheckIcon, CrossIcon, Panel, Ring, Tag } from "./ui";

type Decision =
  | { type: "trade"; seq: number; time: number; why?: string; mkt?: string; side?: string; sealed: boolean }
  | { type: "blocked"; seq: number; time: number; reason?: string }
  | { type: "stand_aside"; time: number; reason: string; why: string; signals?: Signal[]; agreeing?: number; needs?: number; backfilled: boolean };

/** The most recent thing the agent decided: a committed trade, a firewall block, or a stand-aside. */
function latestDecisions(d: LiveData): Decision[] {
  const bySeq = new Map(d.positions.map((p) => [p.seq, p]));
  const out: Decision[] = [];
  for (const it of d.feed) {
    if (it.kind === "commit" && typeof it.seq === "number") {
      const p = bySeq.get(it.seq);
      out.push({ type: "trade", seq: it.seq, time: it.block_time, why: p?.thesis?.why, mkt: p?.thesis?.mkt,
                 side: p?.thesis?.side, sealed: !p?.thesis });
    } else if (it.kind === "blocked" && typeof it.seq === "number") {
      out.push({ type: "blocked", seq: it.seq, time: it.block_time, reason: it.reason_code });
    } else if (it.kind === "stand_aside") {
      out.push({ type: "stand_aside", time: it.block_time, reason: it.reason_code ?? "", why: it.why ?? "",
                 signals: it.evidence?.signals, agreeing: it.evidence?.agreeing, needs: it.evidence?.needs,
                 backfilled: !!it.evidence?.backfilled });
    }
  }
  return out.sort((a, b) => b.time - a.time);
}

function Signals({ signals }: { signals: Signal[] }) {
  return (
    <ul className="space-y-2">
      {signals.map((s) => (
        <li key={s.name} className="flex items-start gap-2.5 text-[13px]">
          <span className={`mt-[1px] grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full ${s.agrees ? "bg-[#A8D86E]/15" : "bg-white/[0.05]"}`}>
            {s.agrees ? <CheckIcon className="h-3 w-3" /> : <CrossIcon className="h-3 w-3" color="#7a7a7a" />}
          </span>
          <span className="min-w-0 flex-1 text-white/75">{s.name}</span>
          <span className="shrink-0 font-mono text-[12px] text-white/45">{s.reading}</span>
        </li>
      ))}
    </ul>
  );
}

function LatestDecision({ data }: { data: LiveData }) {
  const all = latestDecisions(data);
  const top = all[0];
  // the newest decision that carries a signal breakdown (stand-asides record theirs off-chain)
  const withSignals = all.find((x) => x.type === "stand_aside" && x.signals?.length) as Extract<Decision, { type: "stand_aside" }> | undefined;

  return (
    <Panel className="p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-medium text-white">Latest decision</h3>
        {top && <span className="font-mono text-[11.5px] text-white/40">{fmtTime(top.time)}</span>}
      </div>
      {!top ? (
        <p className="mt-3 text-[13.5px] text-white/45">No decisions recorded yet.</p>
      ) : (
        <div className="mt-3.5">
          {top.type === "trade" && (
            <Link href={`/oath/${top.seq}`} className="block rounded-xl border border-white/[0.07] bg-white/[0.025] p-3.5 transition-colors hover:border-white/15">
              <div className="flex flex-wrap items-center gap-2 text-[14px] text-white">
                Traded · Oath #{top.seq}
                {top.sealed ? <Tag tone="amber">sealed</Tag> : <Tag tone="green">revealed</Tag>}
              </div>
              <p className="mt-1.5 text-[13px] leading-[19px] text-white/55">
                {top.sealed
                  ? "The reasoning is sealed on-chain and will be revealed when the trade closes."
                  : <>{top.side && top.mkt && <span className="text-white/75">{top.side} {top.mkt} · </span>}&ldquo;{top.why}&rdquo;</>}
              </p>
            </Link>
          )}
          {top.type === "blocked" && (
            <Link href={`/oath/${top.seq}`} className="block rounded-xl border border-[#FF5A4E]/20 bg-[#FF5A4E]/[0.04] p-3.5">
              <div className="text-[14px] text-[#FF5A4E]">Blocked · Oath #{top.seq}</div>
              <p className="mt-1 font-mono text-[12px] text-white/55">{top.reason}</p>
            </Link>
          )}
          {top.type === "stand_aside" && (
            <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-3.5">
              <div className="flex flex-wrap items-center gap-2 text-[14px] text-white/80">
                Stood aside · {humanCode(top.reason)} {top.backfilled && <Tag>backfilled</Tag>}
              </div>
              <p className="mt-1 text-[13px] text-white/50">{top.why}</p>
            </div>
          )}

          {withSignals?.signals && (
            <div className="mt-4">
              <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 text-[12px] text-white/40">
                <span className="whitespace-nowrap">
                  {withSignals === top ? "Signals" : "Last signal check"} · <span className="text-white/65">{withSignals.agreeing}/{withSignals.signals.length} agreeing, needs {withSignals.needs}</span>
                </span>
                {withSignals !== top && <span className="whitespace-nowrap font-mono">{fmtTime(withSignals.time)}</span>}
              </div>
              <Signals signals={withSignals.signals} />
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function HonestyMeter({ data }: { data: LiveData }) {
  const s = data.stats;
  const closed = s.closed ?? 0;
  const completeness = closed > 0 ? Number(s.completeness ?? 0) : null;
  const adherence = closed > 0 ? 1 - (s.adherence_violations ?? 0) / closed : null;
  const pct = (v: number | null) => (v === null ? "—" : fmtCompleteness(String(v)));
  const colour = completeness === null || completeness >= 1 ? "#A8D86E" : completeness >= 0.9 ? "#F2C14E" : "#FF5A4E";

  return (
    <Panel className="p-5">
      <h3 className="text-[15px] font-medium text-white">Honesty meter</h3>
      <div className="mt-4 flex items-center gap-4">
        <Ring value={completeness ?? 0} size={92} stroke={7} color={colour}>
          <div className="text-center">
            <div className="font-mono text-[19px] font-medium text-white">{pct(completeness)}</div>
            <div className="text-[10px] uppercase tracking-[0.08em] text-white/40">revealed</div>
          </div>
        </Ring>
        <p className="text-[13px] leading-[19px] text-white/55">
          <span className="font-mono text-white">{s.revealed}</span> of <span className="font-mono text-white">{closed}</span> closed trades have their thesis revealed and hash-checked.
        </p>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-2.5">
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <dt className="text-[11.5px] text-white/40">Unrevealed</dt>
          <dd className={`mt-0.5 font-mono text-[18px] ${s.unrevealed > 0 ? "text-[#FF5A4E]" : "text-white"}`}>{s.unrevealed}</dd>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <dt className="text-[11.5px] text-white/40">Plan adherence</dt>
          <dd className={`mt-0.5 font-mono text-[18px] ${adherence !== null && adherence < 1 ? "text-[#F2C14E]" : "text-white"}`}>{pct(adherence)}</dd>
        </div>
      </dl>
      <div className="mt-3.5 flex items-center gap-2 text-[12.5px]">
        {s.verify_pass ? (
          <><CheckIcon className="h-3.5 w-3.5" /><span className="text-white/60">Independent verify passes on the full record</span></>
        ) : (
          <><CrossIcon className="h-3.5 w-3.5" /><span className="text-[#FF5A4E]">Verify reports issues</span></>
        )}
      </div>
      <p className="mt-2 text-[11.5px] leading-[17px] text-white/35">
        Adherence = closed trades whose exit honoured the revealed stop, take-profit or horizon.
      </p>
    </Panel>
  );
}

export function SidePanel({ data }: { data: LiveData }) {
  return (
    <div className="flex flex-col gap-4">
      <LatestDecision data={data} />
      <HonestyMeter data={data} />
    </div>
  );
}
