"""Notary CU sizing: fee cap holds for any limit; failed simulation never sends."""
import pytest
from solders.keypair import Keypair

from oath_core import memo as m
from oath_core.notary import MAX_CU, PRIORITY_LAMPORTS, Notary, build_memo_tx, priority_fee
from oath_core.solana_rpc import RpcError

BLOCKHASH = "4sGjMW1sUnHzSxGspuhpqLDx6wiyjNtZAMdL4VZHirAn"
AGENT = "9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY"


@pytest.mark.parametrize("limit", [1, 999, 58_112, 69_734, 200_000, 333_333, 1_000_001, MAX_CU])
def test_priority_fee_never_exceeds_cap(limit):
    assert priority_fee(limit) <= PRIORITY_LAMPORTS


def test_max_cu_priority_is_exactly_the_cap():
    # required_lamports prices the worst case with a MAX_CU probe tx.
    assert priority_fee(MAX_CU) == PRIORITY_LAMPORTS


class FakeRpc:
    def __init__(self, sim):
        self.sim = sim
        self.sent = []

    def get_latest_blockhash(self):
        return BLOCKHASH

    def simulate_transaction(self, b64):
        return dict(self.sim)

    def send_transaction(self, b64):
        self.sent.append(b64)
        raise AssertionError("must not send")


def test_fit_cu_limit_uses_measured_units_plus_headroom():
    n = Notary(Keypair(), FakeRpc({"err": None, "unitsConsumed": 300_000}))
    assert n.fit_cu_limit(["oath1:t:1:{}"], BLOCKHASH) == 362_000


def test_fit_cu_limit_capped_at_max():
    n = Notary(Keypair(), FakeRpc({"err": None, "unitsConsumed": 1_390_000}))
    assert n.fit_cu_limit(["x"], BLOCKHASH) == MAX_CU


def test_failed_simulation_sends_nothing():
    rpc = FakeRpc({"err": {"InstructionError": [3, "ProgramFailedToComplete"]}, "unitsConsumed": 1_400_000,
                   "logs": ["exceeded CUs meter"]})
    n = Notary(Keypair(), rpc)
    with pytest.raises(RpcError):
        n.post([m.commit(AGENT, 1, "ab" * 32, 0)])
    assert rpc.sent == []


def test_build_rejects_out_of_range_limit():
    with pytest.raises(ValueError):
        build_memo_tx(Keypair(), ["x"], BLOCKHASH, cu_limit=MAX_CU + 1)
    with pytest.raises(ValueError):
        build_memo_tx(Keypair(), ["x"], BLOCKHASH, cu_limit=0)
