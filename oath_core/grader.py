"""Grading from on-chain fills only (SPEC §5.4, §5.6).

v1 positions are USDC -> X -> USDC. Realised P&L (USD):
  pnl = exit USDC received - entry USDC spent - network fees paid by the agent
fees are lamports converted at the exit fill's SOL price (SOL legs) - the only
price we have that the chain itself proves.
"""
from __future__ import annotations

from decimal import Decimal

from .config import MINT_DECIMALS, SOL_MINT, USDC_MINT

Q6 = Decimal("0.000001")

# Adherence tolerances: did the exit honour what was committed?
TP_TOLERANCE = Decimal("0.02")           # a 'tp' exit must fill >= tp * (1 - 2%)
STOP_TOLERANCE = Decimal("0.02")         # a 'stop' exit must fill <= stop * (1 + 2%) ...
STOP_BREACH_TOLERANCE = Decimal("0.05")  # ... and not below stop * (1 - 5%) (stop breached = slashable)
EXPIRY_EARLY_S = 120                     # an 'expiry' exit may not land more than 2 min before the horizon


def adherence(thesis: dict, entry: dict, exit_: dict, exit_reason: str, exit_px: Decimal) -> dict:
    """Checks the exit against the committed thesis. `manual` exits have nothing to check."""
    stop, tp = Decimal(thesis["stop"]), Decimal(thesis["tp"])
    checks: dict[str, bool] = {}
    if exit_reason == "tp":
        checks["tp_honoured"] = exit_px >= tp * (1 - TP_TOLERANCE)
    elif exit_reason == "stop":
        checks["stop_honoured"] = exit_px <= stop * (1 + STOP_TOLERANCE)
        checks["stop_not_breached"] = exit_px >= stop * (1 - STOP_BREACH_TOLERANCE)
    elif exit_reason == "expiry":
        t0, t1 = entry.get("block_time"), exit_.get("block_time")
        checks["expiry_honoured"] = (t0 is not None and t1 is not None and
                                     t1 >= t0 + int(thesis["horizon_min"]) * 60 - EXPIRY_EARLY_S)
    return {"ok": all(checks.values()), "checks": checks}


def units(raw: int, mint: str) -> Decimal:
    return Decimal(raw).scaleb(-MINT_DECIMALS[mint])


def grade_trade(thesis: dict, entry: dict, exit_: dict | None, exit_reason: str) -> dict:
    """entry/exit_ are Fill dicts. Returns per-trade metrics; exit_ None = exec_failed/no exit."""
    in_mint, out_mint = thesis["in_mint"], thesis["out_mint"]
    if in_mint != USDC_MINT:
        raise ValueError("v1 grading assumes USDC-quoted positions")
    committed_size = Decimal(thesis["size_usd"])
    entry_usdc = units(entry["in_raw"], USDC_MINT)
    qty = units(entry["out_raw"], out_mint)
    entry_px = entry_usdc / qty
    out = {
        "seq": int(thesis["seq"]),
        "entry_usdc": str(entry_usdc), "qty": str(qty), "entry_px": str(entry_px.quantize(Q6)),
        "committed_entry": thesis["entry"], "committed_stop": thesis["stop"], "committed_tp": thesis["tp"],
        "size_ok": entry_usdc <= committed_size * Decimal("1.01"),
        "exit_reason": exit_reason,
    }
    if exit_ is None:
        return {**out, "closed": False}
    exit_usdc = units(exit_["out_raw"], USDC_MINT)
    sold = units(exit_["in_raw"], out_mint)
    exit_px = exit_usdc / sold
    fees_lamports = (entry["fee_lamports"] if entry["agent_paid_fee"] else 0) + \
                    (exit_["fee_lamports"] if exit_["agent_paid_fee"] else 0)
    sol_px = exit_px if out_mint == SOL_MINT else None
    fees_usd = units(fees_lamports, SOL_MINT) * sol_px if sol_px is not None else None
    gross = exit_usdc - entry_usdc
    pnl = gross - (fees_usd or Decimal(0))
    risk = (Decimal(thesis["entry"]) - Decimal(thesis["stop"])) * qty
    return {
        **out, "closed": True,
        "exit_usdc": str(exit_usdc), "sold_qty": str(sold), "exit_px": str(exit_px.quantize(Q6)),
        "qty_match": sold == qty,
        "fees_lamports": fees_lamports,
        "fees_usd": str(fees_usd.quantize(Q6)) if fees_usd is not None else None,
        "gross_pnl_usd": str(gross.quantize(Q6)),
        "pnl_usd": str(pnl.quantize(Q6)),
        "r_multiple": str((pnl / risk).quantize(Decimal("0.01"))) if risk > 0 else None,
        "volume_usd": str((entry_usdc + exit_usdc).quantize(Q6)),
        "adherence": adherence(thesis, entry, exit_, exit_reason, exit_px),
    }


def aggregate(trades: list[dict], *, committed: int, open_count: int, unrevealed: list[dict],
              blocked_reasons: list[str] | None = None) -> dict:
    """Stats over graded trades. Unrevealed commitments count as a full loss of committed size."""
    closed = [t for t in trades if t.get("closed")]
    pnl = sum((Decimal(t["pnl_usd"]) for t in closed), Decimal(0))
    unrevealed_loss = sum((Decimal(u["size_usd"]) for u in unrevealed), Decimal(0))
    wins = sum(1 for t in closed if Decimal(t["pnl_usd"]) > 0)
    denom = committed - open_count
    return {
        "committed": committed,
        "open": open_count,
        "closed": len(closed),
        "revealed": len(trades),
        "unrevealed": len(unrevealed),
        "completeness": str(Decimal(len(trades)) / denom) if denom > 0 else None,
        "realised_pnl_usd": str((pnl - unrevealed_loss).quantize(Q6)),
        "win_rate": str(Decimal(wins) / len(closed)) if closed else None,
        "volume_usd": str(sum((Decimal(t["volume_usd"]) for t in closed), Decimal(0)).quantize(Q6)),
        "blocked": len(blocked_reasons or []),
        "blocked_by_reason": {r: (blocked_reasons or []).count(r) for r in sorted(set(blocked_reasons or []))},
        "adherence_violations": sum(1 for t in closed if not (t.get("adherence") or {"ok": True})["ok"]),
    }
