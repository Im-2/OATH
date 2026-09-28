"use client";

/**
 * One floating UI mock per step, drawn on top of the silk ribbon (like the reference's program
 * cards / dashboard / phone). Every value is seq 2's real on-chain record from the snapshot.
 */
import { useEffect, useState } from "react";
import { FEATURED, oathDigest, short, slot, tamper } from "@/lib/featured";
import { amount } from "@/lib/present";

const F = FEATURED!;
const T = F.thesis as Record<string, string>;

const glass =
  "rounded-[14px] border border-white/[0.09] bg-[rgba(16,18,19,0.88)] shadow-[0_24px_60px_-20px_rgba(0,0,0,0.9),inset_0_1px_0_rgba(255,255,255,0.05)] backdrop-blur-md";

function Row({ k, v, mono = true, accent }: { k: string; v: string; mono?: boolean; accent?: string }) {
  return (
    <div className="flex items-center justify-between gap-6 py-[5px] text-[12px]">
      <span className="text-white/45">{k}</span>
      <span className={`${mono ? "font-mono" : ""} ${accent ?? "text-white/90"}`}>{v}</span>
    </div>
  );
}

function Pill({ children, tone }: { children: React.ReactNode; tone: "amber" | "green" | "muted" | "red" }) {
  const cls = {
    amber: "border-[#F2C14E]/40 bg-[#F2C14E]/12 text-[#F2C14E]",
    green: "border-[#A8D86E]/40 bg-[#A8D86E]/12 text-[#A8D86E]",
    muted: "border-white/10 bg-white/[0.04] text-white/55",
    red: "border-[#FF5A4E]/40 bg-[#FF5A4E]/12 text-[#FF5A4E]",
  }[tone];
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-[3px] text-[10px] font-semibold uppercase tracking-[0.14em] ${cls}`}>{children}</span>;
}

function Lock({ className = "h-3 w-3" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" aria-hidden="true">
      <rect x="3" y="7" width="10" height="7" rx="1.6" fill="currentColor" />
      <path d="M5.2 7V5.3a2.8 2.8 0 0 1 5.6 0V7" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function VerifiedCheck({ size = 22 }: { size?: number }) {
  return (
    <span className="grid place-items-center rounded-full bg-[#A8D86E] shadow-[0_0_18px_rgba(61,255,110,0.55)]" style={{ width: size, height: size }}>
      <svg viewBox="0 0 16 16" className="h-[60%] w-[60%]" fill="none" aria-hidden="true">
        <path d="M3.5 8.4 6.6 11.4 12.5 4.9" stroke="#fff" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

/* 1 · THESIS: stacked plan cards (the reference's fanned program cards) */
export function ThesisMock() {
  return (
    <div className="relative h-[250px] w-[400px]">
      {[3, 2, 1].map((k) => (
        <div key={k} className={`${glass} absolute h-[190px] w-[300px] opacity-70`}
          style={{ left: 40 - k * 22, top: 40 - k * 14, opacity: 0.25 + (3 - k) * 0.18 }}>
          <div className="px-4 pt-3 text-[10px] uppercase tracking-[0.18em] text-white/40">Thesis</div>
          <div className="mx-4 mt-3 h-2 w-24 rounded bg-white/10" />
          <div className="mx-4 mt-2 h-2 w-36 rounded bg-white/[0.07]" />
        </div>
      ))}
      <div className={`${glass} absolute left-[64px] top-[48px] w-[318px] p-4`}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-white/45">Thesis · seq {F.seq}</div>
            <div className="mt-1 text-[15px] font-semibold text-white">{T.mkt} · <span className="text-[#A8D86E]">{T.side.toUpperCase()}</span></div>
          </div>
          <Pill tone="muted"><Lock className="h-2.5 w-2.5" /> Private</Pill>
        </div>
        <div className="mt-3 border-t border-white/[0.07] pt-1.5">
          <Row k="Entry" v={`${Number(T.entry).toFixed(2)} USDC`} />
          <Row k="Stop" v={`${Number(T.stop).toFixed(2)} USDC`} accent="text-[#FF8A80]" />
          <Row k="Take-profit" v={`${Number(T.tp).toFixed(2)} USDC`} accent="text-[#A8D86E]" />
          <Row k="Size" v={`${T.size_usd} USDC`} />
          <Row k="Time limit" v={`${T.horizon_min} min`} />
        </div>
      </div>
    </div>
  );
}

/* 2 · COMMIT: the plan sealed into a hash on Solana (amber = sealed) */
export function CommitMock({ active }: { active: boolean }) {
  const target = F.digest!;
  const [shown, setShown] = useState(target);
  useEffect(() => {
    if (!active) return;
    const hex = "0123456789abcdef";
    let frame = 0;
    const id = setInterval(() => {
      frame++;
      const fixed = Math.min(target.length, frame * 3);
      setShown(target.slice(0, fixed) + Array.from({ length: target.length - fixed }, () => hex[(Math.random() * 16) | 0]).join(""));
      if (fixed >= target.length) clearInterval(id);
    }, 28);
    return () => clearInterval(id);
  }, [active, target]);
  return (
    <div className={`${glass} w-[430px] p-5 shadow-[0_0_60px_-10px_rgba(242,193,78,0.25),0_24px_60px_-20px_rgba(0,0,0,0.9)]`}>
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.18em] text-white/45">Commitment · seq {F.seq}</div>
        <Pill tone="amber"><Lock className="h-2.5 w-2.5" /> Sealed</Pill>
      </div>
      <div className="mt-3 text-[11px] text-white/45">sha256(thesis ‖ salt)</div>
      <div className="mt-1 break-all font-mono text-[14.5px] leading-[1.45] text-[#F2C14E]">{shown}</div>
      <div className="mt-3 border-t border-white/[0.07] pt-1.5">
        <Row k="Posted on" v="Solana · Memo program" mono={false} />
        <Row k="Slot" v={slot(F.commit_slot)} />
        <Row k="Tx" v={short(F.commit_sig, 8, 8)} />
      </div>
      <div className="mt-3 text-[11px] text-white/40">The plan itself stays private. Only this hash is public.</div>
    </div>
  );
}

/* 3 · TRADE: only after the commit lands, enforced by code */
export function TradeMock() {
  const e = F.entry_fill!;
  const gap = (F.swap_slot ?? 0) - (F.commit_slot ?? 0);
  return (
    <div className="relative h-[260px] w-[500px]">
      <div className={`${glass} absolute left-0 top-[26px] w-[330px] p-4`}>
        <div className="flex items-center justify-between">
          <div className="text-[10px] uppercase tracking-[0.18em] text-white/45">Entry swap · seq {F.seq}</div>
          <Pill tone="green">Filled</Pill>
        </div>
        <div className="mt-2 font-mono text-[20px] font-medium text-white">{amount(e.out_raw, e.out_mint)}</div>
        <div className="text-[11px] text-white/45">for {amount(e.in_raw, e.in_mint)} · Jupiter via ClawPump</div>
        {/* slot order: commit must land before the swap */}
        <div className="mt-4 rounded-[10px] border border-white/[0.06] bg-black/30 p-3">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.16em] text-white/40">
            <span>Commit</span><span>Swap</span>
          </div>
          <div className="relative mt-2 h-[2px] rounded bg-white/10">
            <div className="absolute inset-y-0 left-0 w-full rounded bg-gradient-to-r from-[#F2C14E] to-[#A8D86E]" />
            <span className="absolute -top-[4px] left-0 h-[10px] w-[10px] rounded-full bg-[#F2C14E]" />
            <span className="absolute -top-[4px] right-0 h-[10px] w-[10px] rounded-full bg-[#A8D86E]" />
          </div>
          <div className="mt-2 flex items-center justify-between font-mono text-[11.5px] text-white/85">
            <span>{slot(F.commit_slot)}</span><span className="text-white/40">+{gap} slots</span><span>{slot(F.swap_slot)}</span>
          </div>
        </div>
      </div>
      <div className={`${glass} absolute right-0 top-0 w-[190px] p-3.5`}>
        <div className="text-[10px] uppercase tracking-[0.18em] text-white/45">Guard</div>
        <div className="mt-2 flex items-center justify-between text-[12px] text-white/85">
          <span>Commit first</span>
          <span className="relative inline-flex h-[18px] w-[32px] items-center rounded-full bg-[#A8D86E]/85 px-[2px]"><span className="ml-auto h-[14px] w-[14px] rounded-full bg-white" /></span>
        </div>
        <div className="mt-2 text-[11px] leading-snug text-white/45">Direct swaps are blocked. The model can only trade through a commitment.</div>
      </div>
      <div className={`${glass} absolute bottom-0 right-[18px] w-[210px] p-3.5`}>
        <Row k="Fill price" v={`${(Number(e.in_raw) / 1e6 / (Number(e.out_raw) / 1e9)).toFixed(2)}`} />
        <Row k="Swap tx" v={short(F.swap_sig, 5, 5)} />
      </div>
    </div>
  );
}

/* 4 · REVEAL: the plan and its salt published on-chain (phone-style card, like the reference) */
export function RevealMock() {
  const pretty = JSON.stringify(T, null, 1).replace(/^\{\n|\n\}$/g, "").split("\n").slice(0, 9);
  return (
    <div className="w-[270px] rounded-[26px] border border-white/[0.1] bg-[rgba(12,14,15,0.92)] p-2.5 shadow-[0_30px_70px_-20px_rgba(0,0,0,0.95),inset_0_1px_0_rgba(255,255,255,0.06)]">
      <div className="rounded-[20px] border border-white/[0.05] bg-black/40 p-3.5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[12.5px] font-semibold text-white">Reveal · seq {F.seq}</div>
            <div className="text-[10.5px] text-white/45">closed: {F.exit_reason} · slot {slot(F.reveal_slot)}</div>
          </div>
          <Pill tone="green">Public</Pill>
        </div>
        <div className="mt-3 rounded-[10px] bg-white/[0.03] p-2.5 font-mono text-[10px] leading-[1.55] text-white/75">
          {pretty.map((l, i) => <div key={i} className="truncate">{l.trim()}</div>)}
          <div className="text-white/35">…</div>
        </div>
        <div className="mt-2.5 text-[10px] uppercase tracking-[0.16em] text-white/40">Salt</div>
        <div className="break-all font-mono text-[10px] leading-[1.45] text-[#A8D86E]">{F.salt_hex}</div>
      </div>
    </div>
  );
}

/* 5 · VERIFIED: recompute the hash in this browser; tamper one character and it fails */
export function VerifyMock({ active }: { active: boolean }) {
  const [ok, setOk] = useState<null | { good: string; bad: string }>(null);
  const t = tamper(F.canonical!);
  useEffect(() => {
    if (!active) return;
    let alive = true;
    Promise.all([oathDigest(F.canonical!, F.salt_hex!), oathDigest(t.text, F.salt_hex!)])
      .then(([good, bad]) => alive && setOk({ good, bad }))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [active, t.text]);
  const matches = ok?.good === F.digest;
  return (
    <div className={`${glass} w-[450px] p-5`}>
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.18em] text-white/45">Recomputed in your browser</div>
        {matches ? (
          <span className="flex items-center gap-2 text-[12px] font-semibold text-white"><VerifiedCheck /> Verified</span>
        ) : (
          <Pill tone="muted">computing…</Pill>
        )}
      </div>
      <div className="mt-3 text-[11px] text-white/45">sha256(revealed thesis ‖ salt)</div>
      <div className="mt-1 break-all font-mono text-[12.5px] leading-[1.45] text-[#A8D86E]">{ok?.good ?? "…"}</div>
      <div className="mt-1 text-[11px] text-white/45">
        {matches ? "= the digest committed at slot " + slot(F.commit_slot) : "comparing with the committed digest…"}
      </div>
      <div className="mt-4 rounded-[10px] border border-[#FF5A4E]/25 bg-[#FF5A4E]/[0.06] p-3">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-white/60">stop <span className="font-mono text-white/80">{t.from}</span> → <span className="font-mono text-[#FF5A4E]">{t.to}</span></span>
          <Pill tone="red">✗ Fails</Pill>
        </div>
        <div className="mt-1.5 break-all font-mono text-[11px] leading-[1.4] text-[#FF5A4E]/85">{ok?.bad ?? "…"}</div>
      </div>
    </div>
  );
}
