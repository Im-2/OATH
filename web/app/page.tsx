import { Hero } from "@/components/Hero";
import { HowItWorks } from "@/components/how/HowItWorks";
import { Nav } from "@/components/Nav";
import { TokenSection } from "@/components/TokenSection";

export default function Home() {
  return (
    <>
    <main className="page-glow min-h-svh px-2 pb-4 sm:px-4 sm:pb-[22px]">
      {/* Dark card flush with the top of the browser (no top margin, border, corners or edge);
          rounded only at the bottom, where the green light bleeds up from behind it. */}
      <div
        className="grain relative mx-auto min-h-[calc(100svh-16px)] overflow-hidden rounded-b-[20px] border-b border-[#1a1a1a] shadow-[inset_0_-40px_60px_-50px_rgba(61,255,110,0.14)] sm:min-h-[calc(100svh-22px)] sm:rounded-b-[24px]"
        style={{ background: "linear-gradient(180deg, #0B0B0C 0px, #070708 160px)" }}
      >
        {/* side borders fade in below the fold line so nothing marks the top edge */}
        <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-0 w-px bg-[linear-gradient(180deg,transparent_0px,#1a1a1a_240px)]" />
        <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-0 w-px bg-[linear-gradient(180deg,transparent_0px,#1a1a1a_240px)]" />
        <Nav />
        <Hero />
      </div>
    </main>
    <HowItWorks />
    <TokenSection />
    </>
  );
}
