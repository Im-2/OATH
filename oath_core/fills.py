"""Fills from on-chain balance deltas: the only source of truth for fills and P&L (SPEC §5.6).

ClawPump's swap_execute response is NOT a fill (Phase 0: response 8,227,098
lamports vs actual gross 8,226,769). We read the confirmed jsonParsed tx:
  token legs: post - pre token balances where owner == agent and mint == leg mint
  SOL legs:   native lamport delta of the agent (+ fee if it paid) + any wSOL token delta
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import SOL_MINT


class FillError(ValueError):
    """The tx does not prove the expected swap. Callers fail closed."""


@dataclass(frozen=True)
class Fill:
    sig: str
    slot: int
    block_time: int | None
    in_mint: str
    out_mint: str
    in_raw: int        # smallest units of in_mint that left the agent
    out_raw: int       # smallest units of out_mint that reached the agent (gross of tx fee)
    fee_lamports: int  # network fee, paid by the agent if agent_paid_fee
    agent_paid_fee: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _account_keys(tx: dict) -> list[dict]:
    return tx["transaction"]["message"]["accountKeys"]


def signers(tx: dict) -> list[str]:
    return [k["pubkey"] for k in _account_keys(tx) if k.get("signer")]


def _token_delta(meta: dict, owner: str, mint: str) -> int:
    def total(entries):
        return sum(int(b["uiTokenAmount"]["amount"]) for b in entries or []
                   if b.get("owner") == owner and b.get("mint") == mint)
    return total(meta.get("postTokenBalances")) - total(meta.get("preTokenBalances"))


def asset_delta(tx: dict, owner: str, mint: str) -> tuple[int, int, bool]:
    """(delta_raw, fee_lamports, owner_paid_fee). SOL delta is gross of the tx fee."""
    meta = tx["meta"]
    keys = [k["pubkey"] for k in _account_keys(tx)]
    fee = int(meta["fee"])
    paid = bool(keys) and keys[0] == owner
    if mint != SOL_MINT:
        return _token_delta(meta, owner, mint), fee, paid
    if owner not in keys:
        raise FillError("agent account not in transaction")
    i = keys.index(owner)
    native = int(meta["postBalances"][i]) - int(meta["preBalances"][i])
    return native + (fee if paid else 0) + _token_delta(meta, owner, SOL_MINT), fee, paid


def compute_fill(tx: dict | None, sig: str, agent: str, in_mint: str, out_mint: str) -> Fill:
    if not tx:
        raise FillError(f"transaction {sig} not found")
    meta = tx.get("meta") or {}
    if meta.get("err") is not None:
        raise FillError(f"transaction failed on-chain: {meta['err']}")
    if tx["transaction"]["signatures"][0] != sig:
        raise FillError("signature mismatch")
    if agent not in signers(tx):
        raise FillError("agent wallet did not sign the swap")
    d_in, fee, paid = asset_delta(tx, agent, in_mint)
    d_out, _, _ = asset_delta(tx, agent, out_mint)
    if d_in >= 0:
        raise FillError(f"agent did not spend {in_mint} (delta {d_in})")
    if d_out <= 0:
        raise FillError(f"agent did not receive {out_mint} (delta {d_out})")
    return Fill(sig=sig, slot=int(tx["slot"]), block_time=tx.get("blockTime"), in_mint=in_mint,
                out_mint=out_mint, in_raw=-d_in, out_raw=d_out, fee_lamports=fee, agent_paid_fee=paid)
