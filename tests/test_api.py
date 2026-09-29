"""Public API against an index built by the real indexer over a fake chain (fixtures only)."""
import pytest
from fastapi.testclient import TestClient

from oath_core import memo as m
from oath_core.config import Config
from oath_core.ledger import Ledger
from oath_core.policy import Policy
from oath_core.thesis import build_thesis, canonical_json, digest
from oath_server.app import RateLimiter, create_app
from oath_server.indexer import build_index
from test_verify import (AGENT, ENTRY_SLOT, NOTARY, SALT, SOL_MINT, T0, USDC_MINT, FakeRpc, memo_tx,
                         round_trip, sig)

SALT2 = bytes(range(1, 33))


class StubIndexer:
    def __init__(self, idx, err=None):
        self.idx, self.last_error = idx, err

    def get(self):
        return self.idx


def blocked_thesis():
    return build_thesis(agent=AGENT, seq=2, mkt="SOL/USDC", in_mint=USDC_MINT, out_mint=SOL_MINT, size_usd="1.00",
                        entry="121.55", stop="100", tp="127.60", horizon_min=60, conf="0.60", strat="t",
                        why="X: stop too wide", ts="2026-09-27T16:00:00Z")


@pytest.fixture
def world(tmp_path):
    rpc = FakeRpc()
    round_trip(rpc)                                                      # seq 1: commit/open/reveal
    bt = blocked_thesis()
    bdg = digest(canonical_json(bt), SALT2)
    rpc.add(sig(6), memo_tx(sig(6), ENTRY_SLOT + 6000, [m.blocked(AGENT, 2, bdg, "stop_too_wide")]))
    rpc.add(sig(7), memo_tx(sig(7), ENTRY_SLOT + 7000, [m.commit(AGENT, 3, "cd" * 32, 0)]))  # seq 3: committed
    ledger = Ledger(tmp_path / "ledger.db")
    ledger.prepare(AGENT, 1, {"seq": "1"}, "00" * 32, "aa" * 32)
    ledger.prepare(AGENT, 2, bt, SALT2.hex(), bdg)
    ledger.record(2, "blocked", {}, status="blocked")
    ledger.prepare(AGENT, 3, {"seq": "3", "secret": "open thesis"}, "ee" * 32, "cd" * 32)  # must never leak
    ledger.record_decision("stand_aside", "SOL/USDC", "INSUFFICIENT_SIGNALS", "1 of 4 signals", {"agreeing": 1})
    idx = build_index(rpc, NOTARY, now=T0 + 3600)
    cfg = Config(agent_id="x", agent_wallet=AGENT)
    app = create_app(StubIndexer(idx), ledger, cfg, NOTARY, lambda: Policy())
    return TestClient(app), ledger, cfg, idx


def test_health_and_cors(world):
    c, *_ = world
    r = c.get("/v1/health", headers={"Origin": "https://oath.example"})
    assert r.status_code == 200 and r.json()["ok"] and r.json()["notary"] == NOTARY
    assert r.headers["access-control-allow-origin"] == "*"


def test_stats_from_chain_plus_ledger_stand_asides(world):
    c, *_ = world
    s = c.get("/v1/stats").json()
    assert s["committed"] == 2 and s["revealed"] == 1 and s["blocked"] == 1 and s["open"] == 1
    assert s["stand_asides"] == 1 and s["source"]["stats"] == "chain"


def test_revealed_position_has_labelled_amounts(world):
    c, *_ = world
    p = c.get("/v1/positions/1").json()
    assert p["status"] == "revealed" and p["digest_ok"] and p["thesis"]["seq"] == "1"
    assert p["entry"]["received"] == "0.008226769 SOL" and p["exit"]["received"].endswith(" USDC")
    assert p["levels"]["stop"].endswith("USDC per SOL") and p["result"]["pnl_usd"] is not None
    t = c.get("/v1/theses/1").json()
    assert t["digest_ok"] and digest(t["canonical"].encode(), SALT) == t["digest"]


def test_blocked_thesis_served_only_if_it_matches_chain_digest(world):
    c, *_ = world
    p = c.get("/v1/positions/2").json()
    assert p["status"] == "blocked" and p["reason_code"] == "stop_too_wide"
    assert p["digest_matches_chain"] and p["salt_hex"] == SALT2.hex()
    assert digest(canonical_json(p["thesis"]), bytes.fromhex(p["salt_hex"])) == p["digest"]


def test_blocked_thesis_with_tampered_salt_not_served(world, tmp_path):
    _, _, cfg, idx = world
    bad = Ledger(tmp_path / "bad.db")
    bad.prepare(AGENT, 1, {"seq": "1"}, "00" * 32, "aa" * 32)
    bad.prepare(AGENT, 2, blocked_thesis(), "ff" * 32, "bb" * 32)  # wrong salt
    c2 = TestClient(create_app(StubIndexer(idx), bad, cfg, NOTARY, lambda: Policy()))
    p = c2.get("/v1/positions/2").json()
    assert "thesis" not in p and "salt_hex" not in p
    assert c2.get("/v1/theses/2").status_code == 404


def test_open_commitment_leaks_nothing(world):
    c, *_ = world
    p = c.get("/v1/positions/3").json()
    assert p["status"] == "committed" and "thesis" not in p and "salt_hex" not in p
    assert c.get("/v1/theses/3").status_code == 404
    everything = str(c.get("/v1/positions").json()) + str(c.get("/v1/feed").json()) + str(c.get("/v1/verify").json())
    assert "open thesis" not in everything and "ee" * 32 not in everything


def test_positions_listing_filter_and_pagination(world):
    c, *_ = world
    allp = c.get("/v1/positions").json()
    assert allp["total"] == 3 and [i["seq"] for i in allp["items"]] == [3, 2, 1]
    assert [i["seq"] for i in c.get("/v1/positions?status=revealed").json()["items"]] == [1]
    assert [i["seq"] for i in c.get("/v1/positions?limit=1&offset=1").json()["items"]] == [2]
    assert c.get("/v1/positions/99").status_code == 404


def test_feed_merges_chain_events_and_stand_asides(world):
    c, *_ = world
    items = c.get("/v1/feed").json()["items"]
    kinds = {i["kind"] for i in items}
    assert {"commit", "open", "reveal", "blocked", "stand_aside"} <= kinds
    times = [i["block_time"] for i in items]
    assert times == sorted(times, reverse=True)
    sa = next(i for i in items if i["kind"] == "stand_aside")
    assert sa["source"].startswith("ledger")


def test_verify_decisions_agent(world):
    c, *_ = world
    v = c.get("/v1/verify").json()
    assert v["notary"] == NOTARY and "agents" in v
    d = c.get("/v1/decisions").json()["items"][0]
    assert d["reason_code"] == "INSUFFICIENT_SIGNALS" and d["evidence"] == {"agreeing": 1}
    a = c.get("/v1/agent").json()
    assert a["bond"] == {"enabled": False} and a["policy"]["max_trade_usd"] == "2.00"
    assert NOTARY in a["verify_command"]


def test_rate_limit_and_no_index(world):
    _, ledger, cfg, idx = world
    c = TestClient(create_app(StubIndexer(idx), ledger, cfg, NOTARY, lambda: Policy(),
                              rate_limiter=RateLimiter(limit=2, window_s=60)))
    assert [c.get("/v1/health").status_code for _ in range(3)] == [200, 200, 429]
    c2 = TestClient(create_app(StubIndexer(None, "rpc down"), ledger, cfg, NOTARY, lambda: Policy()))
    assert c2.get("/v1/stats").status_code == 503
    assert c2.get("/v1/health").json() == {"ok": False, "notary": NOTARY, "indexed_at": None,
                                           "index_age_s": None, "last_error": "rpc down"}


def test_only_get_allowed(world):
    c, *_ = world
    assert c.post("/v1/stats").status_code == 405


def test_health_reports_monitor_only_from_a_fresh_heartbeat(world, tmp_path):
    import json as _json
    import time as _time
    _, ledger, cfg, idx = world
    hb = tmp_path / "hb.json"
    mk = lambda: TestClient(create_app(StubIndexer(idx), ledger, cfg, NOTARY, lambda: Policy(), heartbeat_path=hb))  # noqa: E731
    assert mk().get("/v1/health").json()["monitor"] == {"online": False, "last_tick_age_s": None}  # no file
    hb.write_text(_json.dumps({"ts": _time.time() - 5}))
    assert mk().get("/v1/health").json()["monitor"]["online"] is True
    hb.write_text(_json.dumps({"ts": _time.time() - 600}))
    assert mk().get("/v1/health").json()["monitor"]["online"] is False  # stale = not running


def test_live_bundles_the_five_reads(world):
    c, *_ = world
    live = c.get("/v1/live").json()
    assert set(live) == {"health", "stats", "feed", "positions", "decisions"}
    assert live["stats"] == c.get("/v1/stats").json()
    assert live["positions"] == c.get("/v1/positions?limit=200").json()
    assert live["feed"] == c.get("/v1/feed?limit=200").json()
    assert live["decisions"] == c.get("/v1/decisions?limit=50").json()
    assert live["health"]["ok"] and live["health"]["notary"] == NOTARY
    assert "ee" * 32 not in str(live)  # open-position salt never leaks through the bundle either
