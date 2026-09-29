"use client";

import { useEffect, useRef, useState } from "react";
import { RPC_URLS, verifyFromChain, type ChainReport, type LogLine } from "@/lib/chainVerify";
import { CrossIcon, Panel, VerifiedCheck } from "@/components/live/ui";

type State =
  | { phase: "idle" }
  | { phase: "running" }
  | { phase: "done"; report: ChainReport }
  | { phase: "error"; message: string };

const TONE: Record<LogLine["tone"], string> = {
  ok: "text-[#A8D86E]",
  bad: "text-[#FF5A4E]",
  info: "text-white/85",
  dim: "text-white/40",
};

export function ChainRun({ notary, expected }: { notary: string; expected: number }) {
  const [state, setState] = useState<State>({ phase: "idle" });
  const [lines, setLines] = useState<LogLine[]>([]);
  const [prog, setProg] = useState<{ done: number; total: number }>({ done: 0, total: 0 });
  const [customRpc, setCustomRpc] = useState("");
  const [showRpc, setShowRpc] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const ctl = useRef<AbortController | null>(null);

  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);
  useEffect(() => () => ctl.current?.abort(), []);

  const run = async () => {
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setLines([]);
    setProg({ done: 0, total: 0 });
    setState({ phase: "running" });
    try {
      const own = customRpc.trim();
      const urls = /^https:\/\/[^\s]+$/.test(own) ? [own, ...RPC_URLS.filter((u) => u !== own)] : RPC_URLS;
      const report = await verifyFromChain(
        notary,
        (l) => setLines((xs) => [...xs, l]),
        (done, total) => setProg({ done, total }),
        c.signal,
        urls,
      );
      setState({ phase: "done", report });
    } catch (e) {
      if (c.signal.aborted) return;
      const message = e instanceof Error ? e.message : String(e);
      setLines((xs) => [...xs, { tone: "bad", text: `  ✗ stopped: ${message}` }]);
      setState({ phase: "error", message });
    }
  };

  const pct = prog.total ? Math.round((prog.done / prog.total) * 100) : 0;
  const running = state.phase === "running";

  return (
    <Panel className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b border-white/[0.06] px-4 py-3.5 sm:px-5">
        <button
          type="button"
          onClick={run}
          disabled={running}
          className="rounded-full bg-white px-4 py-2 text-[14px] font-medium text-black transition-transform hover:scale-[1.02] disabled:opacity-60"
        >
          {running ? "Verifying…" : state.phase === "idle" ? "Run verification in my browser" : "Run it again"}
        </button>
        {running && (
          <button type="button" onClick={() => { ctl.current?.abort(); setState({ phase: "idle" }); }}
                  className="text-[13px] text-white/50 hover:text-white">
            Cancel
          </button>
        )}
        <button type="button" onClick={() => setShowRpc(!showRpc)} className="ml-auto text-[12px] text-white/40 underline-offset-2 hover:text-white/70 hover:underline">
          {customRpc ? "using your RPC" : "use your own RPC"}
        </button>
      </div>

      {showRpc && (
        <div className="border-b border-white/[0.06] px-4 py-3 sm:px-5">
          <label className="block text-[12px] text-white/50" htmlFor="own-rpc">
            Optional: a Solana RPC URL you trust. Free public RPCs keep only about two days of history; a full-history
            RPC (e.g. a free Helius or QuickNode endpoint) lets your browser check every oath ever taken.
          </label>
          <input
            id="own-rpc"
            value={customRpc}
            onChange={(e) => setCustomRpc(e.target.value)}
            placeholder="https://mainnet.helius-rpc.com/?api-key=…"
            spellCheck={false}
            className="mt-2 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 font-mono text-[12.5px] text-white outline-none placeholder:text-white/25 focus:border-white/30"
          />
          <p className="mt-1.5 text-[11px] text-white/30">Stays in your browser. Tried first, then the public RPCs.</p>
        </div>
      )}

      {(running || prog.total > 0) && (
        <div className="h-[3px] bg-white/[0.05]" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-[#A8D86E] shadow-[0_0_10px_#3DFF6E] transition-[width] duration-300" style={{ width: `${pct}%` }} />
        </div>
      )}

      <div
        ref={box}
        aria-live="polite"
        className="h-[300px] overflow-y-auto overflow-x-hidden bg-[#050506] px-4 py-3.5 font-mono text-[12px] leading-[19px] sm:h-[340px] sm:px-5 sm:text-[12.5px]"
      >
        {lines.length === 0 ? (
          <p className="text-white/35">
            {"// "}Press the button. Your browser will fetch every transaction the notary signed, parse the
            oath1: memos, recompute each sha256 with Web Crypto and check the order of every step.
            {expected ? ` The API says there are ${expected} oaths; see if your browser agrees.` : ""}
          </p>
        ) : (
          lines.map((l, i) => (
            <div key={i} className={`whitespace-pre-wrap break-words ${TONE[l.tone]}`}>{l.text}</div>
          ))
        )}
        {running && <div className="mt-1 text-white/50">  scanning{prog.total ? ` ${prog.done}/${prog.total} transactions` : "…"}<span className="animate-pulse">▍</span></div>}
      </div>

      {state.phase === "done" && (
        <div className={`flex flex-wrap items-center gap-3 border-t px-4 py-4 sm:px-5 ${state.report.pass ? "border-[#A8D86E]/20 bg-[#A8D86E]/[0.05]" : "border-[#FF5A4E]/25 bg-[#FF5A4E]/[0.05]"}`}>
          {state.report.pass ? <VerifiedCheck size={28} /> : (
            <span className="grid h-7 w-7 place-items-center rounded-full bg-[#FF5A4E]"><CrossIcon className="h-4 w-4" color="#fff" /></span>
          )}
          <span className={`text-[16px] font-medium ${state.report.pass ? "text-white" : "text-[#FF5A4E]"}`}>
            {state.report.pass
              ? `Independently verified ${state.report.verified}/${state.report.total} oaths${state.report.outOfReach.length ? " within reach" : ""}`
              : `${state.report.issues.length} problem(s) found by your browser`}
          </span>
          <span className="text-[12.5px] text-white/45">{state.report.txs} notary txs · {state.report.memos} memos · no OATH server involved</span>
          {state.report.outOfReach.length > 0 && (
            <p className="w-full text-[12.5px] leading-[18px] text-white/55">
              {state.report.outOfReach.length} older oath{state.report.outOfReach.length > 1 ? "s" : ""} (seq {state.report.outOfReach.join(", ")}) predate
              {" "}what these public RPCs keep (history from slot {state.report.horizonSlot?.toLocaleString("en-US")}). They&apos;re still on-chain:
              {" "}<button type="button" onClick={() => setShowRpc(true)} className="text-[#A8D86E] hover:underline">use a full-history RPC</button>
              {" "}or run the Python command below to check them too.
            </p>
          )}
        </div>
      )}
      {state.phase === "error" && (
        <div className="border-t border-[#FF5A4E]/25 px-4 py-3.5 text-[13px] text-white/60 sm:px-5">
          The public RPC stopped answering ({state.message}), so the check couldn&apos;t finish. Public RPCs throttle browsers; try again in a minute, or run the Python command below.
        </div>
      )}
    </Panel>
  );
}
