import pytest
from solders.keypair import Keypair

from oath_core import memo as m
from oath_core.notary import MAX_TX_BYTES, build_memo_tx
from oath_core.thesis import build_thesis, canonical_json

AGENT = "9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY"
SIG = "2yVvHjqByEtJEk6Xh8GQcLJ4Um6KBTJosFaxtQMfS7nTnYLTXVEasmWfQ9McNJUsEuuLkq3XK6wPNqFrvYLEHDDu"
DIG = "ab" * 32
BLOCKHASH = "4sGjMW1sUnHzSxGspuhpqLDx6wiyjNtZAMdL4VZHirAn"


def test_roundtrip_each_kind():
    c = m.parse(m.commit(AGENT, 1, DIG, 0))
    assert (c.kind, c.agent, c.seq, c.fields) == ("c", AGENT, 1, {"digest": DIG, "bond_amt": 0})
    assert m.parse(m.blocked(AGENT, 2, DIG, "max_trade")).fields["reason_code"] == "max_trade"
    assert m.parse(m.open_(AGENT, 3, SIG)).fields["swap_sig"] == SIG
    r = m.parse(m.reveal(AGENT, 4, "cd" * 32, SIG, "tp"))
    assert r.fields == {"salt_hex": "cd" * 32, "exit_sig": SIG, "exit_reason": "tp"}
    assert m.parse(m.reveal(AGENT, 5, "cd" * 32, m.NO_SIG, "exec_failed")).fields["exit_sig"] == "none"
    assert m.parse(m.slash(AGENT, 6, "missed_reveal")).kind == "s"
    t = m.parse(m.thesis(7, b'{"a":"b:c"}'))
    assert (t.kind, t.seq, t.fields["thesis"]) == ("t", 7, '{"a":"b:c"}')


@pytest.mark.parametrize("bad", [
    "pot1:c:" + AGENT + ":1:" + DIG + ":0",       # wrong prefix
    "oath1:c:" + AGENT + ":0:" + DIG + ":0",      # seq 0
    "oath1:c:" + AGENT + ":01:" + DIG + ":0",     # leading zero
    "oath1:c:" + AGENT + ":1:" + DIG[:-1] + ":0", # short digest
    "oath1:c:" + AGENT + ":1:" + DIG.upper() + ":0",
    "oath1:c:" + AGENT + ":1:" + DIG,             # missing bond
    "oath1:c:bad:1:" + DIG + ":0",
    "oath1:o:" + AGENT + ":1:notasig",
    "oath1:r:" + AGENT + ":1:" + "cd" * 32 + ":" + SIG + ":moon",
    "oath1:r:" + AGENT + ":1:" + "cd" * 32 + ":none:manual",  # 'none' only for exec_failed
    "oath1:x:" + AGENT + ":1",
    "oath1:t:1",
])
def test_malformed_rejected(bad):
    with pytest.raises(m.MemoError):
        m.parse(bad)


def test_builders_refuse_invalid_output():
    with pytest.raises(m.MemoError):
        m.commit(AGENT, 1, "zz", 0)


def test_worst_case_reveal_tx_fits():
    """Largest thesis the schema allows + reveal memo must fit one tx (verify needs no API)."""
    t = build_thesis(agent=AGENT, seq=999999, mkt="ABCDEFGHIJKL/ABCDEFGHIJKL",
                     in_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                     out_mint="9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump",
                     size_usd="99999.99", entry="99999999.999999", stop="99999998.999999",
                     tp="999999999.999999", horizon_min=99999, conf="1.00", strat="s" * 32, why="W" * 140)
    kp = Keypair()
    tx = build_memo_tx(kp, [m.reveal(AGENT, 999999, "ff" * 32, SIG, "expiry"),
                            m.thesis(999999, canonical_json(t))], BLOCKHASH)
    assert len(bytes(tx)) <= MAX_TX_BYTES


def test_oversize_tx_refused():
    with pytest.raises(ValueError):
        build_memo_tx(Keypair(), ["oath1:t:1:" + "x" * 1300], BLOCKHASH)
