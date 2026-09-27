"""Notary: signs and sends oath1 memo transactions (SPEC §3, §4.3).

Each memo instruction lists the notary as a signer, so the Memo program itself
attests the notary signed that text. The verifier also requires the notary to
be a tx signer, so memos in txs merely *mentioning* the notary are ignored.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass

from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction

from . import memo as memos
from .config import MEMO_PROGRAM_ID
from .solana_rpc import Rpc, RpcError

MAX_TX_BYTES = 1232
MAX_CU = 1_400_000  # per-tx ceiling; the Memo program's cost grows with memo length
# Priority fee is held at <= 1,000 lamports whatever the CU limit, so every memo tx costs
# at most 5,000 base + 1,000 = 6,000 lamports and the notary budget stays exact.
PRIORITY_LAMPORTS = 1_000
CU_HEADROOM = 1.2


def cu_price_for(limit: int) -> int:
    """Micro-lamports per CU such that limit * price <= PRIORITY_LAMPORTS lamports."""
    return (PRIORITY_LAMPORTS * 1_000_000) // limit


def priority_fee(limit: int) -> int:
    return -(-limit * cu_price_for(limit) // 1_000_000)  # ceil, as the runtime charges


@dataclass(frozen=True)
class Posted:
    sig: str
    slot: int


def build_memo_tx(kp: Keypair, texts: list[str], blockhash: str, cu_limit: int = MAX_CU) -> Transaction:
    if not 0 < cu_limit <= MAX_CU:
        raise ValueError(f"cu_limit {cu_limit} outside (0, {MAX_CU}]")
    memo_pid = Pubkey.from_string(MEMO_PROGRAM_ID)
    ixs = [set_compute_unit_limit(cu_limit), set_compute_unit_price(cu_price_for(cu_limit))]
    for text in texts:
        ixs.append(Instruction(memo_pid, text.encode("utf-8"),
                               [AccountMeta(kp.pubkey(), is_signer=True, is_writable=False)]))
    bh = Hash.from_string(blockhash)
    tx = Transaction([kp], Message.new_with_blockhash(ixs, kp.pubkey(), bh), bh)
    size = len(bytes(tx))
    if size > MAX_TX_BYTES:
        raise ValueError(f"memo tx is {size} bytes (> {MAX_TX_BYTES})")
    return tx


class Notary:
    def __init__(self, kp: Keypair, rpc: Rpc):
        self.kp = kp
        self.rpc = rpc

    @property
    def pubkey(self) -> str:
        return str(self.kp.pubkey())

    def fit_cu_limit(self, texts: list[str], blockhash: str) -> int:
        """Simulate at MAX_CU (free) and size the limit to measured use + headroom. Raises if it fails."""
        sim = self.rpc.simulate_transaction(
            base64.b64encode(bytes(build_memo_tx(self.kp, texts, blockhash, MAX_CU))).decode())
        if sim.get("err") is not None:
            raise RpcError(f"memo tx simulation failed: {sim['err']} {(sim.get('logs') or [])[-2:]}")
        units = int(sim.get("unitsConsumed") or 0)
        if units <= 0:
            raise RpcError("simulation reported no compute units")
        return min(MAX_CU, int(units * CU_HEADROOM) + 2_000)

    def post(self, texts: list[str]) -> Posted:
        bh = self.rpc.get_latest_blockhash()
        tx = build_memo_tx(self.kp, texts, bh, self.fit_cu_limit(texts, bh))
        sig = self.rpc.send_transaction(base64.b64encode(bytes(tx)).decode())
        if sig != str(tx.signatures[0]):
            raise RpcError("RPC returned a different signature than we signed")
        return Posted(sig, self.rpc.confirm(sig))

    def required_lamports(self, n_txs: int) -> int:
        """Balance needed to send n_txs memo txs and stay rent-exempt (the runtime rejects anything less).
        Uses the live rent minimum and the live fee of a real memo tx signed by this notary."""
        probe = build_memo_tx(self.kp, [memos.commit(self.pubkey, 1, "00" * 32, 0)], self.rpc.get_latest_blockhash())
        fee = self.rpc.get_fee_for_message(base64.b64encode(bytes(probe.message)).decode())
        return self.rpc.get_min_rent(0) + n_txs * fee

    def assert_funded(self, n_txs: int) -> None:
        need, have = self.required_lamports(n_txs), self.rpc.get_balance(self.pubkey)
        if have < need:
            raise RpcError(f"notary {self.pubkey} has {have} lamports; needs {need} for {n_txs} memo tx(s)")

    def simulate(self, texts: list[str]) -> dict:
        """Dry run of exactly what post() would send: fitted CU limit, real fee. Sends nothing."""
        bh = self.rpc.get_latest_blockhash()
        try:
            limit = self.fit_cu_limit(texts, bh)
        except RpcError as e:
            return {"err": str(e)}
        tx = build_memo_tx(self.kp, texts, bh, limit)
        sim = self.rpc.simulate_transaction(base64.b64encode(bytes(tx)).decode())
        sim["cu_limit"] = limit
        sim["tx_bytes"] = len(bytes(tx))
        sim["fee_lamports"] = self.rpc.get_fee_for_message(base64.b64encode(bytes(tx.message)).decode())
        return sim

    # --- oath1 events ---------------------------------------------------------

    def commit(self, agent: str, seq: int, digest: str, bond_amt: int = 0) -> Posted:
        return self.post([memos.commit(agent, seq, digest, bond_amt)])

    def blocked(self, agent: str, seq: int, digest: str, reason_code: str) -> Posted:
        return self.post([memos.blocked(agent, seq, digest, reason_code)])

    def slash(self, agent: str, seq: int, reason: str) -> Posted:
        return self.post([memos.slash(agent, seq, reason)])

    def open(self, agent: str, seq: int, swap_sig: str) -> Posted:
        return self.post([memos.open_(agent, seq, swap_sig)])

    def reveal(self, agent: str, seq: int, salt: bytes, exit_sig: str, exit_reason: str,
               canonical: bytes) -> Posted:
        # Thesis rides in the same tx so verification needs zero trust in our API.
        return self.post([memos.reveal(agent, seq, salt.hex(), exit_sig, exit_reason),
                          memos.thesis(seq, canonical)])
