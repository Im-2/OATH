/**
 * The flowing green "silk" ribbon behind each step's mock (as in the reference): a soft glowing
 * band plus many fine fibres, sweeping from the top-left down and out to the right. Pure SVG.
 */
const FIBRES = Array.from({ length: 26 }, (_, i) => i);

function fibre(i: number) {
  const t = i / (FIBRES.length - 1); // 0..1 across the ribbon's width
  const o = t * 70;
  return `M -40 ${190 + o * 0.5}
          C 110 ${60 + o * 0.9}, 250 ${20 + o * 0.8}, 420 ${70 + o * 0.9}
          S 700 ${230 + o * 1.0}, 1080 ${300 + o * 0.7}`;
}

export function Silk({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`silk-sway pointer-events-none absolute inset-0 h-full w-full ${className}`}
      viewBox="0 0 1024 380"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="silkBand" x1="0" y1="0" x2="1" y2="0.35">
          <stop offset="0" stopColor="#3DFF6E" stopOpacity="0" />
          <stop offset="0.16" stopColor="#3DFF6E" stopOpacity="0.55" />
          <stop offset="0.5" stopColor="#1f9c45" stopOpacity="0.45" />
          <stop offset="0.82" stopColor="#3DFF6E" stopOpacity="0.4" />
          <stop offset="1" stopColor="#3DFF6E" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="silkFibre" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#b8ffc6" stopOpacity="0" />
          <stop offset="0.25" stopColor="#b8ffc6" stopOpacity="0.9" />
          <stop offset="0.7" stopColor="#57e37d" stopOpacity="0.55" />
          <stop offset="1" stopColor="#3DFF6E" stopOpacity="0" />
        </linearGradient>
        <filter id="silkBlur" x="-20%" y="-50%" width="140%" height="200%">
          <feGaussianBlur stdDeviation="14" />
        </filter>
      </defs>
      <g>
        {/* soft body of the ribbon */}
        <path
          d="M -60 180 C 100 50, 250 5, 430 60 S 720 220, 1100 290 L 1100 400 C 780 330, 560 250, 430 170 S 160 150, -60 290 Z"
          fill="url(#silkBand)"
          filter="url(#silkBlur)"
          opacity="0.9"
        />
        {/* fine fibres */}
        {FIBRES.map((i) => (
          <path
            key={i}
            d={fibre(i)}
            fill="none"
            stroke="url(#silkFibre)"
            strokeWidth={i % 5 === 0 ? 1.4 : 0.7}
            opacity={0.18 + ((i * 37) % 11) / 30}
          />
        ))}
      </g>
    </svg>
  );
}
