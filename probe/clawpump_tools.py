"""Phase 0 probe: list ClawPump MCP tools + schemas and exercise READ-ONLY tools.

Usage:  uv run python probe/clawpump_tools.py
Moves no funds. The only fund-moving probe is probe/swap_test.py.
"""
from __future__ import annotations

import asyncio

from _common import clawpump_session, decode_result, save

# Tools the spec relies on (§2.4) plus the ones the enforcement hook must cover (§5.2).
SPEC_TOOLS = [
    "swap_quote", "swap_execute", "get_price", "get_portfolio", "agent_balance",
    "token_search", "intelligence_market", "intelligence_signals", "get_market_signals",
    "fee_earnings", "get_wallet_history",
    "perps_order_execute", "agent_send", "wallet_transfer", "dca_create",
    "limit_order_create", "predictions_open",
]

READ_CALLS = [
    ("get_account_status", {}),
    ("list_agents", {}),
    ("get_portfolio", {}),
    ("get_price", {"tokens": "SOL,USDC"}),
    ("swap_quote", {"input_mint": "USDC", "output_mint": "SOL", "amount": "1000000"}),
    ("get_wallet_history", {}),
    ("perps_account", {}),
    ("perps_markets", {}),
    ("token_search", {"query": "ANSEM"}),
    ("intelligence_market", {"token": "SOL"}),
    ("get_whitelist", {}),
]


async def main() -> None:
    async with clawpump_session() as s:
        listed = await s.list_tools()
        tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.inputSchema,
                "annotations": t.annotations.model_dump() if t.annotations else None,
            }
            for t in listed.tools
        ]
        names = {t["name"] for t in tools}
        destructive = sorted(
            t["name"] for t in tools
            if (t["annotations"] or {}).get("destructiveHint")
        )
        save("clawpump_tools", {"count": len(tools), "tools": tools})
        save("spec_tool_presence", {
            "present": sorted(n for n in SPEC_TOOLS if n in names),
            "missing": sorted(n for n in SPEC_TOOLS if n not in names),
            "destructive_hint_tools": destructive,
        })
        print(f"[probe] {len(tools)} tools; missing from spec list: "
              f"{sorted(n for n in SPEC_TOOLS if n not in names)}")

        results = {}
        for name, args in READ_CALLS:
            if name not in names:
                results[name] = {"skipped": "tool not listed"}
                continue
            try:
                res = await s.call_tool(name, args)
                results[name] = {"args": args, **decode_result(res)}
            except Exception as e:  # record, keep probing
                results[name] = {"args": args, "exception": repr(e)}
            flag = "ERR" if results[name].get("is_error") or "exception" in results[name] else "ok"
            print(f"[probe] {name:22s} {flag}")
        save("read_calls", results)


if __name__ == "__main__":
    asyncio.run(main())
