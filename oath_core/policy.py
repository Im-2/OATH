"""Trading policy (SPEC §6): OATH_HOME/policy.json. All limits the firewall enforces live here.

Trade size is configurable: `max_trade_usd`. Edit policy.json (or `python -m oath_core policy
--set max_trade_usd=3.00`); the plugin and monitor re-read it on every decision.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from decimal import Decimal
from pathlib import Path

from .config import OATH_HOME, SOL_MINT, USDC_MINT

POLICY_PATH = OATH_HOME / "policy.json"


@dataclass
class Policy:
    max_trade_usd: str = "2.00"
    max_open_positions: int = 2
    allowed_markets: list[str] = field(default_factory=lambda: ["SOL/USDC"])
    allowed_mints: list[str] = field(default_factory=lambda: [USDC_MINT, SOL_MINT])
    max_daily_loss_pct: str = "5"
    max_drawdown_pct: str = "15"
    max_entry_slippage_pct: str = "1.0"
    min_liquidity_usd: str = "1000000"
    stop_distance_pct_min: str = "1"
    stop_distance_pct_max: str = "10"
    max_horizon_min: int = 360
    reveal_grace_min: int = 30
    swap_slippage_bps: int = 100
    # Each block is an on-chain memo (6,000 lamports); cap them so a looping model can't drain the notary.
    max_blocked_per_hour: int = 5

    def validate(self) -> None:
        for k in ("max_trade_usd", "max_daily_loss_pct", "max_drawdown_pct", "max_entry_slippage_pct",
                  "min_liquidity_usd", "stop_distance_pct_min", "stop_distance_pct_max"):
            v = Decimal(getattr(self, k))
            if not v.is_finite() or v < 0:
                raise ValueError(f"policy.{k} must be a non-negative number")
        if Decimal(self.max_trade_usd) <= 0:
            raise ValueError("policy.max_trade_usd must be > 0")
        if Decimal(self.stop_distance_pct_min) > Decimal(self.stop_distance_pct_max):
            raise ValueError("policy.stop_distance_pct_min > stop_distance_pct_max")
        if self.max_open_positions < 1 or self.max_horizon_min < 1 or not 1 <= self.swap_slippage_bps <= 5000:
            raise ValueError("policy integer limits out of range")

    def public(self) -> dict:
        return asdict(self)


def load_policy(path: Path = POLICY_PATH) -> Policy:
    """Missing file = defaults (and the file is written so the operator can edit it)."""
    if not path.is_file():
        p = Policy()
        save_policy(p, path)
        return p
    raw = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Policy)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"unknown policy keys {sorted(unknown)} in {path}")
    p = Policy(**raw)
    p.validate()
    return p


def save_policy(p: Policy, path: Path = POLICY_PATH) -> None:
    p.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(p), indent=2), encoding="utf-8")


def set_value(p: Policy, key: str, value: str) -> Policy:
    types = {f.name: f.type for f in fields(Policy)}
    if key not in types:
        raise ValueError(f"unknown policy key {key}")
    cur = getattr(p, key)
    if isinstance(cur, bool) or isinstance(cur, list):
        raise ValueError(f"{key} is not settable from the CLI; edit {POLICY_PATH}")
    setattr(p, key, int(value) if isinstance(cur, int) else str(Decimal(value)))
    p.validate()
    return p
