import { Hero } from "@/components/Hero";
import { Nav } from "@/components/Nav";

export default function Home() {
  return (
    <main className="page-glow min-h-svh px-2 pb-4 pt-2 sm:px-4 sm:pb-[22px] sm:pt-4">
      {/* Rounded dark card; the green light bleeds up from behind its bottom edge */}
      <div className="grain relative mx-auto min-h-[calc(100svh-24px)] overflow-hidden rounded-[20px] border border-[#1a1a1a] bg-[#070708] shadow-[inset_0_-40px_60px_-50px_rgba(61,255,110,0.14)] sm:min-h-[calc(100svh-38px)] sm:rounded-[24px]">
        <Nav />
        <Hero />
      </div>
    </main>
  );
}
