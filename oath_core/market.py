"""Prices, liquidity and agent equity. Chain balances are truth; prices come from ClawPump
get_price with Jupiter Price API v3 as fallback (shape verified live 2026-09-27)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

import httpx

from .clawpump import ClawPump, ClawPumpError
from .config import USDC_MINT
from .ledger import Ledger
from .solana_rpc import Rpc

JUP_PRICE_URL = "https://lite-api.jup.ag/price/v3"


@dataclass(frozen=True)
class PriceInfo:
    usd: Decimal
    liquidity_usd: Decimal | None
    source: str


def _jupiter(mint: str) -> PriceInfo | None:
    try:
        r = httpx.get(JUP_PRICE_URL, params={"ids": mint}, timeout=15)
        r.raise_for_status()
        p = r.json().get(mint)
        if p and Decimal(str(p["usdPrice"])) > 0:
            liq = p.get("liquidity")
            return PriceInfo(Decimal(str(p["usdPrice"])), Decimal(str(liq)) if liq is not None else None, "jupiter")
    except (httpx.HTTPError, KeyError, TypeError, ValueError, ArithmeticError):
        pass
    return None


def price_info(cp: ClawPump, mint: str) -> PriceInfo | None:
    """USD price + liquidity for one mint, or None if no source answers sanely.

    ClawPump's get_price answers from different providers over time; its CoinGecko path
    (seen live 2026-09-27) carries no liquidity, so liquidity is filled from Jupiter then.
    """
    cp_info = None
    try:
        data = cp.call("get_price", {"tokens": mint})
        p = (data.get("prices") or {}).get(mint) if isinstance(data, dict) else None
        if p and Decimal(str(p["usd"])) > 0:
            liq = p.get("liquidity")
            cp_info = PriceInfo(Decimal(str(p["usd"])), Decimal(str(liq)) if liq is not None else None,
                                f"clawpump:{p.get('source', '?')}")
    except (ClawPumpError, KeyError, TypeError, ValueError, ArithmeticError):
        cp_info = None
    if cp_info is not None and cp_info.liquidity_usd is not None:
        return cp_info
    jup = _jupiter(mint)
    if cp_info is None:
        return jup
    if jup is not None and jup.liquidity_usd is not None:
        return PriceInfo(cp_info.usd, jup.liquidity_usd, f"{cp_info.source}+jupiter-liquidity")
    return cp_info  # price known, liquidity unknown -> the firewall blocks (fail closed)


def agent_balances(rpc: Rpc, wallet: str) -> tuple[int, int]:
    """(lamports, usdc_raw) straight from chain."""
    lamports = rpc.get_balance(wallet)
    accts = rpc.call("getTokenAccountsByOwner", [wallet, {"mint": USDC_MINT},
                                                 {"encoding": "jsonParsed", "commitment": "confirmed"}])["value"]
    usdc = sum(int(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]) for a in accts)
    return lamports, usdc


def equity_usd(rpc: Rpc, wallet: str, sol_usd: Decimal) -> Decimal:
    lamports, usdc = agent_balances(rpc, wallet)
    return Decimal(usdc).scaleb(-6) + Decimal(lamports).scaleb(-9) * sol_usd


def snapshot_equity(ledger: Ledger, rpc: Rpc, wallet: str, sol_usd: Decimal, source: str) -> Decimal:
    eq = equity_usd(rpc, wallet, sol_usd)
    ledger.snapshot_equity(eq, source)
    return eq


def realised_pnl_today(ledger: Ledger, today: dt.date | None = None) -> Decimal:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    total = Decimal(0)
    for p in ledger.positions():
        if p["pnl_usd"] and p["closed_at"] and p["closed_at"][:10] == today.isoformat():
            total += Decimal(p["pnl_usd"])
    return total

