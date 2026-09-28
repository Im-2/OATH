"""Human-readable amounts for model-facing results.

Raw on-chain integers (lamports, micro-USDC) must never reach the model unlabelled: in the
Phase 2 acceptance test the model reported 8,113,454 lamports as "8.113454 SOL". Every amount
here carries its unit, and raw values keep unit-bearing key names.
"""
from __future__ import annotations

from decimal import Decimal

from .config import MINT_DECIMALS, MINT_SYMBOLS, SOL_MINT

PRICE_Q = Decimal("0.000001")


def amount(raw: int, mint: str) -> str:
    """'0.008113454 SOL' / '1.000000 USDC': full precision, fixed decimals, with the symbol."""
    d = MINT_DECIMALS[mint]
    return f"{Decimal(raw).scaleb(-d):.{d}f} {MINT_SYMBOLS[mint]}"


def _raw_key(mint: str) -> str:
    return {"SOL": "sol_lamports", "USDC": "usdc_micro"}[MINT_SYMBOLS[mint]]


def present_fill(fill: dict) -> dict:
    """On-chain fill -> labelled amounts + one-line summary. Raw integers only under unit-named keys."""
    in_m, out_m = fill["in_mint"], fill["out_mint"]
    spent, got = amount(fill["in_raw"], in_m), amount(fill["out_raw"], out_m)
    # Price quoted as USDC per SOL regardless of direction.
    usdc_raw, sol_raw = (fill["in_raw"], fill["out_raw"]) if MINT_SYMBOLS[in_m] == "USDC" else (fill["out_raw"], fill["in_raw"])
    price = (Decimal(usdc_raw).scaleb(-6) / Decimal(sol_raw).scaleb(-9)).quantize(PRICE_Q)
    fee = amount(fill["fee_lamports"], SOL_MINT)
    return {
        "summary": f"Spent {spent}, received {got} at {price} USDC per SOL (network fee {fee}).",
        "spent": spent,
        "received": got,
        "fill_price": f"{price} USDC per SOL",
        "network_fee": fee,
        "tx": fill["sig"],
        "slot": fill["slot"],
        "raw_smallest_units": {f"spent_{_raw_key(in_m)}": fill["in_raw"],
                               f"received_{_raw_key(out_m)}": fill["out_raw"],
                               "fee_lamports": fill["fee_lamports"]},
    }


def present_levels(thesis: dict) -> dict:
    return {k: f"{thesis[k]} USDC per SOL" for k in ("entry", "stop", "tp")} | {
        "size": f"{thesis['size_usd']} USDC", "horizon": f"{thesis['horizon_min']} minutes"}


def present_open_result(res: dict) -> dict:
    """Model-facing view of open_position's result."""
    out = dict(res)
    if "fill" in out and isinstance(out["fill"], dict):
        out["fill"] = present_fill(out["fill"])
    if "thesis" in out and isinstance(out["thesis"], dict):
        out["levels"] = present_levels(out["thesis"])
    if out.get("quote_price") not in (None, "None"):
        out["quote_price"] = f"{Decimal(out['quote_price']).quantize(PRICE_Q)} USDC per SOL"
    return out
