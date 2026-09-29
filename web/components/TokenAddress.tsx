"use client";

import { useState } from "react";
import { OATH_MINT } from "@/lib/token";

/** The full $OATH contract address with a copy button (never shortened: people paste it into wallets). */
export function TokenAddress({ compact = false }: { compact?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(OATH_MINT);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked: the address is selectable */
    }
  };
  return (
    <div className={`flex min-w-0 items-center gap-2 rounded-xl border border-white/[0.08] bg-black/40 ${compact ? "p-1.5 pl-3" : "p-2 pl-3.5"}`}>
      <code className={`min-w-0 flex-1 select-all break-all font-mono text-white/85 ${compact ? "text-[11.5px] leading-[16px]" : "text-[12.5px] leading-[18px] sm:text-[13.5px]"}`}>
        {OATH_MINT}
      </code>
      <button
        type="button"
        onClick={copy}
        aria-label="Copy $OATH contract address"
        className={`shrink-0 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
          copied ? "bg-[#A8D86E] text-black" : "bg-white/[0.08] text-white/80 hover:bg-white/[0.14]"
        }`}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
