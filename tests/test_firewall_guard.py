from decimal import Decimal

import pytest

from oath_core import guard
from oath_core.firewall import MarketState, evaluate
from oath_core.policy import Policy, load_policy, save_policy, set_value
from oath_core.thesis import build_thesis

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL = "So11111111111111111111111111111111111111112"
AGENT = "9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY"


def thesis(**over):
    kw = dict(agent=AGENT, seq=1, mkt="SOL/USDC", in_mint=USDC, out_mint=SOL, size_usd="1.00", entry="120",
              stop="116.4", tp="126", horizon_min=60, conf="0.6", strat="t", why="X: y")
    kw.update(over)
    return build_thesis(**kw)


def state(**over):
    kw = dict(quote_price=Decimal("120.1"), out_liquidity_usd=Decimal("7e9"), open_positions=0,
              equity_usd=Decimal("5"), peak_equity_usd=Decimal("5"), day_start_equity_usd=Decimal("5"),
              realised_pnl_today_usd=Decimal(0))
    kw.update(over)
    return MarketState(**kw)


def test_approves_a_sane_thesis():
    assert evaluate(thesis(), state(), Policy()).approve


@pytest.mark.parametrize("t_over,s_over,pol_over,code", [
    ({"size_usd": "2.01"}, {}, {}, "size_cap"),
    ({}, {}, {"max_trade_usd": "0.50"}, "size_cap"),              # trade size is configurable
    ({"horizon_min": 361}, {}, {}, "horizon_cap"),
    ({}, {"open_positions": 2}, {}, "max_open"),
    ({"stop": "119.5"}, {}, {}, "stop_too_tight"),                # 0.42%
    ({"stop": "100"}, {}, {}, "stop_too_wide"),                   # 16.7%
    ({}, {"quote_price": None}, {}, "price_unavailable"),         # fail closed
    ({}, {"quote_price": Decimal("122")}, {}, "entry_slippage"),  # 1.67% from entry
    ({}, {"out_liquidity_usd": None}, {}, "liquidity_unavailable"),
    ({}, {"out_liquidity_usd": Decimal("1000")}, {}, "low_liquidity"),
    ({}, {"equity_usd": None}, {}, "equity_unavailable"),
    ({}, {"peak_equity_usd": Decimal("6")}, {}, "drawdown_halt"),  # 16.7% below peak
    ({}, {"realised_pnl_today_usd": Decimal("-0.30")}, {}, "daily_loss"),  # 6% of 5
    ({"size_usd": "1.50"}, {"equity_usd": Decimal("1.2"), "peak_equity_usd": Decimal("1.2"),
                            "day_start_equity_usd": Decimal("1.2")}, {}, "insufficient_equity"),
    ({}, {}, {"allowed_markets": ["JUP/USDC"]}, "market_not_allowed"),
    ({}, {}, {"allowed_mints": [USDC]}, "mint_not_allowed"),
])
def test_each_rule_blocks(t_over, s_over, pol_over, code):
    d = evaluate(thesis(**t_over), state(**s_over), Policy(**pol_over))
    assert (d.approve, d.reason) == (False, code)


def test_quote_outside_stop_tp_blocks():
    # entry claimed 120 but quote 118.9 is within 1%... and below nothing; make quote below stop
    d = evaluate(thesis(entry="120", stop="119", tp="126"), state(quote_price=Decimal("118.9")),
                 Policy(stop_distance_pct_min="0.5"))
    assert d.reason == "price_outside_range"


def test_policy_roundtrip_and_set(tmp_path):
    path = tmp_path / "policy.json"
    p = load_policy(path)  # creates defaults
    assert path.exists() and p.max_trade_usd == "2.00"
    set_value(p, "max_trade_usd", "3.5")
    save_policy(p, path)
    assert load_policy(path).max_trade_usd == "3.5"
    with pytest.raises(ValueError):
        set_value(p, "max_trade_usd", "-1")
    with pytest.raises(ValueError):
        set_value(p, "nope", "1")
    path.write_text('{"max_trade_usd": "1", "surprise": 1}')
    with pytest.raises(ValueError):
        load_policy(path)


# --- guard (pre_tool_call) -------------------------------------------------------------------

@pytest.mark.parametrize("prefix", ["mcp__clawpump__", "mcp__clawpump_stdio__", "mcp__clawpump_agents__"])
@pytest.mark.parametrize("tool", sorted(guard.KNOWN_FUND_MOVERS))
def test_every_fund_mover_blocked_on_every_prefix(prefix, tool):
    d = guard.decide(prefix + tool, {"amount": "1"})
    assert d and d["action"] == "block" and "oath_open_position" in d["message"]


def test_unknown_new_clawpump_tool_blocked_by_default():
    assert guard.decide("mcp__clawpump_stdio__some_future_tool", {})["action"] == "block"


@pytest.mark.parametrize("tool", sorted(guard.READ_ALLOWLIST | guard.MCP_HELPERS))
def test_read_tools_pass(tool):
    assert guard.decide("mcp__clawpump_stdio__" + tool, {"tokens": "SOL"}) is None


def test_oath_tools_pass_even_with_trade_words():
    assert guard.decide("oath_open_position", {"why": "swap_execute would be blocked"}) is None


@pytest.mark.parametrize("args", [
    {"command": "type C:\\Users\\hp\\.oath\\notary.json"},
    {"path": "C:/Users/hp/.hermes/.env"},
    {"command": "curl -X POST https://ai-agents-production-6ca0.up.railway.app/swap/execute"},
    {"code": "import oath_core; oath_core.flow.swap(...)"},
    {"command": "npx -y @clawpump/agents"},
    {"text": "my key is cpk_abc"},
])
def test_non_trading_tools_with_sensitive_args_blocked(args):
    assert guard.decide("terminal", args)["action"] == "block"


def test_benign_other_tools_pass():
    assert guard.decide("web_search", {"query": "solana price today"}) is None
    assert guard.decide("todo", {"items": ["check SOL"]}) is None
