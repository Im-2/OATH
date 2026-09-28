"""oath-server public API (SPEC §8): read-only, CORS open, lightly rate-limited.

    uv run python -m oath_server.app [--host 127.0.0.1] [--port 8787] [--refresh 60]

Sources (every response says which):
  chain   positions, stats, verify, feed events, theses: the chain indexer's rebuild from notary
          memos + on-chain txs alone (the same result `python -m oath_core.verify` prints)
  ledger  stand-aside decisions (off-chain by design), and blocked-thesis salts, which are only
          served after sha256(thesis || salt) is checked against the digest in the on-chain oath1:b memo
Never served: salts or theses of committed/open positions (they only become public at reveal).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from oath_core.config import Config
from oath_core.ledger import Ledger
from oath_core.present import present_fill, present_levels
from oath_core.thesis import ThesisError, canonical_json, digest

ANSEM_MINT = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump"  # user-confirmed 2026-09-27
RATE_LIMIT = 120        # requests
RATE_WINDOW_S = 60.0    # per rolling minute, per client IP
log = logging.getLogger("oath.api")


def _ts(iso: str) -> float:
    return dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()


class RateLimiter:
    def __init__(self, limit: int = RATE_LIMIT, window_s: float = RATE_WINDOW_S):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = now or time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def create_app(indexer, ledger: Ledger, cfg: Config, notary_pubkey: str, load_policy,
               *, token_mint: str | None = None, rate_limiter: RateLimiter | None = None) -> FastAPI:
    app = FastAPI(title="OATH (Proof-of-Thesis) public API", version="1",
                  description="Read-only record of an AI trading agent that commits every thesis on Solana "
                              "before trading and reveals it after. Verify it yourself: "
                              f"python -m oath_core.verify --notary {notary_pubkey}")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
    limiter = rate_limiter or RateLimiter()

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if not limiter.allow(request.client.host if request.client else "unknown"):
            return JSONResponse({"error": "rate limited"}, status_code=429, headers={"Retry-After": "60"})
        return await call_next(request)

    # --- helpers -----------------------------------------------------------------------------

    def index() -> dict:
        idx = indexer.get()
        if idx is None:
            raise HTTPException(503, "index not built yet")
        return idx

    def agent_view(idx: dict) -> dict:
        return idx["agents"].get(cfg.agent_wallet) or {"positions": [], "stats": {}, "gaps": [],
                                                        "uncommitted_trades": [], "disclosed_operator_actions": []}

    def blocked_reveal(seq: int, chain_digest: str) -> dict | None:
        """Blocked theses are public (SPEC §4.3), served only if they hash to the on-chain digest."""
        try:
            pos = ledger.position(seq)
        except Exception:  # noqa: BLE001 - not in this ledger
            return None
        thesis = json.loads(pos["thesis_json"])
        try:
            ok = digest(canonical_json(thesis), bytes.fromhex(pos["salt_hex"])) == chain_digest
        except (ThesisError, ValueError):
            ok = False
        return {"thesis": thesis, "salt_hex": pos["salt_hex"], "digest_matches_chain": ok} if ok else None

    def position_view(row: dict) -> dict:
        v = {k: row.get(k) for k in ("seq", "status", "digest", "digest_ok", "commit_sig", "commit_slot",
                                     "open_sig", "swap_sig", "swap_slot", "exit_sig", "exit_slot", "exit_reason",
                                     "reveal_sig", "reveal_deadline", "blocked_sig", "reason_code", "problems")}
        v = {k: x for k, x in v.items() if x is not None}
        if row.get("thesis"):  # revealed on-chain
            v["thesis"] = row["thesis"]
            v["levels"] = present_levels(row["thesis"])
        if row.get("entry_fill"):
            v["entry"] = present_fill(row["entry_fill"])
        if row.get("exit_fill"):
            v["exit"] = present_fill(row["exit_fill"])
        if row.get("grade"):
            g = row["grade"]
            v["result"] = {k: g.get(k) for k in ("pnl_usd", "gross_pnl_usd", "fees_usd", "r_multiple", "entry_px",
                                                 "exit_px", "qty_match", "adherence", "volume_usd")}
        if row.get("status") == "blocked":
            b = blocked_reveal(row["seq"], row.get("digest", ""))
            if b:
                v.update(thesis=b["thesis"], salt_hex=b["salt_hex"], digest_matches_chain=True)
        v["source"] = "chain"
        return v

    def decision_view(d: dict) -> dict:
        return {"id": d["id"], "ts": d["ts"], "kind": d["kind"], "mkt": d["mkt"], "reason_code": d["reason_code"],
                "why": d["why"], "evidence": d["evidence"], "source": "ledger (off-chain by design)"}

    # --- endpoints ---------------------------------------------------------------------------

    @app.get("/v1/health")
    def health():
        idx = indexer.get()
        age = (time.time() - dt.datetime.fromisoformat(idx["indexed_at"]).timestamp()) if idx else None
        return {"ok": idx is not None, "notary": notary_pubkey, "indexed_at": idx and idx["indexed_at"],
                "index_age_s": round(age, 1) if age is not None else None, "last_error": indexer.last_error}

    @app.get("/v1/agent")
    def agent():
        pol = load_policy().public()
        return {"agent_wallet": cfg.agent_wallet, "notary": notary_pubkey, "token_mint": token_mint,
                "ansem_mint": ANSEM_MINT, "bond": {"enabled": False},
                "policy": {k: pol[k] for k in ("max_trade_usd", "max_open_positions", "allowed_markets",
                                               "max_daily_loss_pct", "max_drawdown_pct", "max_entry_slippage_pct",
                                               "stop_distance_pct_min", "stop_distance_pct_max", "max_horizon_min",
                                               "reveal_grace_min")},
                "verify_command": f"python -m oath_core.verify --notary {notary_pubkey}"}

    @app.get("/v1/stats")
    def stats():
        idx = index()
        ag = agent_view(idx)
        return {**ag["stats"], "verify_pass": idx["pass"], "issues": len(idx["issues"]),
                "sequence_gaps": ag["gaps"], "uncommitted_trades": len(ag["uncommitted_trades"]),
                "disclosed_operator_actions": len(ag.get("disclosed_operator_actions", [])),
                "stand_asides": len(ledger.decisions(limit=1_000_000)),
                "indexed_at": idx["indexed_at"], "source": {"stats": "chain", "stand_asides": "ledger"}}

    @app.get("/v1/positions")
    def positions(status: str | None = None, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        rows = sorted(agent_view(index())["positions"], key=lambda r: r["seq"], reverse=True)
        if status:
            rows = [r for r in rows if r.get("status") == status]
        return {"total": len(rows), "items": [position_view(r) for r in rows[offset:offset + limit]]}

    @app.get("/v1/positions/{seq}")
    def position(seq: int):
        for r in agent_view(index())["positions"]:
            if r["seq"] == seq:
                return position_view(r)
        raise HTTPException(404, f"no seq {seq} on-chain")

    @app.get("/v1/theses/{seq}")
    def thesis(seq: int):
        for r in agent_view(index())["positions"]:
            if r["seq"] != seq:
                continue
            if r.get("thesis"):
                return {"seq": seq, "thesis": r["thesis"],
                        "canonical": canonical_json(r["thesis"]).decode(), "digest": r.get("digest"),
                        "digest_ok": r.get("digest_ok"), "reveal_sig": r.get("reveal_sig"), "source": "chain"}
            if r.get("status") == "blocked":
                b = blocked_reveal(seq, r.get("digest", ""))
                if b:
                    return {"seq": seq, **b, "digest": r.get("digest"), "blocked_sig": r.get("blocked_sig"),
                            "source": "ledger, checked against on-chain digest"}
            raise HTTPException(404, f"seq {seq} is {r.get('status')}: thesis not public until reveal")
        raise HTTPException(404, f"no seq {seq} on-chain")

    @app.get("/v1/verify")
    def verify_report():
        idx = index()
        return {k: idx[k] for k in ("notary", "checked_at", "indexed_at", "pass", "issues",
                                    "notary_txs_with_oath1_memos", "agents")}

    @app.get("/v1/decisions")
    def decisions(limit: int = Query(50, ge=1, le=500)):
        return {"items": [decision_view(d) for d in ledger.decisions(limit=limit)]}

    @app.get("/v1/feed")
    def feed(limit: int = Query(50, ge=1, le=500)):
        items = [{**e, "source": "chain"} for e in index()["events"]]
        for d in ledger.decisions(limit=limit):
            items.append({"kind": "stand_aside", "block_time": _ts(d["ts"]), "ts": d["ts"],
                          "reason_code": d["reason_code"], "why": d["why"], "source": "ledger (off-chain)"})
        items.sort(key=lambda e: e.get("block_time") or 0, reverse=True)
        return {"items": items[:limit]}

    return app


def main(argv=None) -> int:
    import uvicorn

    from oath_core.config import LEDGER_PATH, NOTARY_PATH, load_config
    from oath_core.keys import load_keypair
    from oath_core.policy import load_policy
    from oath_core.solana_rpc import Rpc

    from .indexer import Indexer

    ap = argparse.ArgumentParser(description="OATH public API")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--refresh", type=int, default=60, help="seconds between chain re-index runs")
    ap.add_argument("--token-mint", default=None, help="$OATH mint once launched")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = load_config()
    notary = str(load_keypair(NOTARY_PATH).pubkey())
    ix = Indexer(Rpc(cfg.effective_rpc_url), notary, refresh_s=a.refresh)
    ix.start()
    app = create_app(ix, Ledger(LEDGER_PATH), cfg, notary, load_policy, token_mint=a.token_mint)
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
