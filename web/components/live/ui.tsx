"use client";

import { useState } from "react";
import { SOLSCAN_TX, short } from "@/lib/featured";

export { VerifiedCheck } from "@/components/how/mocks";

/* ---------- icons (brand colours, no emoji) ---------- */

export function LockIcon({ className = "h-4 w-4", color = "#F2C14E" }: { className?: string; color?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" aria-hidden="true">
      <rect x="3" y="7" width="10" height="7" rx="1.6" stroke={color} strokeWidth="1.5" />
      <path d="M5.3 7V5.2a2.7 2.7 0 0 1 5.4 0V7" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function CheckIcon({ className = "h-4 w-4", color = "#A8D86E" }: { className?: string; color?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" aria-hidden="true">
      <path d="M3.5 8.4 6.6 11.4 12.5 4.9" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function CrossIcon({ className = "h-4 w-4", color = "#FF5A4E" }: { className?: string; color?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" aria-hidden="true">
      <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" stroke={color} strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export function BlockIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="5.6" stroke="#FF5A4E" strokeWidth="1.5" />
      <path d="M4.2 11.8 11.8 4.2" stroke="#FF5A4E" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function SwapIcon({ className = "h-4 w-4", color = "#ffffff" }: { className?: string; color?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" aria-hidden="true">
      <path d="M2.5 5.5h10M10 3l2.5 2.5L10 8M13.5 10.5h-10M6 8l-2.5 2.5L6 13" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function PauseIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="5.6" stroke="#9a9a9a" strokeWidth="1.4" />
      <path d="M6.6 5.8v4.4M9.4 5.8v4.4" stroke="#9a9a9a" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

export function FlagIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" aria-hidden="true">
      <path d="M4 14V2.5M4 3h7.5l-1.6 2.7L11.5 8.4H4" stroke="#9a9a9a" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ExternalIcon({ className = "h-3 w-3" }: { className?: string }) {
  return (
    <svg viewBox="0 0 12 12" className={className} fill="none" aria-hidden="true">
      <path d="M4.5 2.5h5v5M9.5 2.5 3 9" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ---------- small pieces ---------- */

export function TxLink({ sig, label, className = "" }: { sig?: string | null; label?: string; className?: string }) {
  if (!sig) return null;
  return (
    <a
      href={SOLSCAN_TX(sig)}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => e.stopPropagation()}
      title={sig}
      className={`inline-flex items-center gap-1 font-mono text-[11.5px] text-white/50 underline-offset-2 transition-colors hover:text-[#A8D86E] hover:underline ${className}`}
    >
      {label ?? short(sig, 5, 5)}
      <ExternalIcon />
    </a>
  );
}

export function CopyHash({ value, head = 8, tail = 8, className = "" }: { value: string; head?: number; tail?: number; className?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      title={`${value} (click to copy)`}
      onClick={async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {
          /* clipboard blocked: the full value is still in the title */
        }
      }}
      className={`group inline-flex items-center gap-1.5 rounded-md border border-white/[0.06] bg-white/[0.03] px-2 py-1 font-mono text-[12px] text-white/80 transition-colors hover:border-white/15 ${className}`}
    >
      <span>{short(value, head, tail)}</span>
      <span className={`text-[10.5px] ${copied ? "text-[#A8D86E]" : "text-white/35 group-hover:text-white/60"}`}>
        {copied ? "copied" : "copy"}
      </span>
    </button>
  );
}

export function Tag({ children, tone = "muted" }: { children: React.ReactNode; tone?: "muted" | "amber" | "red" | "green" }) {
  const cls = {
    muted: "border-white/10 text-white/45",
    amber: "border-[#F2C14E]/30 text-[#F2C14E] bg-[#F2C14E]/[0.06]",
    red: "border-[#FF5A4E]/30 text-[#FF5A4E] bg-[#FF5A4E]/[0.06]",
    green: "border-[#A8D86E]/35 text-[#A8D86E] bg-[#A8D86E]/[0.08]",
  }[tone];
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-[2px] text-[11px] leading-[16px] ${cls}`}>{children}</span>;
}

export function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-[18px] border border-white/[0.07] bg-[#0f0f10]/80 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] ${className}`}>
      {children}
    </section>
  );
}

/** A circular progress ring. `value` 0..1. */
export function Ring({ value, size = 64, stroke = 5, color = "#A8D86E", track = "rgba(255,255,255,0.07)", children }: {
  value: number; size?: number; stroke?: number; color?: string; track?: string; children?: React.ReactNode;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} stroke={track} strokeWidth={stroke} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round"
                strokeDasharray={c} strokeDashoffset={c * (1 - v)} style={{ transition: "stroke-dashoffset 600ms ease" }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center">{children}</div>
    </div>
  );
}
