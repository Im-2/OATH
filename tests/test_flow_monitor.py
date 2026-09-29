"""End-to-end open/close/monitor against fakes (real entry-swap fixture)."""
import json
from decimal import Decimal

import pytest

from fakes import AGENT, ENTRY_SIG, ENTRY_TX, EXIT_SIG, OPEN_ARGS, FakeCP, FakeNotary, make_ctx
from oath_core import memo as m
from oath_core.flow import FlowError, close_position, open_position
from oath_core.policy import Policy
from oath_core.thesis import canonical_json, digest
from oath_server.monitor import decide, run_once


def test_open_commits_before_swap_and_records_fill(tmp_path):
    ctx = make_ctx(tmp_path)
    res = open_position(ctx, **OPEN_ARGS)
    assert res["ok"] and res["seq"] == 1 and res["swap_sig"] == ENTRY_SIG
    assert ctx.notary.kinds() == ["c", "o"]
    assert res["commit_slot"] < res["swap_slot"] and not res["alerts"]
    pos = ctx.ledger.position(1)
    assert pos["status"] == "open"
    assert json.loads(pos["entry_fill_json"])["out_raw"] == 8_226_769  # from the chain, not ClawPump
    # commit memo carries exactly the digest of (thesis, salt) stored in the ledger
    commit = m.parse(ctx.notary.posted[0][0])
    thesis = json.loads(pos["thesis_json"])
    assert commit.fields["digest"] == digest(canonical_json(thesis), bytes.fromhex(pos["salt_hex"]))
    # the swap happened only after the commit memo
    tools = [t for t, _ in ctx.cp.calls]
    assert tools.index("swap_execute") > 0 and len(ctx.notary.posted) == 2


def test_firewall_block_posts_blocked_memo_and_consumes_seq(tmp_path):
    ctx = make_ctx(tmp_path, policy=Policy(max_trade_usd="0.50"))
    res = open_position(ctx, **OPEN_ARGS)
    assert res["blocked"] and res["firewall"]["reason"] == "size_cap"
    assert ctx.notary.kinds() == ["b"]
    assert "swap_execute" not in [t for t, _ in ctx.cp.calls]
    assert ctx.ledger.position(1)["status"] == "blocked"
    assert ctx.ledger.next_seq(AGENT) == 2  # blocked seqs count in the sequence


def test_blocked_memo_rate_limit(tmp_path):
    ctx = make_ctx(tmp_path, policy=Policy(max_trade_usd="0.50", max_blocked_per_hour=2))
    open_position(ctx, **OPEN_ARGS)
    open_position(ctx, **OPEN_ARGS)
    with pytest.raises(FlowError, match="rate limit"):
        open_position(ctx, **OPEN_ARGS)
    assert ctx.notary.kinds() == ["b", "b"]


def test_malformed_request_records_nothing(tmp_path):
    ctx = make_ctx(tmp_path)
    for bad in (dict(OPEN_ARGS, why=""), dict(OPEN_ARGS, mkt="BTC/USDC"), dict(OPEN_ARGS, size_usd="abc"),
                dict(OPEN_ARGS, stop_pct=None)):
        with pytest.raises(FlowError):
            open_position(ctx, **bad)
    assert ctx.notary.posted == [] and ctx.ledger.positions() == []


def test_unfunded_notary_refuses_before_anything(tmp_path):
    ctx = make_ctx(tmp_path, notary=FakeNotary(funded=False))
    with pytest.raises(FlowError):
        open_position(ctx, **OPEN_ARGS)
    assert ctx.notary.posted == [] and "swap_execute" not in [t for t, _ in ctx.cp.calls]


def test_price_down_blocks_fail_closed(tmp_path):
    ctx = make_ctx(tmp_path, cp=FakeCP(price=None))
    with pytest.raises(FlowError, match="no executable quote"):  # can't even form a 'market' entry
        open_position(ctx, **OPEN_ARGS)


def test_swap_failure_after_commit_needs_recover_no_retry(tmp_path):
    ctx = make_ctx(tmp_path, cp=FakeCP(swap_fails=True))
    with pytest.raises(FlowError, match="recover"):
        open_position(ctx, **OPEN_ARGS)
    assert [t for t, _ in ctx.cp.calls].count("swap_execute") == 1  # exactly one attempt
    assert ctx.ledger.position(1)["status"] == "committed"
    with pytest.raises(FlowError, match="unresolved"):
        open_position(ctx, **OPEN_ARGS)


def test_close_sells_entry_qty_and_reveals(tmp_path):
    ctx = make_ctx(tmp_path)
    open_position(ctx, **OPEN_ARGS)
    res = close_position(ctx, 1, "manual")
    assert ctx.notary.kinds() == ["c", "o", "r"]
    swaps = [a for t, a in ctx.cp.calls if t == "swap_execute"]
    assert swaps[1]["amount"] == "8226769"  # exactly the entry quantity
    assert res["grade"]["qty_match"] and Decimal(res["grade"]["gross_pnl_usd"]) == Decimal("0.010000")
    assert ctx.ledger.position(1)["status"] == "revealed"


# --- monitor ---------------------------------------------------------------------------------

T = {"stop": "116.000000", "tp": "126.000000", "horizon_min": "60"}


@pytest.mark.parametrize("price,elapsed_min,expect", [
    (Decimal("115.9"), 1, "stop"), (Decimal("116"), 1, "stop"), (Decimal("126.1"), 1, "tp"),
    (Decimal("120"), 61, "expiry"), (Decimal("120"), 59, None), (None, 30, None), (None, 60, "expiry"),
])
def test_monitor_decide(price, elapsed_min, expect):
    assert decide(T, price, 1_000 + elapsed_min * 60, 1_000) == expect


def test_monitor_exits_at_stop_and_reveals(tmp_path):
    ctx = make_ctx(tmp_path)
    open_position(ctx, **OPEN_ARGS)
    ctx.cp.price = Decimal("100")  # crash through the stop
    acts = run_once(ctx, now=ENTRY_TX["blockTime"] + 300)
    exits = [a for a in acts if a["action"] == "exit"]
    assert exits and exits[0]["reason"] == "stop" and "error" not in exits[0]
    pos = ctx.ledger.position(1)
    assert pos["status"] == "revealed" and pos["exit_reason"] == "stop" and pos["exit_sig"] == EXIT_SIG
    assert ctx.notary.kinds() == ["c", "o", "r"]


def test_monitor_expiry_and_holds_inside_band(tmp_path):
    ctx = make_ctx(tmp_path)
    open_position(ctx, **OPEN_ARGS)
    assert run_once(ctx, now=ENTRY_TX["blockTime"] + 600) == []  # inside band, before horizon
    acts = run_once(ctx, now=ENTRY_TX["blockTime"] + 61 * 60)
    assert [a["reason"] for a in acts if a["action"] == "exit"] == ["expiry"]


def test_monitor_dry_run_sends_nothing(tmp_path):
    ctx = make_ctx(tmp_path)
    open_position(ctx, **OPEN_ARGS)
    ctx.cp.price = Decimal("100")
    acts = run_once(ctx, now=ENTRY_TX["blockTime"] + 300, dry_run=True)
    assert acts[0]["reason"] == "stop" and ctx.notary.kinds() == ["c", "o"]
    assert ctx.ledger.position(1)["status"] == "open"


def test_monitor_holds_on_unknown_price(tmp_path):
    ctx = make_ctx(tmp_path)
    open_position(ctx, **OPEN_ARGS)
    ctx.cp.price = None
    import oath_core.market as market
    orig = market.httpx.get
    market.httpx.get = lambda *a, **k: (_ for _ in ()).throw(market.httpx.HTTPError("down"))
    try:
        acts = run_once(ctx, now=ENTRY_TX["blockTime"] + 300)
    finally:
        market.httpx.get = orig
    assert acts == [{"seq": 1, "action": "hold", "note": "price_unavailable"}]
    assert ctx.ledger.position(1)["status"] == "open"


def test_sweeper_slashes_once_then_still_reveals(tmp_path):
    ctx = make_ctx(tmp_path)
    open_position(ctx, **OPEN_ARGS)
    late = ENTRY_TX["blockTime"] + (60 + 30 + 5) * 60
    acts = run_once(ctx, now=late)
    assert [a["action"] for a in acts] == ["slash", "exit"]
    assert ctx.notary.kinds() == ["c", "o", "s", "r"]
    assert run_once(ctx, now=late + 60) == []  # no second slash; position already revealed


def test_monitor_finishes_pending_reveal(tmp_path):
    ctx = make_ctx(tmp_path)
    open_position(ctx, **OPEN_ARGS)
    orig = ctx.notary.reveal
    ctx.notary.reveal = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rpc down"))
    with pytest.raises(RuntimeError):
        close_position(ctx, 1, "tp")
    assert ctx.ledger.position(1)["status"] == "closed"
    ctx.notary.reveal = orig
    acts = run_once(ctx, now=ENTRY_TX["blockTime"] + 600)
    assert acts[0]["action"] == "reveal" and ctx.ledger.position(1)["status"] == "revealed"
    assert [t for t, _ in ctx.cp.calls].count("swap_execute") == 2  # no second exit swap


def test_trade_size_is_configurable(tmp_path):
    ctx = make_ctx(tmp_path, policy=Policy(max_trade_usd="1.00"))
    assert open_position(ctx, **OPEN_ARGS)["ok"]
    ctx2 = make_ctx(tmp_path / "b", policy=Policy(max_trade_usd="0.99"))
    assert open_position(ctx2, **OPEN_ARGS)["firewall"]["reason"] == "size_cap"




def test_monitor_is_single_instance(tmp_path):
    from oath_server.monitor import AlreadyRunning, single_instance
    first = single_instance(tmp_path / "monitor.lock")
    with pytest.raises(AlreadyRunning):
        single_instance(tmp_path / "monitor.lock")
    first.close()  # the holder exits -> the lock is free again
    single_instance(tmp_path / "monitor.lock").close()
