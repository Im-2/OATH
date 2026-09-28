"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { CANVAS_H_R, CANVAS_W_R } from "@/lib/globe-geometry";

// three.js / WebGL: client only (ssr:false must live in a Client Component in Next 16).
const GlobeInner = dynamic(() => import("./GlobeInner"), { ssr: false });

/**
 * The globe stage is 3.4R wide and 1.35R tall. The globe centre sits on the stage's bottom edge,
 * so only the upper hemisphere is visible (cut just under the equator); the lower face fades to
 * black like the reference. Bloom + light dust sit behind the dome's crown.
 */
export function HeroGlobe({ reducedMotion, onReady }: { reducedMotion: boolean; onReady?: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div
      ref={box}
      className="pointer-events-none relative"
      style={{ width: `calc(var(--R) * ${CANVAS_W_R})`, height: "calc(var(--R) * 1.35)" }}
      aria-hidden="true"
    >
      {/* Wide soft bloom behind the crown */}
      <div
        className="absolute left-1/2 -translate-x-1/2"
        style={{
          top: "calc(var(--R) * 0.02)",
          width: "calc(var(--R) * 2.1)",
          height: "calc(var(--R) * 1.05)",
          background:
            "radial-gradient(50% 50% at 50% 50%, rgba(61,255,110,0.30) 0%, rgba(61,255,110,0.12) 38%, rgba(61,255,110,0.04) 62%, transparent 75%)",
          filter: "blur(18px)",
        }}
      />
      {/* Hot core right on the rim */}
      <div
        className="absolute left-1/2 -translate-x-1/2"
        style={{
          top: "calc(var(--R) * 0.19)",
          width: "calc(var(--R) * 1.1)",
          height: "calc(var(--R) * 0.36)",
          background: "radial-gradient(50% 50% at 50% 58%, rgba(214,255,210,0.8) 0%, rgba(120,255,140,0.42) 32%, rgba(61,255,110,0.14) 58%, transparent 74%)",
          filter: "blur(14px)",
        }}
      />
      {/* Light dust rising off the crown (fine dotted texture, masked to a halo) */}
      <div
        className="absolute left-1/2 -translate-x-1/2"
        style={{
          top: "calc(var(--R) * -0.12)",
          width: "calc(var(--R) * 1.5)",
          height: "calc(var(--R) * 0.62)",
          backgroundImage: "radial-gradient(circle, rgba(215,255,205,1) 0.6px, transparent 1.2px)",
          backgroundSize: "5px 5px",
          opacity: 0.85,
          WebkitMaskImage: "radial-gradient(48% 72% at 50% 100%, #000 0%, rgba(0,0,0,0.5) 45%, transparent 78%)",
          maskImage: "radial-gradient(48% 72% at 50% 100%, #000 0%, rgba(0,0,0,0.5) 45%, transparent 78%)",
        }}
      />
      {/* The WebGL globe: canvas centre = stage bottom edge; lower face fades out */}
      <div
        className="absolute left-0"
        style={{
          top: `calc(var(--R) * ${1.35 - CANVAS_H_R / 2})`,
          width: "100%",
          height: `calc(var(--R) * ${CANVAS_H_R})`,
          WebkitMaskImage:
            "linear-gradient(180deg, #000 0%, #000 27%, rgba(0,0,0,0.62) 33%, rgba(0,0,0,0.22) 38%, transparent 42%)",
          maskImage:
            "linear-gradient(180deg, #000 0%, #000 27%, rgba(0,0,0,0.62) 33%, rgba(0,0,0,0.22) 38%, transparent 42%)",
        }}
      >
        {width > 0 && <GlobeInner width={width} reducedMotion={reducedMotion} onReady={onReady} />}
      </div>
    </div>
  );
}
