"use client";

import { useEffect, useState } from "react";
import { askSandbox, type SandboxOutcome, type SandboxResult } from "@/lib/api";
import { CheckIcon, CopyHash, CrossIcon, LockIcon, Panel, Tag } from "@/components/live/ui";

const EXAMPLES = ["Is SOL a buy right now?", "Long JUP?", "Should I ape into a new memecoin?"];
const STEPS = ["Reading the market (read-only tools)…", "Scoring the playbook's four signals…", "Checking the firewall…", "Writing it up…"];

function SandboxBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[#F2C14E]/35 bg-[#F2C14E]/[0.08] px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.1em] text-[#F2C14E]">
      Sandbox · no money moves · nothing on-chain
    </span>
  );
}

function Resting({ message, onBreak }: { message: string; onBreak: () => void }) {
  return (
    <Panel className="p-6 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-full border border-white/10 bg-white/[0.03]">
        <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" aria-hidden="true">
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" stroke="#9a9a9a" strokeWidth="1.5" strokeLinejoin="round" />
        </svg>
      </div>
      <p className="mt-3 text-[16px] text-white">{message}</p>
      <p className="mt-1 text-[13px] text-white/45">The laptop running OATH may be off, or the free model is taking a break.</p>
      <button type="button" onClick={onBreak} className="mt-4 rounded-full bg-white px-4 py-2 text-[14px] font-medium text-black">Try Break it instead</button>
    </Panel>
  );
}

function Signals({ r }: { r: SandboxResult }) {
  return (
    <Panel className="p-5">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-[15px] font-medium text-white">Playbook evidence</h3>
        <span className="text-[12px] text-white/45">{r.agreeing}/4 agreeing · needs {r.needs}{r.against ? ` · ${r.against} against` : ""}</span>
      </div>
      <ul className="mt-3.5 space-y-2.5">
        {r.signals.map((s) => (
          <li key={s.name} className="flex items-start gap-2.5 text-[13px]">
            <span className={`mt-[1px] grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full ${s.agrees ? "bg-[#A8D86E]/15" : s.against ? "bg-[#FF5A4E]/15" : "bg-white/[0.05]"}`}>
              {s.agrees ? <CheckIcon className="h-3 w-3" /> : <CrossIcon className="h-3 w-3" color={s.against ? "#FF5A4E" : "#7a7a7a"} />}
            </span>
            <span className="min-w-0 flex-1 text-white/75">{s.name}{s.against && <span className="text-[#FF5A4E]"> · against</span>}</span>
            <span className="shrink-0 text-right font-mono text-[12px] text-white/50">{s.reading}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3.5 text-[11.5px] text-white/35">
        Live read-only data at {r.evidence.fetched_at?.toString().slice(11, 16)} UTC · SOL {r.evidence.quote_usdc_per_sol ?? r.evidence.sol_usd} USDC
      </p>
    </Panel>
  );
}

function Decision({ r }: { r: SandboxResult }) {
  const open = r.decision === "open";
  return (
    <Panel className="p-5">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className={`text-[20px] font-medium tracking-[-0.01em] ${open ? "text-[#A8D86E]" : "text-white"}`}>
          {open ? "Would open a SOL/USDC long" : "Stands aside"}
        </span>
        <Tag tone={open ? "green" : "muted"}>{r.reason_code}</Tag>
      </div>
      <p className="mt-2.5 text-[14px] leading-[21px] text-white/75">{r.reply}</p>
      <ul className="mt-3 space-y-1 text-[12.5px] text-white/50">{r.reasons.map((x) => <li key={x}>· {x}</li>)}</ul>
      <p className="mt-3 text-[11.5px] text-white/35">
        The decision comes from OATH&apos;s fixed playbook rules. The model only explains it
        {r.model ? <> ({r.model.split("/").pop()})</> : <> (model unavailable, so this explanation is templated: {r.model_note})</>}.
      </p>
    </Panel>
  );
}

function WouldCommit({ r }: { r: SandboxResult }) {
  const t = r.thesis!;
  const wc = r.would_commit!;
  const fw = r.firewall!;
  const rows: [string, string][] = [
    ["Entry", `${t.entry} USDC per SOL`], ["Stop", `${t.stop}`], ["Take-profit", `${t.tp}`], ["Size", `${t.size_usd} USDC`],
    ["Horizon", `${t.horizon_min} min`], ["Confidence", t.conf], ["Strategy", t.strat], ["Why", t.why], ["Seq", t.seq],
  ];
  return (
    <Panel className="relative overflow-hidden border-[#F2C14E]/25 p-5">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 grid place-items-center overflow-hidden">
        <span className="-rotate-[18deg] select-none whitespace-nowrap font-mono text-[64px] font-bold tracking-[0.2em] text-[#F2C14E]/[0.06] sm:text-[88px]">SANDBOX</span>
      </div>
      <div className="relative">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-full border border-[#F2C14E]/30 bg-[#F2C14E]/10"><LockIcon /></span>
          <h3 className="text-[16px] font-medium text-white">The oath it would seal</h3>
          <Tag tone="amber">not sent</Tag>
        </div>
        <dl className="mt-4 divide-y divide-white/[0.05]">
          {rows.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[100px_minmax(0,1fr)] gap-3 py-1.5 text-[13px]">
              <dt className="text-white/45">{k}</dt>
              <dd className="break-words font-mono text-[12.5px] text-white/80">{v}</dd>
            </div>
          ))}
        </dl>
        <div className={`mt-4 flex items-start gap-2.5 rounded-xl border p-3 text-[13px] ${fw.approve ? "border-[#A8D86E]/25 bg-[#A8D86E]/[0.05]" : "border-[#FF5A4E]/25 bg-[#FF5A4E]/[0.05]"}`}>
          {fw.approve ? <CheckIcon className="mt-0.5 h-4 w-4 shrink-0" /> : <CrossIcon className="mt-0.5 h-4 w-4 shrink-0" />}
          <div>
            <div className={fw.approve ? "text-[#A8D86E]" : "text-[#FF5A4E]"}>Firewall: {fw.approve ? "would approve" : `would block (${fw.reason})`}</div>
            {fw.detail && <div className="mt-0.5 font-mono text-[11.5px] text-white/50">{fw.detail}</div>}
          </div>
        </div>
        <div className="mt-4 text-[12px] text-white/45">Hash it would commit</div>
        <div className="mt-1"><CopyHash value={wc.digest} head={12} tail={12} /></div>
        <details className="mt-3 text-[12px] text-white/45">
          <summary className="cursor-pointer hover:text-white/70">Memo it would post (never sent)</summary>
          <pre className="mt-2 whitespace-pre-wrap break-all rounded-lg bg-black/40 p-2.5 font-mono text-[11px] text-white/60">{wc.memo}</pre>
          <div className="mt-2">salt</div>
          <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-[11px] text-white/60">{wc.salt_hex}</pre>
        </details>
      </div>
    </Panel>
  );
}

export function AskOath({ onBreak }: { onBreak: () => void }) {
  const [idea, setIdea] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [out, setOut] = useState<SandboxOutcome | null>(null);

  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 6000);
    return () => clearInterval(t);
  }, [busy]);

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setIdea(q);
    setBusy(true);
    setStep(0);
    setOut(null);
    const r = await askSandbox(q);
    setOut(r);
    setBusy(false);
  };

  return (
    <div className="flex flex-col gap-4">
      <Panel className="p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label htmlFor="idea" className="text-[15px] font-medium text-white">Give OATH a trade idea</label>
          <SandboxBadge />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); void ask(idea); }} className="mt-3">
          <textarea
            id="idea"
            value={idea}
            onChange={(e) => setIdea(e.target.value.slice(0, 280))}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(idea); } }}
            rows={2}
            maxLength={280}
            placeholder="e.g. Is SOL a buy right now?"
            className="w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3.5 py-3 text-[15px] text-white outline-none placeholder:text-white/30 focus:border-white/30"
          />
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" disabled={busy} onClick={() => void ask(ex)}
                      className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[12.5px] text-white/70 transition-colors hover:border-white/25 hover:text-white disabled:opacity-50">
                {ex}
              </button>
            ))}
            <span className="ml-auto font-mono text-[11px] text-white/30">{idea.length}/280</span>
            <button type="submit" disabled={busy || !idea.trim()}
                    className="rounded-full bg-white px-4 py-2 text-[14px] font-medium text-black transition-transform hover:scale-[1.02] disabled:opacity-50">
              {busy ? "Thinking…" : "Ask OATH"}
            </button>
          </div>
        </form>
        <p className="mt-3 text-[11.5px] leading-[17px] text-white/35">
          OATH evaluates your idea with read-only market data and its fixed playbook. It cannot trade, sign or write anything from here. Your text is treated as an idea to judge, never as instructions. 3 questions per 10 minutes.
        </p>
      </Panel>

      {busy && (
        <Panel className="relative overflow-hidden p-5">
          <div aria-hidden="true" className="scan-line pointer-events-none absolute inset-y-0 w-1/3" />
          <ol className="relative space-y-2 text-[13.5px]">
            {STEPS.map((s, i) => (
              <li key={s} className={i < step ? "text-white/40" : i === step ? "text-white" : "text-white/20"}>
                {i < step ? "✓ " : i === step ? "› " : "  "}{s}
              </li>
            ))}
          </ol>
          <p className="relative mt-3 text-[11.5px] text-white/35">Free model on a laptop: this can take up to a minute.</p>
        </Panel>
      )}

      {out?.kind === "resting" && <Resting message={out.message} onBreak={onBreak} />}
      {(out?.kind === "rate_limited" || out?.kind === "invalid") && (
        <Panel className="p-5 text-[14px] text-white/70">
          {out.message}{" "}
          {out.kind === "rate_limited" && <button type="button" onClick={onBreak} className="text-[#A8D86E] hover:underline">Try Break it meanwhile →</button>}
        </Panel>
      )}
      {out?.kind === "ok" && (
        <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
          <div className="flex min-w-0 flex-col gap-4">
            <Decision r={out.result} />
            <Signals r={out.result} />
          </div>
          {out.result.decision === "open" && out.result.thesis ? (
            <WouldCommit r={out.result} />
          ) : (
            <Panel className="p-5">
              <h3 className="text-[15px] font-medium text-white">No oath to seal</h3>
              <p className="mt-2 text-[13.5px] leading-[20px] text-white/55">
                Standing aside is a decision too. In live trading OATH records it (off-chain, free) and nothing is committed. Only trades get a sealed thesis and an on-chain hash.
              </p>
            </Panel>
          )}
        </div>
      )}
    </div>
  );
}
