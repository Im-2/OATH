"""ONE-OFF (2026-09-28), operator-run, not model-facing: fund the $OATH token launch.

Swap exactly 1.2 USDC -> SOL in the agent wallet so it can pay the ~0.012 SOL launch fee from the
ClawPump dashboard, then disclose the swap on-chain as operator housekeeping (oath1:h memo), so
verify lists it as a disclosed operator action instead of an "uncommitted trade".

  uv run python scripts/oneoff_swap_for_launch_2026-09-28.py --plan   # live numbers, sends nothing
  uv run python scripts/oneoff_swap_for_launch_2026-09-28.py          # asks "yes" before EACH step

Fill amounts come from the chain, never from ClawPump's response. Every reply is saved to probe/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oath_core.clawpump import StdioClawPump  # noqa: E402
from oath_core.config import NOTARY_PATH, SOL_MINT, USDC_MINT, is_signature, load_config  # noqa: E402
from oath_core.executor import assert_agent_wallet, quote  # noqa: E402
from oath_core.fills import compute_fill  # noqa: E402
from oath_core.keys import load_keypair  # noqa: E402
from oath_core.market import agent_balances  # noqa: E402
from oath_core.notary import Notary  # noqa: E402
from oath_core.present import amount  # noqa: E402
from oath_core.solana_rpc import Rpc  # noqa: E402

USDC_IN_RAW = 1_200_000            # exactly 1.2 USDC
LAUNCH_COST_LAMPORTS = 12_000_000  # ~0.012 SOL, per the operator
MAX_SWAP_FEE = 105_000
SLIPPAGE_BPS = 100
REASON = "fund_token_launch"
PROBE = Path(__file__).resolve().parent.parent / "probe"


def save(name: str, payload) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    path = PROBE / f"{stamp}_launch_swap_{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"  saved {path.name}")


def confirm(prompt: str) -> bool:
    return input(f"\n>>> {prompt}\n    Type 'yes' to proceed, anything else to skip: ").strip() == "yes"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="print live numbers only; send nothing")
    plan_only = ap.parse_args().plan

    cfg = load_config()
    rpc = Rpc(cfg.effective_rpc_url)
    notary = Notary(load_keypair(NOTARY_PATH), rpc)
    agent = cfg.agent_wallet
    lamports, usdc = agent_balances(rpc, agent)
    reserve_2_swaps = rpc.get_min_rent(0) + rpc.get_min_rent(165) + 2 * MAX_SWAP_FEE
    print(f"agent now: {amount(lamports, SOL_MINT)}, {amount(usdc, USDC_MINT)}")
    if usdc < USDC_IN_RAW:
        print(f"REFUSED: agent has {amount(usdc, USDC_MINT)} < {amount(USDC_IN_RAW, USDC_MINT)}")
        return 1

    with StdioClawPump() as cp:
        assert_agent_wallet(cp, cfg)
        q = quote(cp, cfg, USDC_MINT, SOL_MINT, USDC_IN_RAW, SLIPPAGE_BPS)
        after_swap = lamports + q.out_raw - MAX_SWAP_FEE
        after_launch = after_swap - LAUNCH_COST_LAMPORTS
        print(f"quote: {amount(USDC_IN_RAW, USDC_MINT)} -> {amount(q.out_raw, SOL_MINT)} "
              f"(venue {q.raw.get('venue')}, impact {q.raw.get('priceImpactPct')})")
        print(f"projected SOL after swap: ~{amount(after_swap, SOL_MINT)} (worst-case fee)")
        print(f"projected SOL after a {amount(LAUNCH_COST_LAMPORTS, SOL_MINT)} launch: ~{amount(after_launch, SOL_MINT)} "
              f"(OATH needs {amount(reserve_2_swaps, SOL_MINT)} for 2 swaps)")
        print(f"USDC left after swap: {amount(usdc - USDC_IN_RAW, USDC_MINT)}")
        need_memo = notary.required_lamports(1)
        print(f"notary: {rpc.get_balance(notary.pubkey)} lamports; disclosure memo needs {need_memo}")
        if plan_only:
            return 0

        # ---- 1. swap -------------------------------------------------------------------
        if not confirm(f"STEP 1/2: swap {amount(USDC_IN_RAW, USDC_MINT)} -> SOL in agent wallet {agent}?"):
            print("  skipped; nothing sent")
            return 1
        try:
            resp = cp.call("swap_execute", {"agent_id": cfg.agent_id, "input_mint": USDC_MINT, "output_mint": SOL_MINT,
                                            "amount": str(USDC_IN_RAW), "slippage_bps": SLIPPAGE_BPS})
        except Exception as e:  # noqa: BLE001 - may still have landed; check the wallet before anything else
            save("swap_error", {"exception": repr(e)[:500]})
            print(f"  swap_execute raised: {e!r}. Check the agent wallet before retrying anything.")
            return 1
        save("swap_response", {"response": resp})
        sig = resp.get("txHash") if isinstance(resp, dict) else None
        if not is_signature(sig or ""):
            print(f"  no txHash in reply: {json.dumps(resp)[:300]}. Check the agent wallet before retrying.")
            return 1
        fill = compute_fill(rpc.wait_transaction(sig), sig, agent, USDC_MINT, SOL_MINT)
        new_lamports, new_usdc = agent_balances(rpc, agent)
        save("swap_fill", {"fill": fill.to_dict(), "agent_lamports_after": new_lamports, "agent_usdc_after": new_usdc})
        print(f"  on-chain: spent {amount(fill.in_raw, USDC_MINT)}, received {amount(fill.out_raw, SOL_MINT)}, "
              f"fee {amount(fill.fee_lamports, SOL_MINT)}; tx {sig}")
        print(f"  AGENT SOL BALANCE NOW: {amount(new_lamports, SOL_MINT)} ({new_lamports} lamports); "
              f"USDC {amount(new_usdc, USDC_MINT)}")

        # ---- 2. disclose on-chain -------------------------------------------------------
        if confirm(f"STEP 2/2: post notary memo oath1:h:{agent[:8]}...:{sig[:8]}...:{REASON} "
                   f"(6,000 lamports from the notary) so verify lists this swap as disclosed housekeeping?"):
            try:
                h = notary.housekeeping(agent, sig, REASON)
                save("disclosure", {"memo_sig": h.sig, "slot": h.slot, "swap_sig": sig, "reason": REASON})
                print(f"  disclosed: {h.sig}")
            except Exception as e:  # noqa: BLE001
                save("disclosure_error", {"exception": repr(e)[:500], "swap_sig": sig})
                print(f"  disclosure failed: {e!r}. Verify will flag {sig} until it is disclosed.")
        else:
            print(f"  not disclosed: verify will report {sig} as an uncommitted trade")
    return 0


if __name__ == "__main__":
    sys.exit(main())
