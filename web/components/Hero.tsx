"use client";

import { motion, useReducedMotion, type Variants } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchLiveStats, fmtCompleteness, fmtUsd, SNAPSHOT, type HeroStats } from "@/lib/stats";
import { HeroGlobe } from "./HeroGlobe";
import { Streaks } from "./Streaks";

const EASE = [0.22, 1, 0.36, 1] as const;

function SealIcon() {
  return (
    <svg viewBox="0 0 20 20" className="h-[17px] w-[17px]" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="7.6" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="10" cy="8.6" r="1.55" fill="currentColor" />
      <path d="M9.3 9.6h1.4l.65 3.5H8.65z" fill="currentColor" />
    </svg>
  );
}

function ArrowChip() {
  return (
    <span className="grid h-[30px] w-[42px] place-items-center rounded-full bg-[#141414] shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_1px_2px_rgba(0,0,0,0.5)] sm:h-[32px] sm:w-[46px]">
      <svg viewBox="0 0 20 20" className="h-[16px] w-[16px]" fill="none" aria-hidden="true">
        <path d="M3.8 10h11.6M10.9 5.5 15.4 10l-4.5 4.5" stroke="#fff" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

function Stat({ value, label, mono = true }: { value: string; label: string; mono?: boolean }) {
  return (
    <div className="flex flex-col items-center px-6 sm:px-10 lg:px-12">
      <span className={`${mono ? "font-mono" : ""} text-[21px] font-medium tracking-tight text-white sm:text-[22px]`}>{value}</span>
      <span className="mt-0.5 text-[14px] text-[#9A9A9A] sm:text-[15px]">{label}</span>
    </div>
  );
}

export function Hero() {
  const reduced = useReducedMotion() ?? false;
  const [globeReady, setGlobeReady] = useState(false);
  const [stats, setStats] = useState<HeroStats>(SNAPSHOT);

  useEffect(() => {
    let alive = true;
    fetchLiveStats().then((s) => alive && s && setStats(s));
    // Reveal the globe block when WebGL is ready, or after 2.5s at the latest, so a slow GPU or
    // software rendering never leaves the hero without its bloom/crown.
    const t = setTimeout(() => alive && setGlobeReady(true), 2500);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, []);

  // Globe rises first; the text column follows in sequence.
  const up: Variants = {
    hidden: { opacity: 0, y: reduced ? 0 : 14 },
    show: (i: number) => ({ opacity: 1, y: 0, transition: { duration: 0.7, ease: EASE, delay: 0.45 + i * 0.12 } }),
  };
  const statsTitle =
    stats.source === "live"
      ? `Live from the OATH chain index (${stats.asOf})`
      : `Last verified on-chain snapshot (${stats.asOf})`;

  return (
    <section className="hero relative flex flex-col items-center">
      {/* Side light streaks (behind everything) */}
      {/* Anchored to the globe in the reference's 1200x750 frame (dome top at y=95, R=245 there). */}
      <Streaks
        className="opacity-35 md:opacity-100"
        style={{ top: "calc(var(--globe-top) - var(--R) * 0.388)", height: "calc(var(--R) * 3.06)" }}
      />

      {/* Globe: top hemisphere, rising in */}
      <motion.div
        className="absolute left-1/2 z-0 -translate-x-1/2"
        style={{ top: "calc(var(--globe-top) - var(--R) * 0.35)" }}
        initial={{ opacity: 0, y: reduced ? 0 : 36 }}
        animate={globeReady ? { opacity: 1, y: 0 } : undefined}
        transition={{ duration: 1.3, ease: EASE }}
      >
        <HeroGlobe reducedMotion={reduced} onReady={() => setGlobeReady(true)} />
      </motion.div>

      {/* Copy column */}
      <div
        className="relative z-10 flex w-full flex-col items-center px-5 text-center"
        style={{ paddingTop: "calc(var(--globe-top) + var(--R) * 0.77)" }}
      >
        <motion.div custom={0} variants={up} initial="hidden" animate="show"
          className="flex items-center gap-2 text-[14px] text-[#9A9A9A] sm:text-[15.5px]">
          <span className="text-white/85"><SealIcon /></span>
          <span>
            The AI trader that <span className="font-semibold text-white">can&apos;t hide a call</span>
          </span>
        </motion.div>

        <motion.h1 custom={1} variants={up} initial="hidden" animate="show"
          className="headline-gradient mt-7 max-w-[12ch] text-balance text-[clamp(40px,5vw,72px)] font-semibold leading-[1.06] tracking-[-0.02em] sm:mt-9 sm:max-w-none">
          Every Trade Starts With An Oath
        </motion.h1>

        <motion.p custom={2} variants={up} initial="hidden" animate="show"
          className="mt-5 max-w-[560px] text-[16px] leading-[1.45] text-[#9A9A9A] sm:mt-6 sm:text-[18px] lg:max-w-[700px] lg:text-[19px]">
          OATH commits its trading thesis on-chain before every trade, then reveals it when the trade
          closes. Every call is provable. No hidden losses.
        </motion.p>

        <motion.div custom={3} variants={up} initial="hidden" animate="show" className="relative mt-9 sm:mt-10">
          {/* green glow pooled under the button */}
          <div className="pointer-events-none absolute left-1/2 top-[70%] h-[46px] w-[190px] -translate-x-1/2 rounded-full bg-[#3DFF6E] opacity-30 blur-[26px]" />
          <Link
            href="/live"
            className="group relative flex h-[50px] items-center gap-3.5 rounded-full border border-white/70 pl-6 pr-[7px] text-[17px] font-medium text-[#111] shadow-[0_0_0_1px_rgba(0,0,0,0.6),inset_0_1px_0_#fff,inset_0_-3px_8px_rgba(0,0,0,0.14),0_10px_30px_-8px_rgba(61,255,110,0.35)] transition-transform duration-200 hover:-translate-y-0.5 sm:h-[54px] sm:text-[18px]"
            style={{ background: "linear-gradient(180deg, #ffffff 0%, #f3f3f3 55%, #e4e4e4 100%)" }}
          >
            Watch it live
            <ArrowChip />
          </Link>
        </motion.div>

        <motion.div custom={4} variants={up} initial="hidden" animate="show"
          className="mt-14 flex flex-col items-center gap-5 sm:mt-[72px] sm:flex-row sm:gap-0" title={statsTitle}>
          <Stat value={String(stats.revealed)} label="Oaths kept" />
          <span className="hidden h-[14px] w-px bg-white/25 sm:block" />
          <Stat value={fmtCompleteness(stats.completeness)} label="Revealed on-chain" />
          <span className="hidden h-[14px] w-px bg-white/25 sm:block" />
          <Stat value={fmtUsd(stats.volumeUsd)} label="On-chain volume" />
        </motion.div>

        {/* faint vertical lines fading down under the stats */}
        <div className="floor-lines pointer-events-none mt-6 h-[120px] w-full max-w-[700px] sm:mt-3 sm:h-[140px]" />
      </div>
    </section>
  );
}
