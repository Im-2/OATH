"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";
import * as THREE from "three";

import { CANVAS_H_R, CANVAS_W_R } from "@/lib/globe-geometry";

const FOV_DEG = 50; // globe.gl camera

/** Altitude (in globe radii) at which a sphere fills 2R/H of the vertical field of view. */
function altitudeFor(heightOverRadius: number) {
  const k = 2 / heightOverRadius; // on-screen radius / half-height
  const theta = Math.atan(k * Math.tan((FOV_DEG / 2) * (Math.PI / 180)));
  return 1 / Math.sin(theta) - 1;
}

// Placeholder coordinates for now. Later: pins = recent oaths committed, arcs = commit -> reveal.
const PINS = [
  { lat: 40.7, lng: -74.0 }, // New York
  { lat: 51.5, lng: -0.1 }, // London
  { lat: 6.5, lng: 3.4 }, // Lagos
  { lat: 1.35, lng: 103.8 }, // Singapore
  { lat: 35.7, lng: 139.7 }, // Tokyo
];
const PIN_ALT = 0.1;

type Arc = { startLat: number; startLng: number; endLat: number; endLng: number; color: string[]; alt: number; dash: boolean; t: number };
const ARC_BASE = [
  { startLat: 6.5, startLng: 3.4, endLat: 51.5, endLng: -0.1, c: "#3DFF6E", alt: 0.42, t: 2600 },
  { startLat: 40.7, startLng: -74.0, endLat: 51.5, endLng: -0.1, c: "#CFF5B0", alt: 0.34, t: 3200 },
  { startLat: 1.35, startLng: 103.8, endLat: 35.7, endLng: 139.7, c: "#F2C14E", alt: 0.46, t: 2900 },
  { startLat: 35.7, startLng: 139.7, endLat: 34.0, endLng: -118.2, c: "#3DFF6E", alt: 0.3, t: 3600 },
];
// Each arc = a faint full trail + a bright dash that travels along it.
const ARCS: Arc[] = ARC_BASE.flatMap(({ c, ...geo }) => [
  { ...geo, color: [hexA(c, 0.12), hexA(c, 0.6)], dash: false },
  { ...geo, color: [hexA(c, 0.0), c], dash: true },
]);

function hexA(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// Deterministic per-country brightness so the dotted land has texture instead of a flat fill.
function landColor(feat: object) {
  const s = JSON.stringify((feat as { geometry: { coordinates: unknown } }).geometry.coordinates).length;
  const a = 0.62 + ((s * 9301 + 49297) % 233280) / 233280 * 0.38;
  return `rgba(168,216,110,${a.toFixed(3)})`;
}

export default function GlobeInner({
  width,
  reducedMotion,
  onReady,
}: {
  width: number;
  reducedMotion: boolean;
  onReady?: () => void;
}) {
  const ref = useRef<GlobeMethods | undefined>(undefined);
  const [countries, setCountries] = useState<object[]>([]);
  const R = width / CANVAS_W_R;
  const height = Math.round(R * CANVAS_H_R);
  const altitude = altitudeFor(CANVAS_H_R);

  useEffect(() => {
    let alive = true;
    fetch("/data/countries.geojson")
      .then((r) => r.json())
      .then((g) => alive && setCountries(g.features))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const globeMaterial = useMemo(
    () => new THREE.MeshPhongMaterial({ color: "#0b2a12", emissive: "#03120a", shininess: 10, specular: "#12401c" }),
    [],
  );

  // Configure camera, controls and lighting once the globe exists; re-run on resize.
  useEffect(() => {
    const g = ref.current;
    if (!g) return;
    g.pointOfView({ lat: 24, lng: 12, altitude }, 0);
    const c = g.controls();
    c.autoRotate = true;
    c.autoRotateSpeed = reducedMotion ? 0.12 : 0.6;
    c.enableZoom = false;
    c.enablePan = false;
    c.enableRotate = false;
    // Light from above and slightly behind: the crown catches it, the front/lower face falls
    // into shadow (as in the reference). Weak ambient keeps the dark side just readable.
    const top = new THREE.DirectionalLight(0xffffff, 4.2);
    top.position.set(0.12, 1, 0.3);
    const front = new THREE.DirectionalLight(0xc8ffd0, 1.3);
    front.position.set(0, 0.25, 1);
    g.lights([new THREE.AmbientLight(0xffffff, 0.42), top, front]);
    g.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  }, [altitude, reducedMotion, width, countries.length]);

  return (
    <Globe
      ref={ref}
      width={Math.round(width)}
      height={height}
      backgroundColor="rgba(0,0,0,0)"
      rendererConfig={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      animateIn={false}
      enablePointerInteraction={false}
      globeMaterial={globeMaterial}
      showAtmosphere
      atmosphereColor="#3DFF6E"
      atmosphereAltitude={0.19}
      hexPolygonsData={countries}
      hexPolygonResolution={width > 700 ? 4 : 3}
      hexPolygonMargin={width > 700 ? 0.28 : 0.32}
      hexPolygonUseDots
      hexPolygonAltitude={0.004}
      hexPolygonColor={landColor}
      hexPolygonsTransitionDuration={0}
      pointsData={PINS}
      pointLat="lat"
      pointLng="lng"
      pointAltitude={PIN_ALT}
      pointRadius={0.16}
      pointResolution={8}
      pointColor={() => "#ffffff"}
      pointsMerge={false}
      pointsTransitionDuration={0}
      customLayerData={PINS}
      customThreeObject={() =>
        new THREE.Mesh(new THREE.SphereGeometry(1.55, 16, 16), new THREE.MeshBasicMaterial({ color: "#ffffff" }))
      }
      customThreeObjectUpdate={(obj, d) => {
        const p = d as { lat: number; lng: number };
        const coords = ref.current?.getCoords(p.lat, p.lng, PIN_ALT);
        if (coords) Object.assign((obj as THREE.Object3D).position, coords);
      }}
      arcsData={ARCS}
      arcColor="color"
      arcAltitude="alt"
      arcStroke={(a: object) => ((a as Arc).dash ? 0.7 : 0.38)}
      arcDashLength={(a: object) => ((a as Arc).dash ? 0.28 : 1)}
      arcDashGap={(a: object) => ((a as Arc).dash ? 0.72 : 0)}
      arcDashInitialGap={(a: object) => ((a as Arc).dash ? ((a as Arc).t % 7) / 7 : 0)}
      arcDashAnimateTime={(a: object) => ((a as Arc).dash && !reducedMotion ? (a as Arc).t : 0)}
      arcsTransitionDuration={0}
      onGlobeReady={() => onReady?.()}
    />
  );
}
