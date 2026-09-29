import Link from "next/link";
import { OATH_BUY_URL } from "@/lib/token";
import { OathWordmark } from "./Logo";
import { LINKS } from "./Nav";
import { TokenAddress } from "./TokenAddress";

export function Footer() {
  return (
    <footer className="relative border-t border-white/[0.06] bg-[#0B0B0C] px-5 pb-10 pt-12 sm:px-10 lg:px-[68px]">
      <div className="mx-auto grid w-full max-w-[1240px] gap-10 md:grid-cols-[1fr_minmax(0,460px)] md:items-start">
        <div>
          <OathWordmark className="h-[26px] w-auto" />
          <p className="mt-3 max-w-[340px] text-[13.5px] leading-[20px] text-white/50">
            The AI trader that can&apos;t hide a call. Every thesis sealed on Solana before the trade, revealed after.
          </p>
          <nav aria-label="Footer" className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-[13.5px]">
            {LINKS.map((l) => (
              <Link key={l.href} href={l.href} className="text-white/55 transition-colors hover:text-white">{l.label}</Link>
            ))}
            <a href="https://github.com/Im-2/OATH" target="_blank" rel="noopener noreferrer" className="text-white/55 transition-colors hover:text-white">GitHub</a>
          </nav>
        </div>
        <div className="min-w-0">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[12px] font-medium uppercase tracking-[0.18em] text-white/40">$OATH contract</span>
            <a href={OATH_BUY_URL} target="_blank" rel="noopener noreferrer" className="text-[13px] text-[#A8D86E] hover:text-white">
              Buy $OATH ↗
            </a>
          </div>
          <div className="mt-2"><TokenAddress compact /></div>
        </div>
      </div>
      <p className="mx-auto mt-10 w-full max-w-[1240px] text-[12px] text-white/30">
        Built for the AnsemHack Clawrena. Not financial advice; trades are small, real and on-chain.
      </p>
    </footer>
  );
}
