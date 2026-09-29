import snapshot from "@/data/stats-snapshot.json";

/** The latest fully revealed oath (seq 2 today), straight from the chain snapshot. */
export const FEATURED = snapshot.featured;
export const NOTARY = snapshot.notary;
export const AGENT = snapshot.agent;

export type Featured = NonNullable<typeof FEATURED>;

export const SOLSCAN_TX = (sig: string) => `https://solscan.io/tx/${sig}`;

export function short(s: string | null | undefined, head = 6, tail = 6) {
  if (!s) return "—";
  return s.length <= head + tail + 1 ? s : `${s.slice(0, head)}…${s.slice(-tail)}`;
}

export function slot(n: number | null | undefined) {
  return typeof n === "number" ? n.toLocaleString("en-US") : "—";
}

/** One implementation of the commitment hash for the whole site (lib/canonical.ts). */
export { oathDigest } from "./canonical";

/** A one-character tamper of the thesis (the stop's last digit), used to show verification failing. */
export function tamper(canonical: string): { text: string; from: string; to: string } {
  const m = canonical.match(/"stop":"([0-9.]+)"/);
  if (!m) return { text: canonical + " ", from: "", to: " " };
  const orig = m[1];
  const last = orig.slice(-1);
  const bumped = orig.slice(0, -1) + (last === "9" ? "8" : String(Number(last) + 1));
  return { text: canonical.replace(`"stop":"${orig}"`, `"stop":"${bumped}"`), from: orig, to: bumped };
}
