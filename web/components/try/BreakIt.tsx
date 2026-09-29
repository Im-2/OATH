"use client";

import { useEffect, useMemo, useState } from "react";
import { canonicalJson, fmtDecimal, normaliseThesis, oathDigest, DECIMALS, type Thesis } from "@/lib/canonical";
import { type Position } from "@/lib/api";
import { SOLSCAN_TX, slot } from "@/lib/featured";
import { CheckIcon, CrossIcon, Panel, Tag, TxLink, VerifiedCheck } from "@/components/live/ui";

const MAIN_FIELDS = ["entry", "stop", "tp", "size_usd", "conf", "horizon_min", "why"];
const LABEL: Record<string, string> = {
  entry: "Entry (USDC per SOL)", stop: "Stop (USDC per SOL)", tp: "Take-profit (USDC per SOL)", size_usd: "Size (USDC)",
  conf: "Confidence", horizon_min: "Horizon (minutes)", why: "Why", mkt: "Market", side: "Side", strat: "Strategy",
  ts: "Written at", seq: "Seq", agent: "Agent", in_mint: "Pays with (mint)", out_mint: "Buys (mint)", v: "Format",
};

/** The same field, normalised the way OATH's encoder would write it. */
function normField(k: string, v: string) {
  return k in DECIMALS ? fmtDecimal(v, DECIMALS[k]) ?? v : v;
}

function HashDiff({ a, b }: { a: string; b: string }) {
  return (
    <>
      {b.split("").map((ch, i) => (
        <span key={i} className={ch === a[i] ? "" : "text-[#FF5A4E]"}>{ch}</span>
      ))}
    </>
  );
}

export function BreakIt({ positions }: { positions: Position[] }) {
  const revealed = useMemo(
    () => positions.filter((p) => p.status === "revealed" && p.thesis && p.salt_hex && p.digest).sort((a, b) => b.seq - a.seq),
    [positions],
  );
  const [seq, setSeq] = useState<number | null>(revealed[0]?.seq ?? null);
  const pos = revealed.find((p) => p.seq === seq) ?? revealed[0];
  const original = pos?.thesis as Thesis | undefined;
  const [edits, setEdits] = useState<Thesis>(original ?? {});
  const [hash, setHash] = useState<string>("");
  const [showAll, setShowAll] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const pick = (s: number) => {
    const p = revealed.find((x) => x.seq === s);
    setSeq(s);
    setEdits((p?.thesis as Thesis) ?? {});
    setNote(null);
  };

  const encoded = useMemo(() => canonicalJson(normaliseThesis(edits)), [edits]);
  useEffect(() => {
    if (!pos?.salt_hex) return;
    let live = true;
    void oathDigest(encoded, pos.salt_hex).then((h) => live && setHash(h));
    return () => {
      live = false;
    };
  }, [encoded, pos?.salt_hex]);

  if (!pos || !original) {
    return <Panel className="p-8 text-center text-white/50">No revealed oath yet. Once OATH reveals one, you can try to break it here.</Panel>;
  }

  const changed = new Set(Object.keys(original).filter((k) => normField(k, edits[k] ?? "") !== original[k]));
  const matches = hash === pos.digest;
  const pending = hash === "";
  const fields = showAll ? [...MAIN_FIELDS, ...Object.keys(original).filter((k) => !MAIN_FIELDS.includes(k))] : MAIN_FIELDS;

  const fakeWin = () => {
    const exitPx = Number(pos.result?.exit_px ?? pos.thesis?.entry);
    // Claim the entry was 1% below where it actually exited: a "win" on paper.
    const fakeEntry = (exitPx * 0.99).toFixed(6);
    const e = Number(fakeEntry);
    setEdits({ ...original, entry: fakeEntry, stop: (e * 0.97).toFixed(6), tp: (exitPx * 0.999).toFixed(6), why: "TREND_UP: called the bounce perfectly" });
    setNote(`Claims OATH bought at ${fakeEntry} and targeted just under the real exit (${exitPx.toFixed(2)}), so the trade reads as a win.`);
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)] lg:items-start">
      <Panel className="min-w-0 p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-2.5 text-[13px] text-white/55">
            Oath
            <select
              value={pos.seq}
              onChange={(e) => pick(Number(e.target.value))}
              className="rounded-lg border border-white/10 bg-[#141415] px-2.5 py-1.5 font-mono text-[13px] text-white focus:border-white/30 focus:outline-none"
            >
              {revealed.map((p) => <option key={p.seq} value={p.seq}>#{p.seq} · {p.thesis?.strat}</option>)}
            </select>
          </label>
          <div className="flex gap-2">
            <button type="button" onClick={() => { setEdits(original); setNote(null); }}
                    className="rounded-full border border-white/12 px-3.5 py-1.5 text-[13px] text-white/75 transition-colors hover:border-white/30 hover:text-white">
              Reset
            </button>
            <button type="button" onClick={fakeWin}
                    className="rounded-full bg-[#FF5A4E]/15 px-3.5 py-1.5 text-[13px] text-[#FF8A80] ring-1 ring-[#FF5A4E]/30 transition-colors hover:bg-[#FF5A4E]/25">
              Try to fake a win
            </button>
          </div>
        </div>
        {note && <p className="mt-3 rounded-lg border border-[#FF5A4E]/20 bg-[#FF5A4E]/[0.05] px-3 py-2 text-[12.5px] text-white/65">{note}</p>}

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {fields.map((k) => {
            const dirty = changed.has(k);
            const wide = k === "why" || k === "agent" || k.endsWith("_mint");
            const norm = normField(k, edits[k] ?? "");
            return (
              <label key={k} className={`block ${wide ? "sm:col-span-2" : ""}`}>
                <span className="flex items-center justify-between text-[12px] text-white/45">
                  {LABEL[k] ?? k}
                  {dirty && <span className="text-[11px] text-[#FF5A4E]">changed</span>}
                </span>
                <input
                  value={edits[k] ?? ""}
                  onChange={(e) => setEdits({ ...edits, [k]: e.target.value })}
                  spellCheck={false}
                  className={`mt-1 w-full rounded-lg border bg-black/40 px-3 py-2 font-mono text-[13px] text-white outline-none transition-colors ${
                    dirty ? "border-[#FF5A4E]/60 bg-[#FF5A4E]/[0.06]" : "border-white/10 focus:border-white/30"
                  }`}
                />
                {k in DECIMALS && norm !== (edits[k] ?? "") && (
                  <span className="mt-0.5 block font-mono text-[11px] text-white/35">encodes as {norm}</span>
                )}
              </label>
            );
          })}
        </div>
        <button type="button" onClick={() => setShowAll(!showAll)} className="mt-3 text-[12.5px] text-white/45 hover:text-white">
          {showAll ? "Hide the other fields" : `Show all ${Object.keys(original).length} fields`}
        </button>
      </Panel>

      <div className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-6">
        <Panel className={`relative overflow-hidden p-5 transition-colors ${pending ? "" : matches ? "border-[#A8D86E]/30" : "border-[#FF5A4E]/40"}`}>
          <div aria-hidden="true" className={`pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full blur-3xl ${matches ? "bg-[#3DFF6E]/[0.1]" : "bg-[#FF5A4E]/[0.1]"}`} />
          <div className="relative" aria-live="polite">
            {pending ? (
              <p className="text-white/50">Hashing…</p>
            ) : matches ? (
              <div className="flex items-center gap-3.5">
                <VerifiedCheck size={46} />
                <p className="text-[18px] font-medium leading-snug text-white">Matches what OATH committed on-chain</p>
              </div>
            ) : (
              <div className="flex items-center gap-3.5">
                <span className="grid h-[46px] w-[46px] shrink-0 place-items-center rounded-full bg-[#FF5A4E] shadow-[0_0_18px_rgba(255,90,78,0.5)]">
                  <CrossIcon className="h-6 w-6" color="#fff" />
                </span>
                <p className="text-[18px] font-medium leading-snug text-[#FF5A4E]">Tampered: this is not what OATH committed</p>
              </div>
            )}
            {!matches && !pending && changed.size > 0 && (
              <p className="mt-3 text-[12.5px] text-white/55">
                Changed: {[...changed].map((k) => <Tag key={k} tone="red">{LABEL[k]?.split(" (")[0] ?? k}</Tag>)}
              </p>
            )}
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="grid gap-3 font-mono text-[11.5px] leading-[17px] sm:grid-cols-2 lg:grid-cols-1">
            <div>
              <div className="mb-1 flex items-center justify-between font-sans text-[12px] text-white/45">
                Committed on-chain <TxLink sig={pos.commit_sig} label={`slot ${slot(pos.commit_slot)}`} />
              </div>
              <div className="break-all rounded-lg bg-black/40 p-2.5 text-white/80">{pos.digest}</div>
            </div>
            <div>
              <div className="mb-1 flex items-center gap-1.5 font-sans text-[12px] text-white/45">
                Your version, hashed live {matches ? <CheckIcon className="h-3.5 w-3.5" /> : <CrossIcon className="h-3.5 w-3.5" />}
              </div>
              <div className={`break-all rounded-lg bg-black/40 p-2.5 ${matches ? "text-[#A8D86E]" : "text-white/80"}`}>
                {hash ? <HashDiff a={pos.digest!} b={hash} /> : "…"}
              </div>
            </div>
          </div>
          <div className="mt-4 text-[12px] text-white/45">salt (published in the reveal)</div>
          <div className="mt-1 break-all font-mono text-[11.5px] text-white/65">{pos.salt_hex}</div>
          <p className="mt-4 text-[12px] leading-[18px] text-white/45">
            <span className="font-mono text-white/65">sha256(canonical_json(thesis) ‖ salt)</span>, computed in your browser on every keystroke with the same encoding OATH uses: sorted keys, no whitespace, every value a fixed-decimal string.
            {" "}<a className="text-white/60 underline-offset-2 hover:underline" href={SOLSCAN_TX(pos.commit_sig!)} target="_blank" rel="noreferrer">See the commit on Solscan ↗</a>
          </p>
          <details className="mt-3 text-[12px] text-white/45">
            <summary className="cursor-pointer hover:text-white/70">Exact bytes being hashed</summary>
            <pre className="mt-2 whitespace-pre-wrap break-all rounded-lg bg-black/40 p-2.5 font-mono text-[11px] text-white/65">{encoded}</pre>
          </details>
        </Panel>
      </div>
    </div>
  );
}
