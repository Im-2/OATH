"""ONE-OFF (2026-09-27), operator-run, not model-facing: fund Phase 1 from the agent wallet.

ALREADY RUN 2026-09-27 ~15:43Z. DO NOT RE-RUN. All 4 steps succeeded (records:
probe/2026-09-27_1542*_rebalance_*.json, chain check probe/2026-09-27_rebalance_chain_check.json);
it crashed only after the final step, when remove_from_whitelist replied in plain text
(fixed in oath_core.clawpump.decode).

  uv run python scripts/oneoff_rebalance_2026-09-27.py --plan   # live numbers, sends nothing
  uv run python scripts/oneoff_rebalance_2026-09-27.py          # asks "yes" before EVERY action

Step 1  swap the SOL bought by the two Phase 0 swap tests back to USDC, keeping the
        agent's pre-test SOL (5,935,253 lamports) for fees.
Step 2  transfer exactly the notary's Phase 1 minimum from the agent wallet:
        rent-exempt minimum + 3 memo txs (commit, open, reveal), live rent and fee.
        Needs the notary on the agent's whitelist; you are asked to add it, and to remove
        it again afterwards.

Every live value is re-read right before its step. Records are saved to probe/ as soon
as a response arrives. This housekeeping happens before OATH seq 1 is committed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oath_core.clawpump import StdioClawPump  # noqa: E402
from oath_core.config import NOTARY_PATH, SOL_MINT, USDC_MINT, load_config  # noqa: E402
from oath_core.executor import assert_agent_wallet, quote  # noqa: E402
from oath_core.fills import compute_fill  # noqa: E402
from oath_core.keys import load_keypair  # noqa: E402
from oath_core.notary import Notary  # noqa: E402
from oath_core.solana_rpc import Rpc  # noqa: E402

PRE_TEST_LAMPORTS = 5_935_253      # agent SOL before the Phase 0 swap tests (probe/2026-09-27_read_calls.json)
TEST_SOL_GROSS = 8_219_635 + 8_226_769  # SOL the two tests bought (4RSqNho6…, 2yVvHjqB…)
MAX_SWAP_FEE = 105_000             # highest ClawPump swap fee observed, lamports
PROBE = Path(__file__).resolve().parent.parent / "probe"


def sol(lamports: int) -> str:
    return f"{Decimal(lamports).scaleb(-9):f}"


def save(name: str, payload) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    path = PROBE / f"{stamp}_rebalance_{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"  saved {path.name}")


def confirm(prompt: str) -> bool:
    ans = input(f"\n>>> {prompt}\n    Type 'yes' to proceed, anything else to skip: ").strip()
    return ans == "yes"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="print live numbers only; send nothing")
    plan_only = ap.parse_args().plan
    cfg = load_config()
    rpc = Rpc(cfg.effective_rpc_url)
    notary = Notary(load_keypair(NOTARY_PATH), rpc)
    agent = cfg.agent_wallet
    rent0, rent165 = rpc.get_min_rent(0), rpc.get_min_rent(165)
    reserve_2_swaps = rent0 + rent165 + 2 * MAX_SWAP_FEE

    with StdioClawPump() as cp:
        assert_agent_wallet(cp, cfg)

        # ---- step 1: swap test SOL back to USDC --------------------------------------------
        bal = rpc.get_balance(agent)
        amount = bal - PRE_TEST_LAMPORTS
        print(f"\nSTEP 1  agent SOL {sol(bal)}; keep {sol(PRE_TEST_LAMPORTS)}; swap {sol(amount)} SOL -> USDC")
        if not (0 < amount <= TEST_SOL_GROSS):
            print(f"  REFUSED: {amount} lamports is not within the SOL the tests bought ({TEST_SOL_GROSS})")
            return 1
        wrap_need = amount + rent165 + rent0 + MAX_SWAP_FEE
        if bal < wrap_need:
            print(f"  REFUSED: selling {amount} needs {wrap_need} lamports on hand (wSOL rent + fee)")
            return 1
        q = quote(cp, cfg, SOL_MINT, USDC_MINT, amount)
        print(f"  quote: {sol(amount)} SOL -> {Decimal(q.out_raw).scaleb(-6):f} USDC "
              f"(impact {q.raw.get('priceImpactPct')}, venue {q.raw.get('venue')}, slippage {cfg.slippage_bps} bps)")
        swapped = False
        if not plan_only and confirm(f"Swap {amount} lamports ({sol(amount)} SOL) -> USDC from agent {agent}?"):
            resp = cp.call("swap_execute", {"agent_id": cfg.agent_id, "input_mint": SOL_MINT,
                                            "output_mint": USDC_MINT, "amount": str(amount),
                                            "slippage_bps": cfg.slippage_bps})
            save("swap_response", {"request_lamports": amount, "response": resp})
            sig = resp.get("txHash")
            fill = compute_fill(rpc.wait_transaction(sig), sig, agent, SOL_MINT, USDC_MINT)
            save("swap_fill", fill.to_dict())
            print(f"  on-chain: sold {sol(fill.in_raw)} SOL, received {Decimal(fill.out_raw).scaleb(-6):f} USDC, "
                  f"fee {fill.fee_lamports} lamports, tx {sig}")
            swapped = True
        elif not plan_only:
            print("  skipped step 1")

        # ---- step 2: fund the notary with exactly the Phase 1 minimum ----------------------
        need = notary.required_lamports(3)
        have = rpc.get_balance(notary.pubkey)
        amt = need - have
        # In --plan (or if step 1 was skipped) project the post-swap balance; otherwise use the live one.
        projected = rpc.get_balance(agent) if swapped else PRE_TEST_LAMPORTS - MAX_SWAP_FEE
        after = projected - max(amt, 0) - MAX_SWAP_FEE
        print(f"\nSTEP 2  notary needs {need} lamports = rent-exempt {rent0} + 3 memo txs; has {have}")
        print(f"  transfer: {max(amt, 0)} lamports = {sol(max(amt, 0))} SOL")
        print(f"  agent after transfer (worst-case fees): ~{after} lamports; reserve for 2 swaps: {reserve_2_swaps} "
              f"(rent {rent0} + temp wSOL rent {rent165} + 2 x {MAX_SWAP_FEE} fee)")
        if amt <= 0:
            print("  notary already funded; nothing to transfer")
            return 0
        if after < reserve_2_swaps:
            print("  REFUSED: the agent would not keep enough SOL for 2 swaps")
            return 1
        if plan_only:
            return 0

        wl = cp.call("get_whitelist", {"agent_id": cfg.agent_id})
        on_wl = notary.pubkey in json.dumps(wl)
        if not on_wl:
            if not confirm(f"Add notary {notary.pubkey} to agent {cfg.agent_id}'s transfer whitelist "
                           f"(required by wallet_transfer)?"):
                print("  skipped: transfer needs the whitelist entry")
                return 1
            save("whitelist_add", cp.call("add_to_whitelist", {"agent_id": cfg.agent_id, "address": notary.pubkey,
                                                               "label": "OATH notary"}))
        amount_ui = sol(amt)
        if confirm(f"Transfer {amount_ui} SOL ({amt} lamports) from agent {agent} to notary {notary.pubkey}?"):
            resp = cp.call("wallet_transfer", {"agent_id": cfg.agent_id, "to": notary.pubkey, "amount": amount_ui,
                                               "token": "SOL", "confirm_transfer": True})
            save("transfer_response", {"lamports": amt, "amount_ui": amount_ui, "response": resp})
            deadline = time.time() + 90
            while time.time() < deadline and rpc.get_balance(notary.pubkey) < need:
                time.sleep(3)
            now_have = rpc.get_balance(notary.pubkey)
            print(f"  notary balance now {now_have} lamports (needs {need}): {'OK' if now_have >= need else 'SHORT'}")
        else:
            print("  skipped transfer")
        if confirm(f"Remove notary {notary.pubkey} from the agent's transfer whitelist again? (recommended)"):
            save("whitelist_remove", cp.call("remove_from_whitelist", {"agent_id": cfg.agent_id,
                                                                       "address": notary.pubkey}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
