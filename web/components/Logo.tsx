/**
 * OATH wordmark, drawn from web-reference/oath-green-wordmark.svg (same seal geometry and letter
 * spacing) but without its black background rect so it sits cleanly on the hero card.
 */
export function OathMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 512 512" className={className} aria-hidden="true">
      <circle cx="256" cy="256" r="196" fill="none" stroke="#A8D86E" strokeWidth="72" />
      <circle cx="256" cy="228" r="38" fill="#A8D86E" />
      <path d="M238 250 L274 250 L290 338 L222 338 Z" fill="#A8D86E" />
    </svg>
  );
}

export function OathWordmark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1400 512" className={className} role="img" aria-label="OATH">
      <circle cx="256" cy="256" r="196" fill="none" stroke="#A8D86E" strokeWidth="72" />
      <circle cx="256" cy="228" r="38" fill="#A8D86E" />
      <path d="M238 250 L274 250 L290 338 L222 338 Z" fill="#A8D86E" />
      <text
        x="520"
        y="338"
        fontFamily="var(--font-space-grotesk), DejaVu Sans, Arial, sans-serif"
        fontWeight="700"
        fontSize="250"
        letterSpacing="28"
        fill="#FFFFFF"
      >
        OATH
      </text>
    </svg>
  );
}
