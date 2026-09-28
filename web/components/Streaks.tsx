/**
 * Thin curved light streaks fanning out left and right from behind the globe (SVG, drawn in the
 * reference's 1200x750 frame), with short bright green dashes travelling outward on a loop.
 * The dashes animate via stroke-dashoffset in CSS (.streak-dash) and stop for reduced motion.
 */
const LEFT = [
  { d: "M372 172 C 250 160, 140 158, 20 164", o: 0.16 },
  { d: "M368 198 C 250 196, 130 204, 16 216", o: 0.12 },
  { d: "M372 226 C 260 232, 140 250, 18 280", o: 0.14 },
  { d: "M382 252 C 270 268, 150 300, 22 356", o: 0.12 },
  { d: "M398 276 C 300 298, 180 340, 40 420", o: 0.1 },
];
const mirror = (d: string) =>
  d.replace(/(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)/g, (_m, x, y) => `${1200 - Number(x)} ${y}`);
const RIGHT = [
  { d: mirror("M372 172 C 250 160, 140 158, 20 164"), o: 0.14 },
  { d: mirror("M368 198 C 250 196, 130 204, 16 216"), o: 0.12 },
  { d: mirror("M366 224 C 250 226, 140 238, 18 262"), o: 0.14 },
  { d: mirror("M378 250 C 270 262, 150 292, 22 340"), o: 0.12 },
  { d: mirror("M396 274 C 290 300, 170 346, 36 424"), o: 0.1 },
];
// Which streaks carry a travelling light (index into LEFT / RIGHT) + timing.
const DASHES = [
  { side: "L", i: 3, dur: "6.5s", delay: "0s" },
  { side: "L", i: 1, dur: "8s", delay: "3.2s" },
  { side: "R", i: 3, dur: "7s", delay: "1.4s" },
  { side: "R", i: 0, dur: "8.5s", delay: "4.6s" },
];

export function Streaks({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg
      style={style}
      className={`pointer-events-none absolute inset-x-0 ${className}`}
      viewBox="0 0 1200 750"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="fadeL" x1="1" y1="0" x2="0" y2="0">
          <stop offset="0" stopColor="#fff" stopOpacity="0" />
          <stop offset="0.25" stopColor="#dfffe4" stopOpacity="1" />
          <stop offset="0.8" stopColor="#fff" stopOpacity="0.7" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="fadeR" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#fff" stopOpacity="0" />
          <stop offset="0.25" stopColor="#dfffe4" stopOpacity="1" />
          <stop offset="0.8" stopColor="#fff" stopOpacity="0.7" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <filter id="dashGlow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {LEFT.map((s, i) => (
        <path key={`l${i}`} d={s.d} fill="none" stroke="url(#fadeL)" strokeOpacity={s.o} strokeWidth="1" vectorEffect="non-scaling-stroke" />
      ))}
      {RIGHT.map((s, i) => (
        <path key={`r${i}`} d={s.d} fill="none" stroke="url(#fadeR)" strokeOpacity={s.o} strokeWidth="1" vectorEffect="non-scaling-stroke" />
      ))}
      {DASHES.map((x, k) => (
        <path
          key={`d${k}`}
          d={(x.side === "L" ? LEFT : RIGHT)[x.i].d}
          pathLength={100}
          fill="none"
          stroke="#3DFF6E"
          strokeWidth="1.8"
          strokeLinecap="round"
          filter="url(#dashGlow)"
          className="streak-dash"
          style={{ ["--dur" as string]: x.dur, ["--delay" as string]: x.delay }}
        />
      ))}
    </svg>
  );
}
