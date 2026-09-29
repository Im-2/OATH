import { OATH_BUY_URL, OATH_SOLSCAN } from "@/lib/token";
import { OathMark } from "./Logo";
import { CircleArrow } from "./Nav";
import { TokenAddress } from "./TokenAddress";

/* Facts only, all checked on-chain: nothing here is a promise about price or future features. */
const FACTS = [
  { k: "Standard", v: "Token-2022" },
  { k: "Supply", v: "1,000,000,000" },
  { k: "Mint authority", v: "Revoked" },
  { k: "Freeze authority", v: "Revoked" },
];

export function TokenSection() {
  return (
    <section id="token" aria-labelledby="token-h" className="relative bg-[#0B0B0C] px-4 py-24 sm:px-8 sm:py-32">
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-1/2 mx-auto h-[420px] max-w-[900px] -translate-y-1/2 rounded-full bg-[#3DFF6E]/[0.06] blur-[120px]" />
      <div className="relative mx-auto w-full max-w-[960px]">
        <div className="text-center">
          <OathMark className="mx-auto h-12 w-12 drop-shadow-[0_0_24px_rgba(61,255,110,0.35)]" />
          <h2 id="token-h" className="mt-5 text-[32px] font-medium leading-[1.1] tracking-[-0.02em] text-white sm:text-[48px]">
            The <span className="bg-gradient-to-b from-[#A8D86E] to-[#d9f2bd] bg-clip-text text-transparent">$OATH</span> token
          </h2>
          <p className="mx-auto mt-3 max-w-[560px] text-[14px] text-[#9A9A9A] sm:text-[15.5px]">
            OATH&apos;s token, launched on ClawPump. Check the contract address before you buy, and only buy what you can afford to lose.
          </p>
        </div>

        <div className="mt-10 rounded-[20px] border border-white/[0.08] bg-[#0f0f10]/80 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] sm:p-7">
          <div className="text-[12px] font-medium uppercase tracking-[0.18em] text-white/40">Contract address</div>
          <div className="mt-2.5"><TokenAddress /></div>

          <dl className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            {FACTS.map((f) => (
              <div key={f.k} className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3">
                <dt className="text-[11.5px] text-white/40">{f.k}</dt>
                <dd className="mt-0.5 font-mono text-[14px] text-white">{f.v}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
            <a
              href={OATH_BUY_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex h-[48px] items-center justify-between gap-3 rounded-full bg-white pl-6 pr-[6px] text-[15.5px] font-medium text-black transition-transform hover:scale-[1.02] sm:justify-start"
            >
              Buy $OATH on ClawPump
              <span className="grid h-[36px] w-[36px] place-items-center rounded-full bg-black text-white" aria-hidden="true">
                <svg viewBox="0 0 16 16" className="h-[55%] w-[55%]" fill="none">
                  <path d="M3.5 8h8.2M8.4 4.4 12 8l-3.6 3.6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
            </a>
            <a href={OATH_SOLSCAN} target="_blank" rel="noopener noreferrer"
               className="inline-flex items-center gap-2 px-2 text-[14px] text-white/60 transition-colors hover:text-[#A8D86E]">
              View on Solscan <CircleArrow className="h-[20px] w-[20px] -rotate-45" />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
