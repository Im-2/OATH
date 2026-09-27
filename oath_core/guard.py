"""pre_tool_call policy (SPEC §5.2 layer 2). Pure so it can be unit-tested without Hermes.

1. Any ClawPump tool (any server prefix mcp__clawpump*) whose suffix is not on the read
   allowlist is blocked: default-deny, so new ClawPump tools stay blocked until reviewed.
2. Any other non-OATH tool whose arguments reference trading credentials or trade endpoints
   is blocked (heuristic defence-in-depth for terminal/file/web tools; the real control is
   running the trading agent with `-t oath,mcp-clawpump-stdio`).
The executor's own swaps go through ctx.call_mcp, which never reaches this hook (Phase 0).
"""
from __future__ import annotations

import json

READ_ALLOWLIST = frozenset({
    "get_price", "swap_quote", "token_search", "get_portfolio", "get_wallet_history",
    "get_market_signals", "get_indicators", "get_news_feed", "intelligence_capabilities",
    "intelligence_market", "intelligence_signals", "intelligence_macro", "list_agents", "get_agent",
})
MCP_HELPERS = frozenset({"list_resources", "read_resource", "list_prompts", "get_prompt"})

# Known fund movers (Phase 0 + manifest). Default-deny already covers them; kept as a test fixture.
KNOWN_FUND_MOVERS = frozenset({
    "swap_execute", "perps_order_execute", "perps_collateral_deposit", "perps_collateral_withdraw",
    "perps_order_cancel", "perps_trader_register", "perps_account_prepare", "dca_create", "dca_cancel",
    "limit_order_create", "limit_order_cancel", "predictions_open", "predictions_close", "wallet_transfer",
    "set_external_wallet", "add_to_whitelist", "remove_from_whitelist", "place_bid", "accept_marketplace_bid",
    "withdraw_marketplace_bid", "x402_pay", "pay_sh_execute_approved", "usepod_deposit", "usepod_provision",
    "agent_card_create", "agent_card_withdraw", "launch_token_gasless", "launch_metaplex_genesis_token",
    "chat_with_agent", "create_agent_run", "trigger_automation", "create_automation", "update_agent",
})

SENSITIVE_PATTERNS = (
    ".oath", "notary.json", "escrow.json", "ledger.db", "cpk_", "clawpump_api_key",
    ".hermes/.env", ".hermes\\\\.env", ".hermes\\.env", "swap_execute", "swap/execute", "wallet_transfer",
    "wallet/transfer", "oath_core", "oath_server", "@clawpump/agents", "ai-agents-production",
    "clawpump-mcp-production", "mcp.clawpump.tech",
)

# Argument repair for read tools (Hermes `modify` directive). intelligence_market only resolves
# mint addresses: with the symbol "SOL" ClawPump returns "Bitget market info request failed."
# (seen live 2026-09-27); with the mint it returns full data.
SYMBOL_MINTS = {"SOL": "So11111111111111111111111111111111111111112",
                "WSOL": "So11111111111111111111111111111111111111112",
                "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"}
MINT_ONLY_TOOLS = {"intelligence_market": "token"}

BLOCK_TRADE = "OATH: trades must go through oath_open_position (commit first). This ClawPump tool is not available."
BLOCK_SENSITIVE = "OATH: this call references protected trading credentials or trade endpoints and is blocked."


def is_clawpump_tool(tool_name: str) -> bool:
    return tool_name.startswith("mcp__clawpump")


def suffix(tool_name: str) -> str:
    return tool_name.rsplit("__", 1)[-1]


def decide(tool_name: str, args) -> dict | None:
    """Return a Hermes block directive, or None to let the call through."""
    if not isinstance(tool_name, str):
        return {"action": "block", "message": BLOCK_TRADE}
    if is_clawpump_tool(tool_name):
        name = suffix(tool_name)
        if name not in READ_ALLOWLIST | MCP_HELPERS:
            return {"action": "block", "message": BLOCK_TRADE}
        field = MINT_ONLY_TOOLS.get(name)
        if field and isinstance(args, dict):
            val = str(args.get(field, "")).strip().lstrip("$").upper()
            if val in SYMBOL_MINTS:
                return {"action": "modify", "args": {field: SYMBOL_MINTS[val]}}
        return None
    if tool_name.startswith("oath_"):
        return None
    try:
        blob = json.dumps(args, default=str).lower()
    except (TypeError, ValueError):
        return {"action": "block", "message": BLOCK_SENSITIVE}
    if any(p in blob for p in SENSITIVE_PATTERNS):
        return {"action": "block", "message": BLOCK_SENSITIVE}
    return None
