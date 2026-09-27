import sqlite3

import pytest

from oath_core.executor import ExecTokenError, ExecTokens
from oath_core.ledger import Ledger, LedgerError

AGENT = "9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY"


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.db")


def prep(ledger, seq):
    ledger.prepare(AGENT, seq, {"seq": str(seq)}, "00" * 32, "ab" * 32)


def test_seq_contiguous_from_one(ledger):
    assert ledger.next_seq(AGENT) == 1
    prep(ledger, 1)
    prep(ledger, 2)
    assert ledger.next_seq(AGENT) == 3


def test_seq_gap_rejected(ledger):
    prep(ledger, 1)
    with pytest.raises(LedgerError):
        prep(ledger, 3)


def test_duplicate_seq_rejected(ledger):
    prep(ledger, 1)
    with pytest.raises(LedgerError):
        prep(ledger, 1)


def test_events_append_only(ledger):
    prep(ledger, 1)
    with pytest.raises(sqlite3.DatabaseError):
        ledger.db.execute("UPDATE events SET kind = 'commit'")
    with pytest.raises(sqlite3.DatabaseError):
        ledger.db.execute("DELETE FROM events")


def test_record_updates_position_and_logs_event(ledger):
    prep(ledger, 1)
    ledger.record(1, "commit", {"x": 1}, tx_sig="s", slot=10, status="committed", commit_sig="s", commit_slot=10)
    assert ledger.position(1)["status"] == "committed"
    assert [e["kind"] for e in ledger.events(1)] == ["prepared", "commit"]
    with pytest.raises(LedgerError):
        ledger.record(1, "commit", {}, not_a_column=1)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_exec_token_single_use_and_bound_to_seq():
    toks = ExecTokens()
    t = toks.issue(5)
    toks.consume(t, 5)
    with pytest.raises(ExecTokenError):
        toks.consume(t, 5)  # replay
    t2 = toks.issue(6)
    with pytest.raises(ExecTokenError):
        toks.consume(t2, 7)  # wrong seq
    with pytest.raises(ExecTokenError):
        toks.consume(t2, 6)  # spent by the failed attempt


def test_exec_token_expires():
    clock = Clock()
    toks = ExecTokens(ttl_s=60, clock=clock)
    t = toks.issue(1)
    clock.t = 61
    with pytest.raises(ExecTokenError):
        toks.consume(t, 1)


def test_unknown_token_rejected():
    with pytest.raises(ExecTokenError):
        ExecTokens().consume("deadbeef", 1)
