"""ONE-OFF (2026-09-27, second funding), operator-run, not model-facing.

Send exactly 24,000 lamports (0.000024 SOL) from the agent wallet to the notary, for the Phase 2
exit test: commit + open + reveal (18,000) + room for one blocked memo (6,000).

  uv run python scripts/oneoff_fund_notary_2026-09-27b.py --plan   # live numbers, sends nothing
  uv run python scripts/oneoff_fund_notary_2026-09-27b.py          # asks "yes" before EVERY step

Steps: whitelist add -> transfer -> whitelist remove. Each ClawPump reply is saved to probe/ as
soon as it arrives. Replies may be JSON or plain text (oath_core.clawpump.decode returns plain text
as {"text": ...}), so nothing here assumes a field exists: every outcome is checked on-chain or by
re-reading the whitelist.
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
from oath_core.config import NOTARY_PATH, is_signature, load_config  # noqa: E402
from oath_core.executor import assert_agent_wallet  # noqa: E402
from oath_core.keys import load_keypair  # noqa: E402
from oath_core.solana_rpc import Rpc  # noqa: E402

AMOUNT_LAMPORTS = 24_000
MAX_FEE = 105_000  # highest ClawPump-sent tx fee observed, lamports
PROBE = Path(__file__).resolve().parent.parent / "probe"


def sol(lamports: int) -> str:
    return f"{Decimal(lamports).scaleb(-9):f}"


def save(name: str, payload) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    path = PROBE / f"{stamp}_fund_notary_{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"  saved {path.name}")


def confirm(prompt: str) -> bool:
    ans = input(f"\n>>> {prompt}\n    Type 'yes' to proceed, anything else to skip: ").strip()
    return ans == "yes"


def reply_text(resp) -> str:
    """Human-readable form of a JSON or plain-text ClawPump reply."""
    if isinstance(resp, dict) and set(resp) == {"text"}:
        return resp["text"]
    return json.dumps(resp, default=str)[:300]


def on_whitelist(cp, cfg, address: str) -> bool:
    wl = cp.call("get_whitelist", {"agent_id": cfg.agent_id})
    return address in json.dumps(wl)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="print live numbers only; send nothing")
    plan_only = ap.parse_args().plan

    cfg = load_config()
    rpc = Rpc(cfg.effective_rpc_url)
    notary = str(load_keypair(NOTARY_PATH).pubkey())
    agent = cfg.agent_wallet
    rent0, rent165 = rpc.get_min_rent(0), rpc.get_min_rent(165)
    reserve_2_swaps = rent0 + rent165 + 2 * MAX_FEE

    agent_bal = rpc.get_balance(agent)
    notary_bal = rpc.get_balance(notary)
    after = agent_bal - AMOUNT_LAMPORTS - MAX_FEE
    print(f"agent  {agent}: {agent_bal} lamports ({sol(agent_bal)} SOL)")
    print(f"notary {notary}: {notary_bal} lamports -> {notary_bal + AMOUNT_LAMPORTS} after transfer")
    print(f"transfer: {AMOUNT_LAMPORTS} lamports = {sol(AMOUNT_LAMPORTS)} SOL")
    print(f"agent after (worst-case fee): ~{after}; reserve for 2 swaps: {reserve_2_swaps} "
          f"(rent {rent0} + temp wSOL rent {rent165} + 2 x {MAX_FEE})")
    if after < reserve_2_swaps:
        print("REFUSED: the agent would not keep enough SOL for 2 swaps")
        return 1
    if plan_only:
        return 0

    with StdioClawPump() as cp:
        assert_agent_wallet(cp, cfg)

        # ---- 1. whitelist add -------------------------------------------------------------
        if on_whitelist(cp, cfg, notary):
            print("\nnotary already on the whitelist")
        elif confirm(f"STEP 1/3: add notary {notary} to agent {cfg.agent_id}'s transfer whitelist?"):
            resp = cp.call("add_to_whitelist", {"agent_id": cfg.agent_id, "address": notary, "label": "OATH notary"})
            save("whitelist_add", {"response": resp})
            print(f"  reply: {reply_text(resp)}")
            if not on_whitelist(cp, cfg, notary):
                print("  STOP: notary is not on the whitelist after add; nothing was transferred")
                return 1
        else:
            print("  skipped; the transfer needs the whitelist entry. Nothing was changed.")
            return 1

        # ---- 2. transfer ------------------------------------------------------------------
        transferred = False
        if confirm(f"STEP 2/3: transfer {sol(AMOUNT_LAMPORTS)} SOL ({AMOUNT_LAMPORTS} lamports) "
                   f"from agent {agent} to notary {notary}?"):
            before = rpc.get_balance(notary)
            try:
                resp = cp.call("wallet_transfer", {"agent_id": cfg.agent_id, "to": notary,
                                                   "amount": sol(AMOUNT_LAMPORTS), "token": "SOL",
                                                   "confirm_transfer": True})
            except Exception as e:  # noqa: BLE001 - it may still have landed: the balance check below decides
                resp = {"exception": repr(e)[:500]}
            save("transfer_response", {"lamports": AMOUNT_LAMPORTS, "response": resp})
            print(f"  reply: {reply_text(resp)}")
            sig = resp.get("txHash") if isinstance(resp, dict) else None
            deadline = time.time() + 90
            while time.time() < deadline and rpc.get_balance(notary) < before + AMOUNT_LAMPORTS:
                time.sleep(3)
            now_bal = rpc.get_balance(notary)
            got = now_bal - before
            check = {"notary_before": before, "notary_after": now_bal, "received": got, "tx": sig}
            if sig and is_signature(sig):
                tx = rpc.get_transaction(sig)
                if tx:
                    keys = [k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
                    i = keys.index(notary) if notary in keys else None
                    check.update(tx_err=tx["meta"]["err"], tx_fee=tx["meta"]["fee"],
                                 tx_notary_delta=(tx["meta"]["postBalances"][i] - tx["meta"]["preBalances"][i])
                                 if i is not None else None)
            save("transfer_chain_check", check)
            transferred = got == AMOUNT_LAMPORTS
            print(f"  on-chain: notary received {got} lamports (expected {AMOUNT_LAMPORTS}): "
                  f"{'OK' if transferred else 'MISMATCH - check before trading'}")
        else:
            print("  skipped transfer")

        # ---- 3. whitelist remove (runs even if the transfer was skipped or mismatched) -----
        if confirm(f"STEP 3/3: remove notary {notary} from the agent's transfer whitelist? (recommended)"):
            try:
                resp = cp.call("remove_from_whitelist", {"agent_id": cfg.agent_id, "address": notary})
                save("whitelist_remove", {"response": resp})
                print(f"  reply: {reply_text(resp)}")
            except Exception as e:  # noqa: BLE001 - verify below either way
                print(f"  remove call raised: {e!r}")
            still = on_whitelist(cp, cfg, notary)
            print(f"  whitelist re-read: notary {'STILL LISTED - remove it manually' if still else 'removed'}")
        else:
            print("  left notary on the whitelist; remove later with remove_from_whitelist")

    print(f"\nnotary final balance: {rpc.get_balance(notary)} lamports")
    return 0 if transferred else 1


if __name__ == "__main__":
    sys.exit(main())
