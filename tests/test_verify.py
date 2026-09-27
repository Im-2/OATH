"""verify.py against a fake RPC: synthetic notary memo txs + the REAL entry swap fixture."""
import copy
import json
from decimal import Decimal
from pathlib import Path

from oath_core import memo as m
from oath_core.config import MEMO_PROGRAM_ID, SOL_MINT, USDC_MINT
from oath_core.thesis import build_thesis, canonical_json, digest
from oath_core.verify import verify

AGENT = "9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY"
NOTARY = "FhpJ6i5oaBiCpNJasksf2qBgFmTv6ikgSUuqDzSBiUod"
ATTACKER = "GMCJvYGf5Ex2ARiMquaBDqU6iKM8uiEQkB8jCnoNfHpC"
ENTRY_SIG = "2yVvHjqByEtJEk6Xh8GQcLJ4Um6KBTJosFaxtQMfS7nTnYLTXVEasmWfQ9McNJUsEuuLkq3XK6wPNqFrvYLEHDDu"
ENTRY_TX = json.loads((Path(__file__).parent / "fixtures" / "swap_usdc_to_sol_2yVv.json").read_text())
ENTRY_SLOT = ENTRY_TX["slot"]  # 451033522
T0 = ENTRY_TX["blockTime"]
SALT = bytes(range(32))


def sig(n: int) -> str:
    return (str(n) + "A" * 88)[:88].replace("0", "z")


class FakeRpc:
    def __init__(self):
        self.txs = {}

    def add(self, s, tx):
        self.txs[s] = tx

    def get_transaction(self, s):
        return copy.deepcopy(self.txs.get(s))

    def get_signatures_for_address(self, addr):
        rows = [{"signature": s, "err": t["meta"]["err"], "slot": t["slot"], "blockTime": t["blockTime"]}
                for s, t in self.txs.items()
                if any(k["pubkey"] == addr for k in t["transaction"]["message"]["accountKeys"])]
        return sorted(rows, key=lambda r: r["slot"], reverse=True)


def memo_tx(s, slot, texts, signer=NOTARY, extra_keys=()):
    keys = [{"pubkey": signer, "signer": True}] + [{"pubkey": k, "signer": False} for k in extra_keys]
    return {"slot": slot, "blockTime": T0 + (slot - ENTRY_SLOT) // 2,
            "meta": {"err": None, "fee": 6000, "preBalances": [10**7] * len(keys),
                     "postBalances": [10**7 - 6000] + [10**7] * (len(keys) - 1),
                     "preTokenBalances": [], "postTokenBalances": []},
            "transaction": {"signatures": [s], "message": {
                "accountKeys": keys,
                "instructions": [{"programId": MEMO_PROGRAM_ID, "parsed": t} for t in texts]}}}


def exit_tx(s, slot, sold_lamports, usdc_out_raw, fee=5000):
    pre_usdc, post_usdc = 176, 176 + usdc_out_raw
    return {"slot": slot, "blockTime": T0 + (slot - ENTRY_SLOT) // 2,
            "meta": {"err": None, "fee": fee, "preBalances": [22_271_655], "postBalances": [22_271_655 - sold_lamports - fee],
                     "preTokenBalances": [{"owner": AGENT, "mint": USDC_MINT, "uiTokenAmount": {"amount": str(pre_usdc)}}],
                     "postTokenBalances": [{"owner": AGENT, "mint": USDC_MINT, "uiTokenAmount": {"amount": str(post_usdc)}}]},
            "transaction": {"signatures": [s], "message": {"accountKeys": [{"pubkey": AGENT, "signer": True}],
                                                          "instructions": []}}}


def thesis(seq=1):
    return build_thesis(agent=AGENT, seq=seq, mkt="SOL/USDC", in_mint=USDC_MINT, out_mint=SOL_MINT, size_usd="1.00",
                        entry="121.55", stop="117.90", tp="127.60", horizon_min=60, conf="0.60",
                        strat="manual_test", why="PHASE1_ROUNDTRIP: manual verification trade",
                        ts="2026-09-27T15:11:30Z")


def round_trip(rpc, *, commit_slot=ENTRY_SLOT - 20, tamper=False, usdc_out=1_010_000):
    t = thesis()
    canon = canonical_json(t)
    dg = digest(canon, SALT)
    rpc.add(sig(1), memo_tx(sig(1), commit_slot, [m.commit(AGENT, 1, dg, 0)]))
    rpc.add(ENTRY_SIG, ENTRY_TX)
    rpc.add(sig(2), memo_tx(sig(2), ENTRY_SLOT + 5, [m.open_(AGENT, 1, ENTRY_SIG)]))
    rpc.add(sig(3), exit_tx(sig(3), ENTRY_SLOT + 5000, 8_226_769, usdc_out))
    revealed = canon.replace(b"manual verification", b"manual verificatioN") if tamper else canon
    rpc.add(sig(4), memo_tx(sig(4), ENTRY_SLOT + 5010, [m.reveal(AGENT, 1, SALT.hex(), sig(3), "manual"),
                                                       "oath1:t:1:" + revealed.decode()]))
    return t


def run(rpc, **kw):
    return verify(rpc, NOTARY, now=T0 + 3600, **kw)


def test_honest_round_trip_passes_and_pnl_from_chain():
    rpc = FakeRpc()
    round_trip(rpc)
    r = run(rpc)
    assert r["pass"], r["issues"]
    row = r["agents"][AGENT]["positions"][0]
    assert row["status"] == "revealed" and row["digest_ok"]
    g = row["grade"]
    # 1.010000 - 1.000000 USDC gross; fees 10,002 lamports at the exit price (1.01 / 0.008226769 SOL)
    fees_usd = Decimal(10_002) / 10**9 * (Decimal("1.01") / Decimal("0.008226769"))
    assert Decimal(g["gross_pnl_usd"]) == Decimal("0.010000")
    assert Decimal(g["pnl_usd"]) == (Decimal("0.01") - fees_usd).quantize(Decimal("0.000001"))
    assert g["qty_match"] is True
    assert r["agents"][AGENT]["stats"]["completeness"] == "1"


def test_tampered_reveal_fails_digest():
    rpc = FakeRpc()
    round_trip(rpc, tamper=True)
    r = run(rpc)
    assert not r["pass"]
    assert any("committed digest" in i for i in r["issues"])


def test_open_before_commit_flagged():
    rpc = FakeRpc()
    round_trip(rpc, commit_slot=ENTRY_SLOT + 1)
    r = run(rpc)
    assert not r["pass"]
    assert any("did not land after commit" in i for i in r["issues"])


def test_sequence_gap_flagged():
    rpc = FakeRpc()
    round_trip(rpc)
    rpc.add(sig(9), memo_tx(sig(9), ENTRY_SLOT + 6000, [m.commit(AGENT, 3, "cd" * 32, 0)]))
    r = run(rpc)
    assert r["agents"][AGENT]["gaps"] == [2]
    assert not r["pass"]


def test_memo_in_tx_not_signed_by_notary_is_ignored():
    rpc = FakeRpc()
    round_trip(rpc)
    # Attacker's tx references the notary account but is signed by someone else.
    rpc.add(sig(7), memo_tx(sig(7), ENTRY_SLOT + 7000, [m.commit(AGENT, 1, "ee" * 32, 0)],
                            signer=ATTACKER, extra_keys=[NOTARY]))
    r = run(rpc)
    assert r["pass"], r["issues"]


def test_unrevealed_past_deadline_counts_as_loss():
    rpc = FakeRpc()
    t = thesis()
    dg = digest(canonical_json(t), SALT)
    rpc.add(sig(1), memo_tx(sig(1), ENTRY_SLOT - 20, [m.commit(AGENT, 1, dg, 0)]))
    rpc.add(ENTRY_SIG, ENTRY_TX)
    rpc.add(sig(2), memo_tx(sig(2), ENTRY_SLOT + 5, [m.open_(AGENT, 1, ENTRY_SIG)]))
    r = verify(rpc, NOTARY, now=T0 + (360 + 30 + 1) * 60, scan_agent=False)
    assert not r["pass"]
    stats = r["agents"][AGENT]["stats"]
    assert stats["unrevealed"] == 1
    assert Decimal(stats["realised_pnl_usd"]) == Decimal("-1.000000")  # full loss of the on-chain entry spend


def test_open_position_within_deadline_is_fine():
    rpc = FakeRpc()
    t = thesis()
    dg = digest(canonical_json(t), SALT)
    rpc.add(sig(1), memo_tx(sig(1), ENTRY_SLOT - 20, [m.commit(AGENT, 1, dg, 0)]))
    rpc.add(ENTRY_SIG, ENTRY_TX)
    rpc.add(sig(2), memo_tx(sig(2), ENTRY_SLOT + 5, [m.open_(AGENT, 1, ENTRY_SIG)]))
    r = verify(rpc, NOTARY, now=T0 + 600)
    assert r["pass"], r["issues"]
    assert r["agents"][AGENT]["positions"][0]["status"] == "open"


def test_uncommitted_agent_trade_flagged():
    rpc = FakeRpc()
    round_trip(rpc)
    rpc.add(sig(8), exit_tx(sig(8), ENTRY_SLOT + 8000, 1_000_000, 120_000))  # agent swap nobody committed to
    r = run(rpc)
    assert not r["pass"]
    assert r["agents"][AGENT]["uncommitted_trades"][0]["sig"] == sig(8)


def test_exit_quantity_mismatch_flagged():
    rpc = FakeRpc()
    round_trip(rpc)
    rpc.add(sig(3), exit_tx(sig(3), ENTRY_SLOT + 5000, 4_000_000, 500_000))  # sold only half
    r = run(rpc)
    assert not r["pass"]
    assert any("exit sold" in i for i in r["issues"])
