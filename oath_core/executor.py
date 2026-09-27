"""Swap execution via ClawPump, gated by one-time exec tokens (SPEC §5.1 step 6–7).

call_mcp bypasses Hermes hooks (Phase 0), so the in-process exec token is what
guarantees no code path reaches swap_execute without a committed seq.
Fills come from the chain (fills.compute_fill), never from ClawPump's response.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from decimal import Decimal

from .clawpump import ClawPump, ClawPumpError
from .config import MINT_DECIMALS, Config, is_signature
from .fills import Fill, compute_fill
from .solana_rpc import Rpc

TOKEN_TTL_S = 60.0


class ExecTokenError(PermissionError):
    pass


class ExecTokens:
    """Single-use tokens bound to a seq, valid for TOKEN_TTL_S."""

    def __init__(self, ttl_s: float = TOKEN_TTL_S, clock=time.monotonic):
        self._ttl = ttl_s
        self._clock = clock
        self._live: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def issue(self, seq: int) -> str:
        tok = secrets.token_hex(16)
        with self._lock:
            self._live[tok] = (seq, self._clock() + self._ttl)
        return tok

    def consume(self, tok: str, seq: int) -> None:
        with self._lock:
            entry = self._live.pop(tok, None)  # pop first: a token is spent even if invalid
        if entry is None:
            raise ExecTokenError("unknown or already-used exec token")
        bound_seq, expiry = entry
        if bound_seq != seq:
            raise ExecTokenError(f"exec token bound to seq {bound_seq}, not {seq}")
        if self._clock() > expiry:
            raise ExecTokenError("exec token expired")


@dataclass(frozen=True)
class Quote:
    in_raw: int
    out_raw: int
    price: Decimal  # in-asset units per out-asset unit (e.g. USDC per SOL)
    raw: dict


def to_units(raw: int, mint: str) -> Decimal:
    return Decimal(raw).scaleb(-MINT_DECIMALS[mint])


def quote(cp: ClawPump, cfg: Config, in_mint: str, out_mint: str, in_raw: int, slippage_bps: int) -> Quote:
    q = cp.call("swap_quote", {"agent_id": cfg.agent_id, "input_mint": in_mint, "output_mint": out_mint,
                               "amount": str(in_raw), "slippage_bps": slippage_bps})
    try:
        qi, qo = int(q["input"]["rawAmount"]), int(q["output"]["rawAmount"])
        ok = q["status"] == "quoted" and q["input"]["mint"] == in_mint and q["output"]["mint"] == out_mint
    except (KeyError, TypeError, ValueError) as e:
        raise ClawPumpError(f"unreadable quote: {q!r:.300}") from e
    if not ok or qi != in_raw or qo <= 0:
        raise ClawPumpError(f"quote does not match request: {q!r:.300}")
    return Quote(qi, qo, to_units(qi, in_mint) / to_units(qo, out_mint), q)


def assert_agent_wallet(cp: ClawPump, cfg: Config) -> None:
    a = cp.call("get_agent", {"agent_id": cfg.agent_id})
    wallet = a.get("wallet_address") or a.get("wallet") if isinstance(a, dict) else None
    if wallet != cfg.agent_wallet:
        raise ClawPumpError(f"agent {cfg.agent_id} wallet is {wallet!r}, expected {cfg.agent_wallet}")


@dataclass(frozen=True)
class SwapResult:
    fill: Fill
    response: dict  # ClawPump's response, kept for reference only (not a fill)


def swap(cp: ClawPump, rpc: Rpc, cfg: Config, tokens: ExecTokens, token: str, seq: int,
         in_mint: str, out_mint: str, in_raw: int, *, slippage_bps: int, allowed_mints: list[str]) -> SwapResult:
    tokens.consume(token, seq)
    for m in (in_mint, out_mint):
        if m not in allowed_mints:
            raise ClawPumpError(f"mint {m} not allowed")
    assert_agent_wallet(cp, cfg)
    resp = cp.call("swap_execute", {"agent_id": cfg.agent_id, "input_mint": in_mint, "output_mint": out_mint,
                                    "amount": str(in_raw), "slippage_bps": slippage_bps})
    sig = resp.get("txHash") if isinstance(resp, dict) else None
    if not is_signature(sig or "") or resp.get("status") != "executed":
        raise ClawPumpError(f"swap_execute returned no executed txHash: {resp!r:.300}")
    fill = compute_fill(rpc.wait_transaction(sig), sig, cfg.agent_wallet, in_mint, out_mint)
    return SwapResult(fill, resp)
