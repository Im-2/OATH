"""Deliberately small firewall (SPEC §6). Pure: all inputs are passed in; missing data blocks.

Reason codes are short strings written into the oath1:b blocked memo.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .policy import Policy


@dataclass(frozen=True)
class MarketState:
    """Everything the firewall needs besides the thesis. None = could not be read (fail closed)."""
    quote_price: Decimal | None        # live executable price, in-asset per out-asset
    out_liquidity_usd: Decimal | None  # liquidity of the out-mint
    open_positions: int
    equity_usd: Decimal | None         # current agent equity from chain balances
    peak_equity_usd: Decimal | None    # max equity snapshot on record
    day_start_equity_usd: Decimal | None
    realised_pnl_today_usd: Decimal    # sum over positions closed today (UTC), incl. unrevealed losses


@dataclass(frozen=True)
class Decision:
    approve: bool
    reason: str = "ok"
    detail: str = ""


def _block(reason: str, detail: str) -> Decision:
    return Decision(False, reason, detail)


def evaluate(thesis: dict, mkt_state: MarketState, policy: Policy) -> Decision:
    size = Decimal(thesis["size_usd"])
    entry, stop, tp = (Decimal(thesis[k]) for k in ("entry", "stop", "tp"))

    if thesis["mkt"] not in policy.allowed_markets:
        return _block("market_not_allowed", thesis["mkt"])
    for k in ("in_mint", "out_mint"):
        if thesis[k] not in policy.allowed_mints:
            return _block("mint_not_allowed", thesis[k])
    if size > Decimal(policy.max_trade_usd):
        return _block("size_cap", f"{size} > {policy.max_trade_usd}")
    if int(thesis["horizon_min"]) > policy.max_horizon_min:
        return _block("horizon_cap", f"{thesis['horizon_min']} > {policy.max_horizon_min}")
    if mkt_state.open_positions >= policy.max_open_positions:
        return _block("max_open", f"{mkt_state.open_positions} open >= {policy.max_open_positions}")

    stop_pct = (entry - stop) / entry * 100
    if stop_pct < Decimal(policy.stop_distance_pct_min):
        return _block("stop_too_tight", f"{stop_pct:.2f}% < {policy.stop_distance_pct_min}%")
    if stop_pct > Decimal(policy.stop_distance_pct_max):
        return _block("stop_too_wide", f"{stop_pct:.2f}% > {policy.stop_distance_pct_max}%")

    if mkt_state.quote_price is None or mkt_state.quote_price <= 0:
        return _block("price_unavailable", "no executable quote")
    dev = abs(mkt_state.quote_price - entry) / entry * 100
    if dev > Decimal(policy.max_entry_slippage_pct):
        return _block("entry_slippage", f"quote {mkt_state.quote_price:.6f} is {dev:.2f}% from entry {entry}")
    if not stop < mkt_state.quote_price < tp:
        return _block("price_outside_range", f"quote {mkt_state.quote_price:.6f} not within stop..tp")

    if mkt_state.out_liquidity_usd is None:
        return _block("liquidity_unavailable", "")
    if mkt_state.out_liquidity_usd < Decimal(policy.min_liquidity_usd):
        return _block("low_liquidity", f"{mkt_state.out_liquidity_usd} < {policy.min_liquidity_usd}")

    eq, peak, day0 = mkt_state.equity_usd, mkt_state.peak_equity_usd, mkt_state.day_start_equity_usd
    if eq is None or peak is None or day0 is None or eq <= 0:
        return _block("equity_unavailable", "")
    if peak > 0 and (peak - eq) / peak * 100 >= Decimal(policy.max_drawdown_pct):
        return _block("drawdown_halt", f"equity {eq:.2f} vs peak {peak:.2f}")
    if mkt_state.realised_pnl_today_usd < 0 and day0 > 0 and \
            -mkt_state.realised_pnl_today_usd / day0 * 100 >= Decimal(policy.max_daily_loss_pct):
        return _block("daily_loss", f"{mkt_state.realised_pnl_today_usd:.4f} today on {day0:.2f}")
    if size > eq:
        return _block("insufficient_equity", f"size {size} > equity {eq:.2f}")
    return Decision(True)
