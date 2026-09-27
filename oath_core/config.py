"""Paths, verified constants and operator identity config for OATH.

Secrets (notary keypair, ledger with unrevealed salts) live in OATH_HOME
(default ~/.oath), never in the repo. Identity settings live in
OATH_HOME/config.json (`python -m oath_core init`); trading limits live in
OATH_HOME/policy.json (oath_core.policy).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

OATH_HOME = Path(os.environ.get("OATH_HOME") or Path.home() / ".oath")
NOTARY_PATH = OATH_HOME / "notary.json"
CONFIG_PATH = OATH_HOME / "config.json"
LEDGER_PATH = OATH_HOME / "ledger.db"

# Mints verified against @clawpump/agents WELL_KNOWN_MINTS and on-chain (Phase 0).
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT = "So11111111111111111111111111111111111111112"
MINT_DECIMALS = {USDC_MINT: 6, SOL_MINT: 9}
MINT_SYMBOLS = {USDC_MINT: "USDC", SOL_MINT: "SOL"}

# SPL Memo v2 (verified executable on mainnet, 2026-09-27).
MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

CLAWPUMP_PKG = "@clawpump/agents@0.1.27"  # 0.1.25 ships without dist/
CLAWPUMP_SERVER = "clawpump-stdio"        # Hermes mcp_servers entry the plugin calls via ctx.call_mcp
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"

BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]+$")


def is_pubkey(s: str) -> bool:
    return isinstance(s, str) and 32 <= len(s) <= 44 and bool(BASE58_RE.match(s))


def is_signature(s: str) -> bool:
    return isinstance(s, str) and 86 <= len(s) <= 88 and bool(BASE58_RE.match(s))


@dataclass
class Config:
    agent_id: str
    agent_wallet: str
    rpc_url: str = DEFAULT_RPC_URL

    def validate(self) -> None:
        if not self.agent_id or not is_pubkey(self.agent_wallet):
            raise ValueError("config: agent_id and a valid agent_wallet are required")

    @property
    def effective_rpc_url(self) -> str:
        return os.environ.get("OATH_RPC_URL") or self.rpc_url


# Keys that moved to policy.json in Phase 2; tolerated (ignored) in old config files.
_MOVED_TO_POLICY = {"max_trade_usd", "max_entry_slippage_pct", "max_horizon_min", "reveal_grace_min",
                    "slippage_bps", "allowed_mints", "min_notary_lamports"}


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.is_file():
        raise SystemExit(f"No OATH config at {path}. Run: python -m oath_core init --agent-id ... --agent-wallet ...")
    raw = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Config)}
    unknown = set(raw) - known - _MOVED_TO_POLICY
    if unknown:
        raise ValueError(f"unknown config keys {sorted(unknown)} in {path}")
    cfg = Config(**{k: v for k, v in raw.items() if k in known})
    cfg.validate()
    return cfg


def save_config(cfg: Config, path: Path = CONFIG_PATH) -> None:
    cfg.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


# --- ClawPump key ------------------------------------------------------------

ENV_FILES = [OATH_HOME / ".env", Path(__file__).resolve().parent.parent / ".env", Path.home() / ".hermes" / ".env"]


def _read_env_file(path: Path, name: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() != name:
            continue
        v = v.strip()
        if v[:1] in ('"', "'"):
            v = v[1:].split(v[0], 1)[0]
        else:
            v = re.split(r"\s+#", v, maxsplit=1)[0].strip()  # dotenv inline comment
        return v or None
    return None


def load_clawpump_key() -> str:
    """Return the cpk_ key from env or a gitignored env file. Never logged."""
    key = os.environ.get("CLAWPUMP_API_KEY")
    if not key:
        for f in ENV_FILES:
            key = _read_env_file(f, "CLAWPUMP_API_KEY")
            if key:
                break
    if not key or not key.startswith("cpk_"):
        raise SystemExit("CLAWPUMP_API_KEY not found. Put it in one of: " + ", ".join(map(str, ENV_FILES)))
    return key
