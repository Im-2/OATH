"""Phase 2: the OATH plugin inside the REAL Hermes (~/.hermes), via the model's dispatch path.

Run with Hermes's interpreter:
  ~/.hermes/hermes-agent/venv/Scripts/python.exe probe/hermes_plugin_check.py
Moves no funds and posts no memos: the only oath_open_position call is deliberately malformed
(empty `why`), which is refused after the read-only wallet check + quote, before any memo or swap.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

PROBE_DIR = Path(__file__).resolve().parent
HERMES_SRC = Path.home() / ".hermes" / "hermes-agent"
os.environ["HERMES_HOME"] = str(Path.home() / ".hermes")
sys.path.insert(0, str(HERMES_SRC))
sys.path.insert(0, str(PROBE_DIR))
os.chdir(HERMES_SRC)

from _common import scrub  # noqa: E402
from hermes_cli.plugins import discover_plugins  # noqa: E402
from model_tools import handle_function_call  # noqa: E402
from tools.mcp_tool import discover_mcp_tools  # noqa: E402
from tools.registry import registry  # noqa: E402

discover_plugins(force=True)
mcp_tools = sorted(n for n in discover_mcp_tools() if "clawpump" in n)
all_tools = sorted(registry.get_all_tool_names()) if hasattr(registry, "get_all_tool_names") else []


def call(name, args):
    raw = handle_function_call(name, args, task_id="oath-phase2-check")
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw


def blocked(res) -> bool:
    return isinstance(res, dict) and "OATH:" in str(res.get("error", ""))


cases = {
    "direct swap_execute (stdio prefix)": call("mcp__clawpump_stdio__swap_execute",
                                               {"input_mint": "USDC", "output_mint": "SOL", "amount": "1000000"}),
    "direct swap_execute (remote prefix)": call("mcp__clawpump__swap_execute",
                                                {"input_mint": "USDC", "output_mint": "SOL", "amount": "1000000"}),
    "direct wallet_transfer": call("mcp__clawpump_stdio__wallet_transfer",
                                   {"to": "FhpJ6i5oaBiCpNJasksf2qBgFmTv6ikgSUuqDzSBiUod", "amount": "0.1",
                                    "confirm_transfer": True}),
    "terminal with trade endpoint (harmless echo)": call("terminal", {"command": "echo swap/execute"}),
    "read tool get_price (must pass)": call("mcp__clawpump_stdio__get_price", {"tokens": "SOL"}),
    "oath_policy": call("oath_policy", {}),
    "oath_status": call("oath_status", {}),
    "oath_open_position malformed (must refuse, no memo)": call("oath_open_position", {
        "size_usd": "1.00", "entry": "market", "stop_pct": "3", "tp_pct": "5", "horizon_min": 60,
        "conf": "0.6", "strat": "probe", "why": ""}),
}


report = {
    "date": dt.datetime.now(dt.timezone.utc).isoformat(),
    "oath_tools_registered": [t for t in ("oath_open_position", "oath_status", "oath_policy")
                              if t in all_tools] if all_tools else "registry listing unavailable",
    "clawpump_tools_exposed_to_model": mcp_tools,
    "cases": cases,
    "checks": {
        "swap_execute_blocked_stdio": blocked(cases["direct swap_execute (stdio prefix)"]),
        "swap_execute_blocked_remote": blocked(cases["direct swap_execute (remote prefix)"]),
        "wallet_transfer_blocked": blocked(cases["direct wallet_transfer"]),
        "terminal_sensitive_blocked": blocked(cases["terminal with trade endpoint (harmless echo)"]),
        "get_price_passes": not blocked(cases["read tool get_price (must pass)"]),
        "oath_policy_works": isinstance(cases["oath_policy"], dict) and "max_trade_usd" in cases["oath_policy"],
        "oath_status_works": isinstance(cases["oath_status"], dict) and "totals" in cases["oath_status"],
        "open_refused_before_chain": "refused" in str(cases["oath_open_position malformed (must refuse, no memo)"]),
    },
}
report["pass"] = all(report["checks"].values())
out = PROBE_DIR / f"{dt.date.today():%Y-%m-%d}_phase2_hermes_check.json"
out.write_text(json.dumps(scrub(report), indent=2, default=str), encoding="utf-8")
print(json.dumps({k: report[k] for k in ("oath_tools_registered", "checks", "pass")}, indent=2))
sys.stdout.flush()
os._exit(0)
