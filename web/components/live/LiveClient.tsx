"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { SOLSCAN_ACCOUNT, fmtPnl, fmtTime, useLiveData, type LiveData, type Position } from "@/lib/api";
import { short, slot } from "@/lib/featured";
import { fmtCompleteness, fmtUsd } from "@/lib/stats";
import { useNow } from "@/lib/useNow";
import { SidePanel } from "./SidePanel";
import { Tape } from "./Tape";
import { sealedPositions } from "./rows";
import { CopyHash, ExternalIcon, LockIcon, Panel, Ring, Tag, TxLink } from "./ui";

/* ---------- 1 · status bar ---------- */

function StatusBar({ data, ready }: { data: LiveData; ready: boolean }) {
  const live = data.source === "live";
  const monitorOn = live && data.health.monitor?.online === true;
  const sealed = sealedPositions(data.positions);
  const state = !ready
    ? { text: "Connecting…", dot: "#9a9a9a", pulse: false }
    : !live
      ? { text: "Offline", dot: "#FF5A4E", pulse: false }
      : sealed.length
        ? { text: `Position open · seq ${sealed[0].seq}`, dot: "#F2C14E", pulse: true }
        : monitorOn
          ? { text: "Watching the market", dot: "#3DFF6E", pulse: true }
          : { text: "Idle", dot: "#9a9a9a", pulse: false };
  const monitor = !ready
    ? "Checking the API…"
    : !live
      ? `Offline — showing last snapshot from ${fmtTime(Date.parse(data.asOf) / 1000)}`
      : monitorOn
        ? "Monitor online"
        : "API online · monitor not running";
  const notary = data.health.notary;

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-[14px] border border-white/[0.07] bg-[#0f0f10]/80 px-4 py-2.5 text-[12.5px] sm:px-5 sm:text-[13px]">
      <span className="flex items-center gap-2.5 text-white">
        <span className="relative flex h-2.5 w-2.5">
          {state.pulse && <span className="absolute inset-0 animate-ping rounded-full opacity-60 motion-reduce:animate-none" style={{ background: state.dot }} />}
          <span className="relative h-2.5 w-2.5 rounded-full" style={{ background: state.dot, boxShadow: `0 0 10px ${state.dot}` }} />
        </span>
        <span className="font-medium">{state.text}</span>
      </span>
      <span className={live ? "text-white/55" : "text-[#FF5A4E]/85"}>{monitor}</span>
      {live && <span className="hidden font-mono text-[12px] text-white/40 sm:inline">updated {fmtTime(Date.parse(data.asOf) / 1000, false)}</span>}
      <a href={SOLSCAN_ACCOUNT(notary)} target="_blank" rel="noreferrer" title={notary}
         className="hidden items-center gap-1.5 text-white/50 transition-colors hover:text-[#A8D86E] md:inline-flex">
        notary <span className="font-mono text-[12px]">{short(notary, 4, 4)}</span><ExternalIcon />
      </a>
      <Link href="/verify" className="ml-auto text-[#A8D86E] transition-colors hover:text-white">Verify everything →</Link>
    </div>
  );
}

/* ---------- 2 · header + stat pills ---------- */

function StatPills({ data }: { data: LiveData }) {
  const s = data.stats;
  const pnl = Number(s.realised_pnl_usd);
  const pills: { label: string; value: string; tone?: string }[] = [
    { label: "oaths kept", value: String(s.revealed) },
    { label: "revealed", value: s.closed > 0 ? fmtCompleteness(s.completeness) : "—" },
    { label: "blocked", value: String(s.blocked), tone: s.blocked ? "#FF5A4E" : undefined },
    { label: "stood aside", value: String(s.stand_asides) },
    { label: "volume", value: fmtUsd(s.volume_usd) },
    { label: "realised P&L", value: fmtPnl(s.realised_pnl_usd), tone: pnl < 0 ? "#FF5A4E" : pnl > 0 ? "#A8D86E" : undefined },
  ];
  return (
    <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0">
      {pills.map((p) => (
        <div key={p.label} className="flex shrink-0 items-baseline gap-2 rounded-full border border-white/[0.08] bg-white/[0.03] px-3.5 py-1.5">
          <span className="font-mono text-[14.5px] text-white" style={p.tone ? { color: p.tone } : undefined}>{p.value}</span>
          <span className="text-[12.5px] text-white/45">{p.label}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------- 3 · open (sealed) positions ---------- */

function fmtLeft(ms: number) {
  if (ms <= 0) return "overdue";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}:${String(ss).padStart(2, "0")}`;
}

function SealedCard({ p }: { p: Position }) {
  const now = useNow();
  const start = (p.commit_time ?? 0) * 1000;
  const end = p.reveal_deadline ? Date.parse(p.reveal_deadline) : NaN;
  const hasClock = now > 0 && Number.isFinite(end) && start > 0;
  const left = hasClock ? end - now : 0;
  const frac = hasClock ? Math.max(0, Math.min(1, left / (end - start))) : 1;
  const overdue = p.status === "unrevealed" || (hasClock && left <= 0);

  const router = useRouter();
  const go = () => router.push(`/oath/${p.seq}`);
  return (
    <div role="link" tabIndex={0} aria-label={`Open Oath #${p.seq}`} onClick={go}
         onKeyDown={(e) => { if (e.key === "Enter") go(); }} className="block cursor-pointer rounded-[18px] focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#F2C14E]/50">
      <Panel className={`relative overflow-hidden p-4 transition-colors hover:border-white/15 sm:p-5 ${overdue ? "border-[#FF5A4E]/30" : "border-[#F2C14E]/20"}`}>
        <div aria-hidden="true" className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-[#F2C14E]/[0.07] blur-3xl" />
        <div className="relative flex items-start gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-full border border-[#F2C14E]/30 bg-[#F2C14E]/10"><LockIcon /></span>
              <span className="text-[16px] font-medium text-white">Oath #{p.seq} · <span className="text-[#F2C14E]">Sealed</span></span>
              {overdue ? <Tag tone="red">reveal overdue</Tag> : p.exit_sig ? <Tag tone="amber">closed · reveal pending</Tag> : p.swap_sig ? <Tag tone="amber">position open</Tag> : <Tag tone="amber">committed</Tag>}
            </div>
            <div className="mt-3.5 space-y-2 text-[12.5px] text-white/50">
              <div className="flex flex-wrap items-center gap-2">commit hash {p.digest && <CopyHash value={p.digest} />}</div>
              <div>commit slot <span className="font-mono text-white/75">{slot(p.commit_slot)}</span> · <span className="font-mono">{fmtTime(p.commit_time)}</span></div>
              <p className="text-white/40">Entry, size, stop and target stay sealed until the reveal. The hash above locks them in.</p>
            </div>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
              <TxLink sig={p.commit_sig} label="commit tx" />
              <TxLink sig={p.swap_sig} label="swap tx" />
              <TxLink sig={p.exit_sig} label="exit tx" />
            </div>
          </div>
          <div className="flex flex-col items-center gap-1.5">
            <Ring value={frac} size={78} stroke={6} color={overdue ? "#FF5A4E" : "#F2C14E"}>
              <span className="font-mono text-[13px] text-white">{hasClock ? fmtLeft(left) : "—"}</span>
            </Ring>
            <span className="max-w-[92px] text-center text-[10.5px] leading-[13px] text-white/40">to reveal deadline</span>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function EmptyOpen({ live, watching }: { live: boolean; watching: boolean }) {
  return (
    <Panel className="relative overflow-hidden px-5 py-7">
      <div aria-hidden="true" className="scan-line pointer-events-none absolute inset-y-0 w-1/3" />
      <div className="relative flex items-center gap-4">
        <div className="relative grid h-11 w-11 shrink-0 place-items-center">
          <span className="absolute inset-0 rounded-full border border-[#A8D86E]/25" />
          <span className="absolute inset-[7px] rounded-full border border-[#A8D86E]/15" />
          <span className="radar-sweep absolute inset-0 rounded-full" />
          <span className="h-1.5 w-1.5 rounded-full bg-[#A8D86E] shadow-[0_0_8px_#3DFF6E]" />
        </div>
        <div>
          <p className="text-[15px] text-white">{!live ? "No open oaths in the last snapshot." : watching ? "No open oaths. OATH is watching the market." : "No open oaths right now."}</p>
          <p className="mt-0.5 text-[12.5px] text-white/45">When it commits to a trade, the sealed oath appears here before the swap lands.</p>
        </div>
      </div>
    </Panel>
  );
}

/* ---------- page ---------- */

export function LiveClient() {
  const { data, ready } = useLiveData(10_000);
  const sealed = sealedPositions(data.positions);

  return (
    <div className="mx-auto w-full max-w-[1240px] px-4 pb-20 pt-4 sm:px-8 sm:pt-6">
      <StatusBar data={data} ready={ready} />

      <header className="mt-9 sm:mt-12">
        <h1 className="headline-gradient text-[44px] font-medium leading-[1] tracking-[-0.035em] sm:text-[64px]">Live</h1>
        <p className="mt-3 text-[16px] text-white/60 sm:text-[18px]">Every oath OATH takes, as it happens.</p>
        <div className="mt-6"><StatPills data={data} /></div>
      </header>

      <section className="mt-9" aria-labelledby="open-h">
        <div className="mb-3 flex items-baseline gap-2.5">
          <h2 id="open-h" className="text-[17px] font-medium text-white">Open positions</h2>
          <span className="text-[12.5px] text-white/40">{sealed.length} sealed</span>
        </div>
        {sealed.length ? (
          <div className="grid gap-3 md:grid-cols-2">{sealed.map((p) => <SealedCard key={p.seq} p={p} />)}</div>
        ) : (
          <EmptyOpen live={data.source === "live"} watching={data.source === "live" && data.health.monitor?.online === true} />
        )}
      </section>

      <div className="mt-9 grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
        {/* remount once when the first live read settles, so only events after that flash in */}
        <Tape key={ready ? "ready" : "boot"} feed={data.feed} positions={data.positions} />
        <aside className="lg:sticky lg:top-6"><SidePanel data={data} /></aside>
      </div>
    </div>
  );
}
