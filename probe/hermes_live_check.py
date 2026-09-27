"""Phase 0: verify the REAL Hermes config (~/.hermes) exposes only read-only ClawPump tools.

Run with Hermes's interpreter:
  ~/.hermes/hermes-agent/venv/Scripts/python.exe probe/hermes_live_check.py
Moves no funds: only calls get_portfolio through the model's dispatch path.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

PROBE_DIR = Path(__file__).resolve().parent
HERMES_SRC = Path.home() / ".hermes" / "hermes-agent"
os.environ.setdefault("HERMES_HOME", str(Path.home() / ".hermes"))
sys.path.insert(0, str(HERMES_SRC))
sys.path.insert(0, str(PROBE_DIR))
os.chdir(HERMES_SRC)

from _common import scrub  # noqa: E402
from model_tools import handle_function_call  # noqa: E402
from tools.mcp_tool import discover_mcp_tools  # noqa: E402

# Anything outside this set reaching the model's registry is a config failure.
ALLOWED = {
    "get_price", "swap_quote", "token_search", "get_portfolio", "get_wallet_history",
    "get_market_signals", "get_indicators", "get_news_feed", "intelligence_capabilities",
    "intelligence_market", "intelligence_signals", "intelligence_macro", "list_agents",
    "get_agent",
}
# MCP resource/prompt helpers Hermes adds per server; they cannot move funds.
UTILITY = {"list_resources", "read_resource", "list_prompts", "get_prompt"}

registered = sorted(n for n in discover_mcp_tools() if "clawpump" in n)
suffixes = {n.rsplit("__", 1)[-1] for n in registered}
unexpected = sorted(n for n in registered if n.rsplit("__", 1)[-1] not in ALLOWED | UTILITY)
remote = [n for n in registered if n.startswith("mcp__clawpump__")]

raw = handle_function_call("mcp__clawpump_stdio__get_portfolio", {}, task_id="probe")
try:
    portfolio = json.loads(raw)
except json.JSONDecodeError:
    portfolio = raw

report = {
    "date": dt.datetime.now(dt.timezone.utc).isoformat(),
    "registered_clawpump_tools": registered,
    "allowed_missing": sorted(ALLOWED - suffixes),
    "unexpected_tools_exposed": unexpected,
    "remote_clawpump_tools_exposed": remote,
    "get_portfolio_via_hermes": portfolio,
    "pass": not unexpected and not remote and "error" not in str(raw)[:200].lower(),
}
out = PROBE_DIR / f"{dt.date.today():%Y-%m-%d}_hermes_live_check.json"
out.write_text(json.dumps(scrub(report), indent=2, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "get_portfolio_via_hermes"}, indent=2))
print("portfolio:", str(raw)[:300])
sys.stdout.flush()
os._exit(0)
