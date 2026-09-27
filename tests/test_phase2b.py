"""Stand-aside records, operator test mode, and read-tool argument repair."""
import datetime as dt
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from fakes import OPEN_ARGS, make_ctx
from oath_core import guard, testmode
from oath_core.flow import FlowError, open_position
from oath_core.ledger import Ledger
from oath_core.policy import Policy

PLUGIN = Path(__file__).resolve().parent.parent / "plugin" / "oath" / "__init__.py"
SOL_MINT = "So11111111111111111111111111111111111111112"
TEST_ARGS = dict(OPEN_ARGS, strat="acceptance_test", why="OPERATOR_TEST: acceptance test, 1/4 signals")


def load_plugin():
    spec = importlib.util.spec_from_file_location("oath_plugin_b", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- intelligence_market argument repair ---------------------------------------------------

@pytest.mark.parametrize("token", ["SOL", "sol", "$SOL", " SOL ", "WSOL"])
def test_intelligence_market_symbol_rewritten_to_mint(token):
    d = guard.decide("mcp__clawpump_stdio__intelligence_market", {"token": token})
    assert d == {"action": "modify", "args": {"token": SOL_MINT}}


def test_intelligence_market_mint_untouched_and_other_reads_untouched():
    assert guard.decide("mcp__clawpump_stdio__intelligence_market", {"token": SOL_MINT}) is None
    assert guard.decide("mcp__clawpump_stdio__get_price", {"tokens": "SOL"}) is None


# --- operator test mode -------------------------------------------------------------------

def test_testmode_arm_consume_once_and_expire(tmp_path):
    p = tmp_path / "tm.json"
    assert testmode.status(p) == {"armed": False}
    with pytest.raises(testmode.TestModeError):
        testmode.consume(p)
    testmode.arm(30, p)
    assert testmode.status(p)["armed"]
    testmode.consume(p)
    assert not testmode.status(p)["armed"]
    with pytest.raises(testmode.TestModeError):
        testmode.consume(p)
    testmode.arm(1, p)
    s = json.loads(p.read_text())
    s["expires_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)).isoformat()
    p.write_text(json.dumps(s))
    assert not testmode.status(p)["armed"]
    with pytest.raises(ValueError):
        testmode.arm(0, p)


def test_acceptance_test_refused_unless_operator_armed(tmp_path):
    ctx = make_ctx(tmp_path)
    with pytest.raises(FlowError, match="not armed"):
        open_position(ctx, **TEST_ARGS)
    assert ctx.notary.posted == [] and ctx.ledger.positions() == []


def test_armed_acceptance_test_goes_through_full_pipeline_once(tmp_path):
    ctx = make_ctx(tmp_path)
    testmode.arm(30, ctx.testmode_path)
    res = open_position(ctx, **TEST_ARGS)
    assert res["ok"] and res["thesis"]["strat"] == "acceptance_test"   # labelled honestly on-chain
    assert ctx.notary.kinds() == ["c", "o"]                            # commit before swap, as normal
    assert not testmode.status(ctx.testmode_path)["armed"]             # one-shot
    with pytest.raises(FlowError, match="not armed"):
        open_position(ctx, **TEST_ARGS)


def test_acceptance_test_still_subject_to_firewall_and_block_keeps_token(tmp_path):
    ctx = make_ctx(tmp_path, policy=Policy(max_trade_usd="0.50"))
    testmode.arm(30, ctx.testmode_path)
    res = open_position(ctx, **TEST_ARGS)
    assert res["blocked"] and res["firewall"]["reason"] == "size_cap"
    assert testmode.status(ctx.testmode_path)["armed"]  # not consumed by a block


# --- stand-aside records ------------------------------------------------------------------

def test_stand_aside_recorded_off_chain_and_shown_in_status(tmp_path, monkeypatch):
    mod = load_plugin()
    ledger = Ledger(tmp_path / "ledger.db")
    monkeypatch.setattr(testmode, "TESTMODE_PATH", tmp_path / "tm.json")
    res = mod.record_stand_aside(ledger, {"reason_code": "insufficient_signals",
                                          "why": "1 of 4 signals agree; need 2",
                                          "evidence": {"sol_24h_pct": 1.6, "sentiment": "neutral", "agreeing": 1}},
                                 session_id="s1")
    assert res["ok"] and res["on_chain"] is False
    d = ledger.decisions()[0]
    assert d["reason_code"] == "INSUFFICIENT_SIGNALS" and d["evidence"]["agreeing"] == 1 and d["session_id"] == "s1"
    st = mod.status_summary(ledger)
    assert st["totals"]["stand_asides"] == 1 and st["recent_stand_asides"][0]["why"].startswith("1 of 4")
    assert st["test_mode"] == {"armed": False}
    assert ledger.positions() == []  # no seq consumed


@pytest.mark.parametrize("params", [{"reason_code": "bad code!", "why": "x"}, {"reason_code": "OK", "why": ""},
                                    {"reason_code": "OK", "why": "x" * 281},
                                    {"reason_code": "OK", "why": "x", "mkt": "BTC/USDC"}])
def test_stand_aside_validation(tmp_path, params):
    mod = load_plugin()
    ledger = Ledger(tmp_path / "ledger.db")
    assert mod.record_stand_aside(ledger, params)["ok"] is False
    assert ledger.decisions() == []


def test_stand_aside_evidence_is_bounded_and_decisions_append_only(tmp_path):
    mod = load_plugin()
    ledger = Ledger(tmp_path / "ledger.db")
    big = {f"k{i}" * 30: "v" * 500 for i in range(50)}
    mod.record_stand_aside(ledger, {"reason_code": "X", "why": "y", "evidence": big})
    ev = ledger.decisions()[0]["evidence"]
    assert len(ev) == 20 and all(len(k) <= 40 and len(v) <= 120 for k, v in ev.items())
    with pytest.raises(sqlite3.DatabaseError):
        ledger.db.execute("DELETE FROM decisions")
