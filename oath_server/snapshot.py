"""Write the website's fallback stats snapshot from a fresh chain-only index.

    uv run python -m oath_server.snapshot     # -> web/data/stats-snapshot.json

The site shows live /v1/stats when the API is reachable and these last-known real values
when it isn't (e.g. the laptop running the API is off). Every number comes from the chain
rebuild (the same data `python -m oath_core.verify` checks), never from a guess.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path

from oath_core.config import NOTARY_PATH, load_config
from oath_core.keys import load_keypair
from oath_core.solana_rpc import Rpc

from .indexer import build_index

OUT = Path(__file__).resolve().parent.parent / "web" / "data" / "stats-snapshot.json"
API_OUT = OUT.with_name("api-snapshot.json")


class _FixedIndexer:
    def __init__(self, idx):
        self.idx, self.last_error = idx, None

    def get(self):
        return self.idx


def api_snapshot(idx: dict, cfg, notary: str) -> dict:
    """The real API's own responses (same code path), frozen for when the live API is unreachable."""
    from fastapi.testclient import TestClient

    from oath_core.config import LEDGER_PATH
    from oath_core.ledger import Ledger
    from oath_core.policy import load_policy

    from .app import RateLimiter, create_app

    app = create_app(_FixedIndexer(idx), Ledger(LEDGER_PATH), cfg, notary, load_policy,
                     rate_limiter=RateLimiter(limit=10_000))
    c = TestClient(app)
    get = lambda path: c.get(path).raise_for_status().json()  # noqa: E731
    return {
        "generated_at": idx["indexed_at"],
        "source": "snapshot of the OATH API (chain index + ledger decisions), via oath_server.snapshot",
        "health": get("/v1/health"),
        "agent": get("/v1/agent"),
        "stats": get("/v1/stats"),
        "feed": get("/v1/feed?limit=500"),
        "positions": get("/v1/positions?limit=500"),
        "decisions": get("/v1/decisions?limit=500"),
        "verify": get("/v1/verify"),
    }


FEATURE_KEYS = ("seq", "status", "digest", "digest_ok", "salt_hex", "canonical", "thesis", "commit_sig",
                "commit_slot", "commit_time", "open_sig", "swap_sig", "swap_slot", "exit_sig", "exit_slot",
                "exit_reason", "reveal_sig", "reveal_slot", "entry_fill", "exit_fill")


def featured(ag: dict) -> dict | None:
    """The latest fully revealed position, with everything the site needs to show and re-verify it."""
    revealed = [p for p in ag["positions"] if p.get("status") == "revealed" and p.get("canonical")]
    if not revealed:
        return None
    p = max(revealed, key=lambda r: r["seq"])
    g = p.get("grade") or {}
    return {**{k: p.get(k) for k in FEATURE_KEYS},
            "result": {k: g.get(k) for k in ("pnl_usd", "gross_pnl_usd", "fees_usd", "entry_px", "exit_px", "adherence")}}


def snapshot(index: dict, agent: str) -> dict:
    ag = index["agents"].get(agent) or {"stats": {}, "positions": []}
    st = ag["stats"]
    return {
        "as_of": index["indexed_at"],
        "source": "chain (notary memos + on-chain txs), via oath_server.snapshot",
        "notary": index["notary"],
        "verify_pass": index["pass"],
        "revealed": st.get("revealed", 0),
        "committed": st.get("committed", 0),
        "completeness": st.get("completeness"),
        "volume_usd": st.get("volume_usd", "0"),
        "realised_pnl_usd": st.get("realised_pnl_usd", "0"),
        "blocked": st.get("blocked", 0),
        "agent": agent,
        "featured": featured(ag),
        "seqs": [{"seq": p["seq"], "status": p.get("status"), "reveal_sig": p.get("reveal_sig"),
                  "pnl_usd": (p.get("grade") or {}).get("pnl_usd")} for p in ag["positions"]],
    }


def main() -> int:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = load_config()
    notary = str(load_keypair(NOTARY_PATH).pubkey())
    idx = build_index(Rpc(cfg.effective_rpc_url), notary)
    snap = snapshot(idx, cfg.agent_wallet)
    if not snap["verify_pass"]:
        raise SystemExit(f"refusing to publish a snapshot of a record that fails verify: {idx['issues']}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: revealed={snap['revealed']} completeness={snap['completeness']} "
          f"volume=${Decimal(snap['volume_usd']):.2f}")
    API_OUT.write_text(json.dumps(api_snapshot(idx, cfg, notary), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {API_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
