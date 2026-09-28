import Link from "next/link";
import { OathWordmark } from "./Logo";

const LINKS = [
  { href: "/live", label: "Live" },
  { href: "/verify", label: "Verify" },
  { href: "/performance", label: "Performance" },
  { href: "/build", label: "Build" },
];

export function CircleArrow({ className = "" }: { className?: string }) {
  return (
    <span
      className={`grid place-items-center rounded-full bg-white text-black ${className}`}
      aria-hidden="true"
    >
      <svg viewBox="0 0 16 16" className="h-[62%] w-[62%]" fill="none">
        <path d="M3.5 8h8.2M8.4 4.4 12 8l-3.6 3.6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function Nav() {
  return (
    <header className="relative z-30 flex h-[60px] items-center justify-between px-5 sm:h-[68px] sm:px-10 lg:px-[68px]">
      <div className="flex items-center gap-10 lg:gap-[52px]">
        <Link href="/" aria-label="OATH home" className="shrink-0">
          <OathWordmark className="h-[24px] w-auto sm:h-[28px]" />
        </Link>
        <nav className="hidden items-center gap-[30px] md:flex" aria-label="Main">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="text-[15px] text-white/60 transition-colors duration-200 hover:text-white"
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
      <Link
        href="/verify"
        className="group flex h-[36px] items-center gap-2.5 rounded-full border border-white/[0.07] bg-[#1b1b1c] pl-[18px] pr-[6px] text-[14px] sm:h-[38px] sm:text-[15px] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition-colors hover:bg-[#232324]"
      >
        <span className="hidden sm:inline">Verify it yourself</span>
        <span className="sm:hidden">Verify</span>
        <CircleArrow className="h-[22px] w-[22px] transition-transform duration-200 group-hover:translate-x-0.5" />
      </Link>
    </header>
  );
}
