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

function hexToBytes(hex: string) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

/** sha256(canonical_thesis_utf8 || salt_bytes), hex: exactly what the notary committed on-chain. */
export async function oathDigest(canonical: string, saltHex: string): Promise<string> {
  const a = new TextEncoder().encode(canonical);
  const b = hexToBytes(saltHex);
  const buf = new Uint8Array(a.length + b.length);
  buf.set(a, 0);
  buf.set(b, a.length);
  const h = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(h), (x) => x.toString(16).padStart(2, "0")).join("");
}

/** A one-character tamper of the thesis (the stop's last digit), used to show verification failing. */
export function tamper(canonical: string): { text: string; from: string; to: string } {
  const m = canonical.match(/"stop":"([0-9.]+)"/);
  if (!m) return { text: canonical + " ", from: "", to: " " };
  const orig = m[1];
  const last = orig.slice(-1);
  const bumped = orig.slice(0, -1) + (last === "9" ? "8" : String(Number(last) + 1));
  return { text: canonical.replace(`"stop":"${orig}"`, `"stop":"${bumped}"`), from: orig, to: bumped };
}
