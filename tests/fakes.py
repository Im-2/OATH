"""Test doubles for flow/monitor/plugin tests. Fixtures only (SPEC §0.2).

The entry swap is the REAL mainnet tx 2yVvHjqB... (tests/fixtures); the exit swap is synthetic
but shaped like a jsonParsed mainnet tx.
"""
from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

from oath_core.config import USDC_MINT, Config
from oath_core.executor import ExecTokens
from oath_core.flow import Ctx
from oath_core.ledger import Ledger
from oath_core.notary import Posted
from oath_core.policy import Policy

AGENT = "9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY"
AGENT_ID = "2b9abb41-60e1-4b62-b1ec-ce772445003e"
NOTARY = "FhpJ6i5oaBiCpNJasksf2qBgFmTv6ikgSUuqDzSBiUod"
ENTRY_SIG = "2yVvHjqByEtJEk6Xh8GQcLJ4Um6KBTJosFaxtQMfS7nTnYLTXVEasmWfQ9McNJUsEuuLkq3XK6wPNqFrvYLEHDDu"
ENTRY_TX = json.loads((Path(__file__).parent / "fixtures" / "swap_usdc_to_sol_2yVv.json").read_text())
EXIT_SIG = "3" * 87 + "X"
SOL_PX = Decimal("121.60")


def exit_tx(sig=EXIT_SIG, slot=ENTRY_TX["slot"] + 4000, sold=8_226_769, usdc_out=1_010_000, fee=5000,
            block_time=None):
    return {"slot": slot, "blockTime": block_time or ENTRY_TX["blockTime"] + 1800,
            "meta": {"err": None, "fee": fee, "preBalances": [30_000_000], "postBalances": [30_000_000 - sold - fee],
                     "preTokenBalances": [{"owner": AGENT, "mint": USDC_MINT, "uiTokenAmount": {"amount": "100"}}],
                     "postTokenBalances": [{"owner": AGENT, "mint": USDC_MINT,
                                            "uiTokenAmount": {"amount": str(100 + usdc_out)}}]},
            "transaction": {"signatures": [sig], "message": {"accountKeys": [{"pubkey": AGENT, "signer": True}],
                                                             "instructions": []}}}


class FakeCP:
    """ClawPump: quotes/prices at SOL_PX; swap_execute returns the fixture signatures."""

    def __init__(self, price=SOL_PX, liquidity="7000000000", swap_fails=False):
        self.price, self.liquidity, self.swap_fails = price, liquidity, swap_fails
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "get_agent":
            return {"id": AGENT_ID, "wallet_address": AGENT}
        if tool == "get_portfolio":
            return {"usdc_balance": "1.98", "sol_balance": "0.005"}
        if tool == "get_price":
            if self.price is None:
                from oath_core.clawpump import ClawPumpError
                raise ClawPumpError("price down")
            return {"prices": {args["tokens"]: {"usd": float(self.price), "liquidity": float(self.liquidity),
                                                "source": "fake"}}}
        if tool == "swap_quote":
            if self.price is None:
                from oath_core.clawpump import ClawPumpError
                raise ClawPumpError("swap_quote: no route")
            n = int(args["amount"])
            if args["input_mint"] == USDC_MINT:
                out = int(Decimal(n) / 10**6 / self.price * 10**9)
            else:
                out = int(Decimal(n) / 10**9 * self.price * 10**6)
            return {"status": "quoted", "input": {"mint": args["input_mint"], "rawAmount": str(n)},
                    "output": {"mint": args["output_mint"], "rawAmount": str(out)}}
        if tool == "swap_execute":
            if self.swap_fails:
                from oath_core.clawpump import ClawPumpError
                raise ClawPumpError("swap_execute: backend 502")
            sig = ENTRY_SIG if args["input_mint"] == USDC_MINT else EXIT_SIG
            return {"status": "executed", "txHash": sig}
        raise AssertionError(f"unexpected tool {tool}")


class FakeRpc:
    def __init__(self, notary_lamports=10_000_000, agent_lamports=30_000_000, usdc_raw=1_987_050):
        self.balances = {NOTARY: notary_lamports, AGENT: agent_lamports}
        self.usdc_raw = usdc_raw
        self.txs = {ENTRY_SIG: copy.deepcopy(ENTRY_TX), EXIT_SIG: exit_tx()}

    def get_balance(self, pk):
        return self.balances.get(pk, 0)

    def get_min_rent(self, n):
        return 650_240 if n == 0 else 1_488_440

    def wait_transaction(self, sig, timeout_s=60):
        return copy.deepcopy(self.txs[sig])

    def get_transaction(self, sig):
        return copy.deepcopy(self.txs.get(sig))

    def get_signatures_for_address(self, addr):
        return []

    def call(self, method, params):
        if method == "getTokenAccountsByOwner":
            return {"value": [{"account": {"data": {"parsed": {"info": {"tokenAmount": {"amount": str(self.usdc_raw)}}}}}}]}
        raise AssertionError(method)


class FakeNotary:
    """Records memos; slots start below the fixture entry slot so commit < swap holds."""

    def __init__(self, funded=True):
        self.pubkey = NOTARY
        self.posted: list[list[str]] = []
        self.slot = ENTRY_TX["slot"] - 100
        self.funded = funded

    def _post(self, texts):
        self.posted.append(texts)
        self.slot += 1 if self.slot < ENTRY_TX["slot"] - 1 else 5000
        return Posted(f"{len(self.posted)}" + "N" * 87, self.slot)

    def assert_funded(self, n):
        if not self.funded:
            from oath_core.solana_rpc import RpcError
            raise RpcError("notary unfunded")

    def simulate(self, texts):
        return {"err": None, "unitsConsumed": 1000}

    def commit(self, agent, seq, dg, bond=0):
        from oath_core import memo as m
        return self._post([m.commit(agent, seq, dg, bond)])

    def blocked(self, agent, seq, dg, reason):
        from oath_core import memo as m
        return self._post([m.blocked(agent, seq, dg, reason)])

    def open(self, agent, seq, sig):
        from oath_core import memo as m
        return self._post([m.open_(agent, seq, sig)])

    def reveal(self, agent, seq, salt, exit_sig, reason, canon):
        from oath_core import memo as m
        return self._post([m.reveal(agent, seq, salt.hex(), exit_sig, reason), m.thesis(seq, canon)])

    def slash(self, agent, seq, reason):
        from oath_core import memo as m
        return self._post([m.slash(agent, seq, reason)])

    def kinds(self):
        return [t[0].split(":")[1] for t in self.posted]


def make_ctx(tmp_path, *, cp=None, rpc=None, notary=None, policy=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return Ctx(Config(agent_id=AGENT_ID, agent_wallet=AGENT), rpc or FakeRpc(), notary or FakeNotary(),
               Ledger(tmp_path / "ledger.db"), cp or FakeCP(), ExecTokens(),
               load_policy=lambda: policy or Policy(), testmode_path=tmp_path / "test_mode.json")


OPEN_ARGS = dict(mkt="SOL/USDC", size_usd="1.00", entry="market", stop_pct="3", tp_pct="5", horizon_min=60,
                 conf="0.6", strat="trend_pullback", why="TREND_UP: test thesis")
