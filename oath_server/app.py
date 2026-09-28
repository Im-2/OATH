"""oath-server public API (SPEC §8): read-only record (GET), CORS open, lightly rate-limited, plus the
thesis-only Ask OATH sandbox (POST /v1/sandbox, oath_server.sandbox), which cannot trade or write.

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
from pydantic import BaseModel, Field

from oath_core.config import Config
from oath_core.ledger import Ledger
from oath_core.present import present_fill, present_levels
from oath_core.thesis import ThesisError, canonical_json, digest

ANSEM_MINT = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump"  # user-confirmed 2026-09-27
RATE_LIMIT = 120        # requests
RATE_WINDOW_S = 60.0    # per rolling minute, per client IP
SANDBOX_PER_IP = (3, 600.0)       # Ask OATH: 3 questions per 10 minutes per IP
SANDBOX_GLOBAL = (40, 3600.0)     # and 40 per hour overall, to stay inside the free model's quota
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


class SandboxIn(BaseModel):
    idea: str = Field(..., min_length=1, max_length=2000)


MONITOR_STALE_S = 90  # monitor ticks every 20s; 90s without a heartbeat = not running


def monitor_status(path) -> dict:
    """From the heartbeat the monitor writes each tick (oath_server.monitor.write_heartbeat)."""
    try:
        hb = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - float(hb["ts"])
        return {"online": age < MONITOR_STALE_S, "last_tick_age_s": round(age, 1)}
    except (OSError, ValueError, KeyError, TypeError):
        return {"online": False, "last_tick_age_s": None}


def create_app(indexer, ledger: Ledger, cfg: Config, notary_pubkey: str, load_policy,
               *, token_mint: str | None = None, rate_limiter: RateLimiter | None = None,
               heartbeat_path=None, sandbox=None, sandbox_limits=(SANDBOX_PER_IP, SANDBOX_GLOBAL)) -> FastAPI:
    """`sandbox`: optional callable(idea) -> dict (oath_server.sandbox.make_runner). It is the only
    non-GET route, and it can only evaluate; it has no path to the notary, executor or ledger writes."""
    app = FastAPI(title="OATH (Proof-of-Thesis) public API", version="1",
                  description="Read-only record of an AI trading agent that commits every thesis on Solana "
                              "before trading and reveals it after. Verify it yourself: "
                              f"python -m oath_core.verify --notary {notary_pubkey}")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
    limiter = rate_limiter or RateLimiter()
    sb_ip, sb_all = RateLimiter(*sandbox_limits[0]), RateLimiter(*sandbox_limits[1])

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
        v = {k: row.get(k) for k in ("seq", "status", "digest", "digest_ok", "commit_sig", "commit_slot", "commit_time",
                                     "open_sig", "open_time", "swap_sig", "swap_slot", "swap_time", "exit_sig",
                                     "exit_slot", "exit_reason", "reveal_sig", "reveal_slot", "reveal_time",
                                     "reveal_deadline", "blocked_sig", "reason_code", "problems")}
        v = {k: x for k, x in v.items() if x is not None}
        if row.get("thesis"):  # revealed on-chain: thesis, salt and canonical bytes are public
            v["thesis"] = row["thesis"]
            v["levels"] = present_levels(row["thesis"])
            v["canonical"] = row.get("canonical")
            v["salt_hex"] = row.get("salt_hex")
        if row.get("entry_fill"):
            v["entry"] = {**present_fill(row["entry_fill"]), "block_time": row["entry_fill"].get("block_time")}
        if row.get("exit_fill"):
            v["exit"] = {**present_fill(row["exit_fill"]), "block_time": row["exit_fill"].get("block_time")}
        if row.get("grade"):
            g = row["grade"]
            v["result"] = {k: g.get(k) for k in ("pnl_usd", "gross_pnl_usd", "fees_usd", "r_multiple", "entry_px",
                                                 "exit_px", "qty_match", "size_ok", "adherence", "volume_usd")}
        if row.get("status") == "blocked":
            b = blocked_reveal(row["seq"], row.get("digest", ""))
            if b:
                v.update(thesis=b["thesis"], salt_hex=b["salt_hex"], digest_matches_chain=True)
        v["source"] = "chain"
        return v

    def decision_view(d: dict) -> dict:
        return {"id": d["id"], "ts": d["ts"], "kind": d["kind"], "mkt": d["mkt"], "reason_code": d["reason_code"],
                "why": d["why"], "evidence": d["evidence"], "backfilled": bool(d["evidence"].get("backfilled")),
                "source": "ledger (off-chain by design)"}

    # --- endpoints ---------------------------------------------------------------------------

    @app.get("/v1/health")
    def health():
        idx = indexer.get()
        age = (time.time() - dt.datetime.fromisoformat(idx["indexed_at"]).timestamp()) if idx else None
        out = {"ok": idx is not None, "notary": notary_pubkey, "indexed_at": idx and idx["indexed_at"],
               "index_age_s": round(age, 1) if age is not None else None, "last_error": indexer.last_error}
        if heartbeat_path is not None:
            out["monitor"] = monitor_status(heartbeat_path)
        return out

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
            items.append({"kind": "stand_aside", "id": d["id"], "block_time": _ts(d["ts"]), "ts": d["ts"],
                          "reason_code": d["reason_code"], "why": d["why"], "evidence": d["evidence"],
                          "backfilled": bool(d["evidence"].get("backfilled")), "source": "ledger (off-chain)"})
        items.sort(key=lambda e: e.get("block_time") or 0, reverse=True)
        return {"items": items[:limit]}

    resting = {"error": "resting", "message": "OATH is resting. Try Break it instead."}

    @app.post("/v1/sandbox")
    def ask_sandbox(body: SandboxIn, request: Request):
        from .sandbox import SandboxBadIdea, SandboxRefused, SandboxResting

        if sandbox is None:
            return JSONResponse(resting, status_code=503)
        ip = request.client.host if request.client else "unknown"
        if not sb_ip.allow(ip):
            return JSONResponse({"error": "rate_limited", "message": "3 questions per 10 minutes. Try Break it meanwhile."},
                                status_code=429, headers={"Retry-After": "600"})
        if not sb_all.allow("all"):
            return JSONResponse({**resting, "detail": "hourly sandbox budget used"}, status_code=503)
        try:
            return sandbox(body.idea)
        except SandboxBadIdea as e:
            raise HTTPException(422, str(e)) from e
        except SandboxRefused:
            log.warning("sandbox refused an out-of-box call")
            return JSONResponse(resting, status_code=503)
        except SandboxResting as e:
            return JSONResponse({**resting, "detail": str(e)}, status_code=503)
        except Exception:  # noqa: BLE001 - never leak internals to visitors
            log.exception("sandbox failed")
            return JSONResponse(resting, status_code=503)

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
    ap.add_argument("--no-sandbox", action="store_true", help="disable POST /v1/sandbox (Ask OATH)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = load_config()
    notary = str(load_keypair(NOTARY_PATH).pubkey())
    ix = Indexer(Rpc(cfg.effective_rpc_url), notary, refresh_s=a.refresh)
    ix.start()
    from oath_core.config import OATH_HOME

    from .sandbox import make_runner

    sandbox = None if a.no_sandbox else make_runner(cfg, LEDGER_PATH, cfg.effective_rpc_url, load_policy)
    app = create_app(ix, Ledger(LEDGER_PATH), cfg, notary, load_policy, token_mint=a.token_mint,
                     heartbeat_path=OATH_HOME / "monitor_heartbeat.json", sandbox=sandbox)
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
