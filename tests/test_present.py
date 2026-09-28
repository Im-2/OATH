"""Model-facing amounts are labelled (Phase 2 bug: 8,113,454 lamports reported as '8.113454 SOL')."""
import importlib.util
import json
from pathlib import Path

from fakes import OPEN_ARGS, make_ctx
from oath_core.present import amount, present_fill, present_open_result

SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SEQ2_ENTRY = {"sig": "x", "slot": 451088333, "block_time": 1, "in_mint": USDC, "out_mint": SOL,
              "in_raw": 1_000_000, "out_raw": 8_113_454, "fee_lamports": 5000, "agent_paid_fee": True}


def test_amounts_carry_units_and_full_precision():
    assert amount(8_113_454, SOL) == "0.008113454 SOL"
    assert amount(1_000_000, USDC) == "1.000000 USDC"
    assert amount(998_162, USDC) == "0.998162 USDC"


def test_seq2_fill_presented_correctly():
    f = present_fill(SEQ2_ENTRY)
    assert f["received"] == "0.008113454 SOL" and f["spent"] == "1.000000 USDC"
    assert f["fill_price"] == "123.252070 USDC per SOL" and f["network_fee"] == "0.000005000 SOL"
    assert "8.113454" not in json.dumps(f)
    assert f["raw_smallest_units"] == {"spent_usdc_micro": 1_000_000, "received_sol_lamports": 8_113_454,
                                       "fee_lamports": 5000}
    assert f["summary"].startswith("Spent 1.000000 USDC, received 0.008113454 SOL at 123.252070")


def test_exit_direction_price_still_usdc_per_sol():
    f = present_fill({**SEQ2_ENTRY, "in_mint": SOL, "out_mint": USDC, "in_raw": 8_113_454, "out_raw": 998_162})
    assert f["spent"] == "0.008113454 SOL" and f["received"] == "0.998162 USDC"
    assert f["fill_price"] == "123.025533 USDC per SOL"


def test_open_result_has_no_unlabelled_raw_amounts(tmp_path):
    from oath_core.flow import open_position
    res = present_open_result(open_position(make_ctx(tmp_path), **OPEN_ARGS))
    fill = res["fill"]
    assert "out_raw" not in fill and "in_raw" not in fill
    assert fill["received"].endswith(" SOL") and res["levels"]["stop"].endswith("USDC per SOL")
    assert res["quote_price"].endswith("USDC per SOL")


def test_plugin_handler_returns_presented_result(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "oath_plugin_c", Path(__file__).resolve().parent.parent / "plugin" / "oath" / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import oath_core.flow as flow
    monkeypatch.setattr(flow, "open_position", lambda ctx, **kw: {"ok": True, "fill": SEQ2_ENTRY,
                                                                   "quote_price": "123.2", "thesis": None})
    monkeypatch.setattr(mod, "_runtime", lambda ctx: None)
    out = json.loads(mod._make_open(None)(dict(OPEN_ARGS)))
    assert out["fill"]["received"] == "0.008113454 SOL" and "out_raw" not in out["fill"]
