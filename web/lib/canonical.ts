/**
 * OATH's canonical thesis encoding and commitment hash, byte-for-byte the same as oath_core/thesis.py:
 *   canonical_json = JSON with sorted keys, no whitespace, UTF-8, every value a string,
 *                    decimals as fixed-precision strings (size_usd 2 dp, prices 6 dp, conf 2 dp)
 *   digest         = sha256(canonical_json || salt)   (salt = 32 bytes)
 * Used by /oath/[seq]'s verify button, /try's live hash and /verify's in-browser chain check.
 */

export type Thesis = Record<string, string>;

/** Fixed decimals per numeric field (oath_core.thesis.DECIMALS). */
export const DECIMALS: Record<string, number> = { size_usd: 2, entry: 6, stop: 6, tp: 6, conf: 2 };

/**
 * Decimal(value).quantize(10^-places, ROUND_HALF_EVEN) as a string, or null if not a plain number.
 * Pure string/BigInt arithmetic: no float ever touches a value that gets hashed.
 */
export function fmtDecimal(value: string, places: number): string | null {
  const m = value.trim().match(/^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/);
  if (!m || (!m[2] && !m[3])) return null;
  const neg = m[1] === "-";
  // shift the decimal point by the exponent, as Decimal("1e3") does
  let int = m[2] || "0";
  let frac = m[3] || "";
  const exp = m[4] ? Number(m[4]) : 0;
  if (!Number.isSafeInteger(exp) || Math.abs(exp) > 400) return null;
  if (exp > 0) {
    const f = frac.padEnd(exp, "0");
    int += f.slice(0, exp);
    frac = f.slice(exp);
  } else if (exp < 0) {
    const i = int.padStart(-exp + 1, "0");
    frac = i.slice(i.length + exp) + frac;
    int = i.slice(0, i.length + exp);
  }
  const kept = (frac + "0".repeat(places)).slice(0, places);
  const rest = frac.slice(places);
  let n = BigInt(int + kept);
  if (rest && /[1-9]/.test(rest)) {
    const first = rest.charCodeAt(0) - 48;
    const tail = /[1-9]/.test(rest.slice(1));
    if (first > 5 || (first === 5 && tail) || (first === 5 && !tail && n % BigInt(2) === BigInt(1))) n += BigInt(1);
  }
  let digits = n.toString().padStart(places + 1, "0");
  if (places > 0) digits = `${digits.slice(0, -places)}.${digits.slice(-places)}`;
  // Decimal keeps the sign of a negative that rounds to zero ("-0.00")
  return (neg ? "-" : "") + digits;
}

/** JSON.stringify's string escaping matches Python json.dumps(ensure_ascii=False) for thesis values. */
export function canonicalJson(t: Thesis): string {
  const keys = Object.keys(t).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${JSON.stringify(String(t[k]))}`).join(",")}}`;
}

/** Normalise numeric fields the way build_thesis does (so "123.5" hashes as "123.500000"). */
export function normaliseThesis(t: Thesis): Thesis {
  const out: Thesis = { ...t };
  for (const [k, dp] of Object.entries(DECIMALS)) {
    if (k in out) {
      const v = fmtDecimal(out[k], dp);
      if (v !== null) out[k] = v;
    }
  }
  return out;
}

export function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

/** sha256(utf8(canonical) || salt), hex. */
export async function oathDigest(canonical: string, saltHex: string): Promise<string> {
  const a = new TextEncoder().encode(canonical);
  const b = hexToBytes(saltHex);
  const buf = new Uint8Array(a.length + b.length);
  buf.set(a, 0);
  buf.set(b, a.length);
  const h = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(h), (x) => x.toString(16).padStart(2, "0")).join("");
}

/** Hash a thesis object exactly as OATH commits it. */
export async function thesisDigest(t: Thesis, saltHex: string): Promise<{ canonical: string; digest: string }> {
  const canonical = canonicalJson(t);
  return { canonical, digest: await oathDigest(canonical, saltHex) };
}

/** A revealed thesis must already be in canonical form (parse_canonical). */
export function isCanonical(raw: string): boolean {
  try {
    const t = JSON.parse(raw);
    if (!t || typeof t !== "object" || Array.isArray(t)) return false;
    if (Object.values(t).some((v) => typeof v !== "string")) return false;
    return canonicalJson(t as Thesis) === raw;
  } catch {
    return false;
  }
}
