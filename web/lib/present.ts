/** Labelled amounts (mirrors oath_core/present.py): never show raw lamports / micro-USDC unlabelled. */
const MINTS: Record<string, { sym: string; dec: number }> = {
  So11111111111111111111111111111111111111112: { sym: "SOL", dec: 9 },
  EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v: { sym: "USDC", dec: 6 },
};

export function amount(raw: number | string, mint: string) {
  const m = MINTS[mint];
  if (!m) return `${raw} (raw)`;
  const n = BigInt(String(raw));
  const base = BigInt(10) ** BigInt(m.dec);
  const frac = (n % base).toString().padStart(m.dec, "0");
  return `${n / base}.${frac} ${m.sym}`;
}
