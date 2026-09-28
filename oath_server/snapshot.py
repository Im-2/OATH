"""Write the website's fallback stats snapshot from a fresh chain-only index.

    uv run python -m oath_server.snapshot     # -> web/data/stats-snapshot.json

The site shows live /v1/stats when the API is reachable and these last-known real values
when it isn't (e.g. the laptop running the API is off). Every number comes from the chain
rebuild (the same data `python -m oath_core.verify` checks), never from a guess.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from decimal import Decimal
from pathlib import Path

from oath_core.config import NOTARY_PATH, load_config
from oath_core.keys import load_keypair
from oath_core.solana_rpc import Rpc

from .indexer import build_index

OUT = Path(__file__).resolve().parent.parent / "web" / "data" / "stats-snapshot.json"


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
