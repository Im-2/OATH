"use client";

import { useState } from "react";
import { useLiveData } from "@/lib/api";
import { AskOath } from "./AskOath";
import { BreakIt } from "./BreakIt";

type Tab = "break" | "ask";

export function TryClient() {
  const [tab, setTab] = useState<Tab>("break");
  const { data } = useLiveData(30_000);

  return (
    <div className="mx-auto w-full max-w-[1160px] px-4 pb-24 pt-8 sm:px-8 sm:pt-12">
      <header>
        <h1 className="headline-gradient text-[44px] font-medium leading-[1] tracking-[-0.035em] sm:text-[64px]">Try</h1>
        <p className="mt-3 max-w-[640px] text-[16px] text-white/60 sm:text-[18px]">
          Try to rewrite history and watch the hash give you away. Or hand OATH a trade idea and see how it decides.
        </p>
      </header>

      <div role="tablist" aria-label="Try" className="mt-7 inline-flex rounded-full border border-white/[0.08] bg-black/30 p-1">
        {([["break", "Break it"], ["ask", "Ask OATH"]] as const).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            id={`tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`panel-${id}`}
            onClick={() => setTab(id)}
            className={`rounded-full px-4 py-2 text-[14px] transition-colors ${tab === id ? "bg-white text-black" : "text-white/60 hover:text-white"}`}
          >
            {label}
            {id === "ask" && <span className={`ml-1.5 font-mono text-[10px] uppercase tracking-[0.08em] ${tab === id ? "text-black/50" : "text-[#F2C14E]/80"}`}>sandbox</span>}
          </button>
        ))}
      </div>

      <div className="mt-5" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "break" ? <BreakIt positions={data.positions} /> : <AskOath onBreak={() => setTab("break")} />}
      </div>
    </div>
  );
}
