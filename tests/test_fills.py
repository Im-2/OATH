"""Fills from the REAL Phase 0 swap (tests/fixtures/swap_usdc_to_sol_2yVv.json, mainnet slot 451033522)."""
import copy
import json
from pathlib import Path

import pytest

from oath_core.config import SOL_MINT, USDC_MINT
from oath_core.fills import FillError, compute_fill

AGENT = "9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY"
SIG = "2yVvHjqByEtJEk6Xh8GQcLJ4Um6KBTJosFaxtQMfS7nTnYLTXVEasmWfQ9McNJUsEuuLkq3XK6wPNqFrvYLEHDDu"
TX = json.loads((Path(__file__).parent / "fixtures" / "swap_usdc_to_sol_2yVv.json").read_text())


def test_real_swap_fill_matches_chain():
    f = compute_fill(TX, SIG, AGENT, USDC_MINT, SOL_MINT)
    assert f.in_raw == 1_000_000            # exactly 1 USDC left the agent
    assert f.out_raw == 8_226_769           # gross SOL in = pool's SOL delta (not ClawPump's 8,227,098)
    assert f.fee_lamports == 5_002 and f.agent_paid_fee
    assert f.out_raw - f.fee_lamports == 8_221_767  # net native delta observed in Phase 0
    assert f.slot == 451033522


def test_failed_tx_refused():
    tx = copy.deepcopy(TX)
    tx["meta"]["err"] = {"InstructionError": [3, {"Custom": 1}]}
    with pytest.raises(FillError):
        compute_fill(tx, SIG, AGENT, USDC_MINT, SOL_MINT)


def test_wrong_signer_refused():
    with pytest.raises(FillError):
        compute_fill(TX, SIG, "FhpJ6i5oaBiCpNJasksf2qBgFmTv6ikgSUuqDzSBiUod", USDC_MINT, SOL_MINT)


def test_wrong_direction_refused():
    with pytest.raises(FillError):
        compute_fill(TX, SIG, AGENT, SOL_MINT, USDC_MINT)


def test_signature_mismatch_and_missing_tx_refused():
    with pytest.raises(FillError):
        compute_fill(TX, "1" * 88, AGENT, USDC_MINT, SOL_MINT)
    with pytest.raises(FillError):
        compute_fill(None, SIG, AGENT, USDC_MINT, SOL_MINT)
