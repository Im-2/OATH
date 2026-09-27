"""Phase 0 probe: ONE $1 USDC -> SOL swap on MAINNET via ClawPump swap_execute.

Usage:  uv run python probe/swap_test.py --confirm
        uv run python probe/swap_test.py --dry-run   # all pre-swap checks, no swap

Records exactly what swap_execute returns (signature? fill amounts?), then
independently reads the transaction from Solana RPC. Amount is hard-capped at
1 USDC; there is no flag to raise it. Fails closed if the quote can't be read.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import re
import time

import httpx

from _common import clawpump_session, decode_result, save

# From @clawpump/agents WELL_KNOWN_MINTS (verified against the package source).
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL = "So11111111111111111111111111111111111111112"
AMOUNT_USDC_UNITS = "1000000"  # 1.000000 USDC, hard cap
# Agent "OATH" from list_agents (probe/2026-09-27_read_calls.json).
AGENT_ID = "2b9abb41-60e1-4b62-b1ec-ce772445003e"
AGENT_WALLET = "9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY"
SLIPPAGE_BPS = 100
RPC = "https://api.mainnet-beta.solana.com"
_SIG_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{86,88}$")


def find_signatures(obj, path="$"):
    """Yield (json_path, value) for every string that looks like a Solana tx signature."""
    if isinstance(obj, str) and _SIG_RE.match(obj):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from find_signatures(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from find_signatures(v, f"{path}[{i}]")


def rpc_get_tx(sig: str, tries: int = 10) -> dict | None:
    body = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed", "commitment": "confirmed",
                         "maxSupportedTransactionVersion": 0}],
    }
    for _ in range(tries):
        r = httpx.post(RPC, json=body, timeout=20).json()
        if r.get("result"):
            return r["result"]
        time.sleep(3)
    return None


def summarize_tx(tx: dict) -> dict:
    meta = tx["meta"]
    keys = tx["transaction"]["message"]["accountKeys"]
    signers = [k["pubkey"] for k in keys if k.get("signer")]
    def bal(entries):
        return {(b["owner"], b["mint"]): b["uiTokenAmount"]["amount"] for b in entries or []}
    pre, post = bal(meta.get("preTokenBalances")), bal(meta.get("postTokenBalances"))
    deltas = {}
    for k in set(pre) | set(post):
        d = int(post.get(k, "0")) - int(pre.get(k, "0"))
        if d:
            deltas[f"{k[0]}|{k[1]}"] = d
    fee_payer_idx = 0
    sol_delta = meta["postBalances"][fee_payer_idx] - meta["preBalances"][fee_payer_idx]
    return {
        "slot": tx["slot"], "block_time": tx.get("blockTime"), "err": meta.get("err"),
        "fee_lamports": meta["fee"], "signers": signers,
        "fee_payer_native_sol_delta_lamports": sol_delta,
        "token_balance_deltas_raw_units": deltas,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="actually execute the 1 USDC swap")
    ap.add_argument("--dry-run", action="store_true", help="run pre-swap checks only")
    args = ap.parse_args()
    if args.confirm == args.dry_run:
        raise SystemExit("Pass exactly one of --dry-run or --confirm "
                         "(--confirm executes a real 1 USDC -> SOL mainnet swap).")

    record: dict = {"started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "request": {"agent_id": AGENT_ID, "input_mint": USDC, "output_mint": SOL,
                                "amount": AMOUNT_USDC_UNITS, "slippage_bps": SLIPPAGE_BPS}}
    async with clawpump_session() as s:
        agent = decode_result(await s.call_tool("get_agent", {"agent_id": AGENT_ID}))
        wallet = (agent.get("data") or {}).get("wallet_address") or (agent.get("data") or {}).get("wallet")
        if agent["is_error"] or wallet != AGENT_WALLET:
            record["agent_check"] = agent
            save("swap_test", record)
            raise SystemExit(f"Agent wallet check failed (got {wallet!r}); not executing (fail closed).")
        record["portfolio_before"] = decode_result(
            await s.call_tool("get_portfolio", {"agent_id": AGENT_ID}))

        quote = decode_result(await s.call_tool("swap_quote", record["request"]))
        record["quote"] = quote
        if quote["is_error"] or "data" not in quote:
            save("swap_test", record)
            raise SystemExit("Quote failed or unreadable; not executing (fail closed).")
        if args.dry_run:
            print(f"[dry-run] agent wallet OK: {wallet}")
            print(f"[dry-run] USDC before: {record['portfolio_before'].get('data', {}).get('usdc_balance')}")
            print(f"[dry-run] quote out: {quote['data'].get('output')}")
            print("[dry-run] all pre-swap checks passed; swap_execute NOT called.")
            return

        t0 = time.time()
        raw = await s.call_tool("swap_execute", record["request"])
        record["swap_execute_latency_s"] = round(time.time() - t0, 2)
        record["swap_execute_response"] = decode_result(raw)
        print(f"[swap] is_error={raw.isError} latency={record['swap_execute_latency_s']}s")
        save("swap_test_partial", record)  # persist before anything else can fail

        await asyncio.sleep(5)
        record["portfolio_after"] = decode_result(
            await s.call_tool("get_portfolio", {"agent_id": AGENT_ID}))
        record["wallet_history_after"] = decode_result(
            await s.call_tool("get_wallet_history", {"agent_id": AGENT_ID}))

    sigs = list(find_signatures(record["swap_execute_response"]))
    record["signature_candidates_in_response"] = [{"path": p, "sig": v} for p, v in sigs]
    if sigs:
        tx = rpc_get_tx(sigs[0][1])
        record["onchain"] = summarize_tx(tx) if tx else {"error": "not found on RPC after retries"}
    else:
        record["onchain"] = {"error": "swap_execute response contained no signature-shaped string"}
    save("swap_test", record)
    print(f"[swap] signature(s) in response: {[v for _, v in sigs] or 'NONE'}")
    print(f"[swap] onchain: {record['onchain']}")


if __name__ == "__main__":
    asyncio.run(main())
