"use client";

/**
 * "How it works": design matched to web-reference/how it works.mp4; motion is SCROLL-DRIVEN.
 *
 * A tall outer container (one screen-height of scroll per step) holds a sticky, full-screen inner
 * container, so the section pins while you scroll through it:
 *   progress p in [0, 1] = useScroll(target: outer, offset ["start start", "end end"])
 *   bar i fill           = clamp(p * N - i, 0, 1)
 *   active step          = min(N - 1, floor(p * N))
 * Both come from the same p, so a step becomes active exactly when the previous bar reaches 100%.
 * After step N's bar fills, the outer container ends and the page scrolls on; scrolling back up
 * re-pins at step N and runs backwards. No timers, no autoplay.
 * Clicking a step label smooth-scrolls to that step's start. Reduced motion: still scroll-driven,
 * but card/text swaps are instant (no blur, slide or crossfade).
 */
import {
  AnimatePresence,
  motion,
  type MotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useTransform,
} from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { CommitMock, RevealMock, ThesisMock, TradeMock, VerifyMock } from "./mocks";
import { Silk } from "./Silk";

const EASE = [0.22, 1, 0.36, 1] as const;

const STEPS = [
  { key: "thesis", title: "Thesis", text: "The agent writes its plan: entry, stop, take-profit, size, time limit." },
  { key: "commit", title: "Commit", text: "The plan is sealed into a hash and posted on Solana. Nobody can read it yet." },
  { key: "trade", title: "Trade", text: "Only after the commit lands can the agent trade. Enforced by code." },
  { key: "reveal", title: "Reveal", text: "When the trade closes, the plan and its salt are published on-chain." },
  { key: "verified", title: "Verified", text: "Anyone can recompute the hash. Change one character and it fails." },
] as const;
const N = STEPS.length;

/** The single source of truth for "which step", shared by the bars and the active index. */
export function stepFromProgress(p: number) {
  return Math.min(N - 1, Math.max(0, Math.floor(p * N)));
}
export function fillFromProgress(p: number, i: number) {
  return Math.min(1, Math.max(0, p * N - i));
}

function Mock({ i, active }: { i: number; active: boolean }) {
  switch (i) {
    case 0: return <ThesisMock />;
    case 1: return <CommitMock active={active} />;
    case 2: return <TradeMock />;
    case 3: return <RevealMock />;
    default: return <VerifyMock active={active} />;
  }
}

/** Scales the fixed-size desktop mock down to fit narrow/short panels. */
function useFitScale(designW: number, designH: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      setScale(Math.min(1, (width - 20) / designW, (height - 20) / designH));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [designW, designH]);
  return { ref, scale };
}

/** One progress bar, filled directly from scroll (no animation of its own). */
function StepBar({ progress, i }: { progress: MotionValue<number>; i: number }) {
  const fill = useTransform(progress, (p) => fillFromProgress(p, i));
  return (
    <span className="relative block h-[3px] w-full overflow-hidden rounded-full bg-white/[0.1] sm:h-px sm:rounded-none">
      <motion.span
        className="absolute inset-y-0 left-0 w-full origin-left bg-gradient-to-r from-[#A8D86E] to-[#3DFF6E]"
        style={{ scaleX: fill }}
      />
    </span>
  );
}

// Blueprint corner marks around the heading drift a little on each step (as in the reference).
const MARKS = [
  { cls: "left-[6%] top-[18%] border-l border-t", dx: [0, 10, -6, 14, 4], dy: [0, 6, -4, 2, 8] },
  { cls: "right-[8%] top-[4%] border-r border-t", dx: [0, -12, 6, -4, -10], dy: [0, 4, 10, -2, 6] },
  { cls: "left-[20%] bottom-[2%] border-l border-b", dx: [0, 8, 14, -6, 2], dy: [0, -6, 4, 8, -4] },
  { cls: "right-[22%] bottom-[10%] border-r border-b", dx: [0, -6, -14, 6, -2], dy: [0, 8, -6, 4, 10] },
];

export function HowItWorks() {
  const reduced = useReducedMotion() ?? false;
  const outerRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: outerRef, offset: ["start start", "end end"] });
  const [step, setStep] = useState(0);
  const [switching, setSwitching] = useState(false);
  const { ref: stageRef, scale } = useFitScale(520, 270);

  // Active step follows scroll; a change opens the short transition window (ribbon dims, grid shows).
  useMotionValueEvent(scrollYProgress, "change", (p) => {
    const next = stepFromProgress(p);
    setStep((cur) => {
      if (cur !== next && !reduced) setSwitching(true);
      return next;
    });
  });

  useEffect(() => {
    if (!switching) return;
    const id = setTimeout(() => setSwitching(false), 750);
    return () => clearTimeout(id);
  }, [switching, step]);

  /** Smooth-scroll to the start of step i (just past its boundary so it is the active one). */
  const scrollToStep = (i: number) => {
    const el = outerRef.current;
    if (!el) return;
    const top = el.getBoundingClientRect().top + window.scrollY;
    const scrollable = el.offsetHeight - window.innerHeight;
    window.scrollTo({ top: top + (scrollable * i) / N + 2, behavior: reduced ? "auto" : "smooth" });
  };

  const colPct = ((step + 0.5) / N) * 100;
  const cardAnim = reduced
    ? { initial: { opacity: 0 }, animate: { opacity: 1, transition: { duration: 0 } }, exit: { opacity: 0, transition: { duration: 0 } } }
    : {
        initial: { opacity: 0, y: 16, scale: 0.97, filter: "blur(12px)" },
        animate: { opacity: 1, y: 0, scale: 1, filter: "blur(0px)", transition: { duration: 0.55, delay: 0.18, ease: EASE } },
        exit: { opacity: 0, scale: 0.985, filter: "blur(10px)", transition: { duration: 0.32, ease: EASE } },
      };
  const textAnim = reduced
    ? { initial: { opacity: 0 }, animate: { opacity: 1, transition: { duration: 0 } }, exit: { opacity: 0, transition: { duration: 0 } } }
    : {
        initial: { opacity: 0, y: 8 },
        animate: { opacity: 1, y: 0, transition: { duration: 0.35, delay: 0.12, ease: EASE } },
        exit: { opacity: 0, y: -4, transition: { duration: 0.2, ease: EASE } },
      };

  return (
    <section ref={outerRef} id="how-it-works" className="relative bg-[#0B0B0C]" style={{ height: `${(N + 1) * 100}svh` }}>
      <div className="sticky top-0 flex h-svh flex-col justify-center overflow-hidden px-4 sm:px-6">
        {/* faint blueprint grid behind the panel */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-[8%] mx-auto h-[80%] max-w-[1180px] transition-opacity duration-500"
          style={{
            opacity: switching ? 0.9 : 0.35,
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            WebkitMaskImage: "radial-gradient(55% 55% at 50% 45%, #000 20%, transparent 75%)",
            maskImage: "radial-gradient(55% 55% at 50% 45%, #000 20%, transparent 75%)",
          }}
        />

        {/* heading */}
        <div className="relative mx-auto w-full max-w-[760px] text-center">
          {MARKS.map((m, i) => (
            <motion.span
              key={i}
              aria-hidden="true"
              className={`pointer-events-none absolute hidden h-[22px] w-[22px] border-[#A8D86E]/35 sm:block ${m.cls}`}
              animate={reduced ? undefined : { x: m.dx[step], y: m.dy[step] }}
              transition={{ duration: 0.9, ease: EASE }}
            />
          ))}
          <h2 className="text-[32px] font-medium leading-[1.1] tracking-[-0.02em] text-white sm:text-[48px]">
            How does it{" "}
            <span className="bg-gradient-to-b from-[#A8D86E] to-[#d9f2bd] bg-clip-text text-transparent">work?</span>
          </h2>
          <p className="mt-3 text-[14px] text-[#9A9A9A] sm:text-[15.5px]">From a private plan to a public proof, in five steps.</p>
        </div>

        {/* panel */}
        <div className="relative mx-auto mt-7 w-full max-w-[1024px] sm:mt-10">
          <div className="relative h-[min(300px,40svh)] overflow-hidden rounded-[16px] border border-white/[0.07] bg-[#0c0e0f] sm:h-[min(380px,44svh)]">
            <motion.div className="absolute inset-0" animate={{ opacity: switching ? 0.32 : 1 }} transition={{ duration: reduced ? 0 : 0.45, ease: EASE }}>
              <Silk className={reduced ? "" : "silk-animate"} />
            </motion.div>
            {/* inner grid shows through during the swap */}
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 transition-opacity duration-500"
              style={{
                opacity: switching ? 0.8 : 0,
                backgroundImage:
                  "linear-gradient(rgba(168,216,110,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(168,216,110,0.07) 1px, transparent 1px)",
                backgroundSize: "48px 48px",
              }}
            />
            {/* mock stage (right of centre, like the reference); cross-dissolve, never waits */}
            <div ref={stageRef} className="absolute inset-0 sm:left-[12%]">
              <AnimatePresence initial={false}>
                <motion.div
                  key={step}
                  className="absolute inset-0 flex items-center justify-center"
                  {...cardAnim}
                  style={{ transformOrigin: "center", willChange: "opacity, transform, filter" }}
                >
                  <div style={{ transform: `scale(${scale})`, transformOrigin: "center" }}>
                    <Mock i={step} active />
                  </div>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
          {/* green edge glow that slides to the active step (left edge at step 1, right edge at step 5) */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 rounded-[16px] border-2 border-[#3DFF6E]"
            style={{
              WebkitMaskImage: `radial-gradient(46% 150% at ${colPct}% 100%, #000 0%, rgba(0,0,0,0.6) 42%, transparent 74%)`,
              maskImage: `radial-gradient(46% 150% at ${colPct}% 100%, #000 0%, rgba(0,0,0,0.6) 42%, transparent 74%)`,
              filter: "drop-shadow(0 0 8px rgba(61,255,110,0.85)) drop-shadow(0 0 22px rgba(61,255,110,0.35))",
            }}
          />
        </div>

        {/* timeline */}
        <div className="relative mx-auto mt-5 w-full max-w-[1024px] sm:mt-6">
          {/* warm spotlight under the active column */}
          <motion.div
            aria-hidden="true"
            className="pointer-events-none absolute -top-10 hidden h-[260px] w-[320px] -translate-x-1/2 rounded-full sm:block"
            style={{ background: "radial-gradient(50% 50% at 50% 45%, rgba(168,216,110,0.20) 0%, rgba(242,193,78,0.07) 45%, transparent 72%)", filter: "blur(10px)" }}
            animate={{ left: `${colPct}%` }}
            transition={{ duration: reduced ? 0 : 0.8, ease: EASE }}
          />
          <div className="relative grid grid-cols-5 gap-2 sm:gap-6" role="tablist" aria-label="How it works">
            {STEPS.map((s, i) => {
              const active = i === step;
              return (
                <button
                  key={s.key}
                  role="tab"
                  aria-selected={active}
                  aria-label={`Step ${i + 1}: ${s.title}`}
                  onClick={() => scrollToStep(i)}
                  className="group flex flex-col items-start py-2 text-left outline-none sm:py-0"
                >
                  <StepBar progress={scrollYProgress} i={i} />
                  <span
                    className={`mt-3 hidden whitespace-nowrap text-[11px] font-medium uppercase tracking-[0.22em] transition-colors duration-300 sm:inline ${
                      active ? "text-white" : "text-white/35 group-hover:text-white/60"
                    }`}
                  >
                    {active ? `[ Step ${i + 1} ]` : `Step ${i + 1}`}
                  </span>
                </button>
              );
            })}
          </div>

          {/* active step title + text: under its column on desktop, full width under the card on phones */}
          <div className="relative mt-3 grid min-h-[104px] grid-cols-1 sm:mt-5 sm:grid-cols-5 sm:gap-6">
            <AnimatePresence initial={false}>
              <motion.div
                key={step}
                className={`step-text [grid-row:1] ${step === N - 1 ? "step-text-last" : ""}`}
                style={{ ["--col" as string]: String(Math.min(step, N - 2) + 1) }}
                {...textAnim}
              >
                <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-white/40 sm:hidden">
                  [ Step {step + 1} of {N} ]
                </div>
                <h3 className="mt-1 text-[17px] font-medium text-white sm:mt-0 sm:text-[18px]">
                  Step {step + 1}: {STEPS[step].title}
                </h3>
                <p className="mt-2 max-w-[340px] text-[14px] leading-[1.55] text-[#9A9A9A]">{STEPS[step].text}</p>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  );
}
