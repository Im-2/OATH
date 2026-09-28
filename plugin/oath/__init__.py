"""OATH Hermes plugin (SPEC §5.1–5.2, §10).

Registers, in this order so a later failure can never leave trading unguarded:
  1. pre_tool_call hook  -> oath_core.guard.decide (default-deny for ClawPump fund movers)
  2. tools               -> oath_open_position, oath_stand_aside, oath_status, oath_policy
  3. system prompt rules + oath-trader skill + `hermes oath ...` CLI + /oath slash command

Trades execute via ctx.call_mcp("clawpump-stdio", "swap_execute", ...), which needs
plugins.entries.oath.mcp_allowlist: [clawpump-stdio] in ~/.hermes/config.yaml. That path
does not pass through pre_tool_call (Phase 0), so the model itself can never reach it.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

log = logging.getLogger("oath.plugin")
_HERE = Path(__file__).resolve().parent

RULES = """\
You trade through OATH (Proof-of-Thesis). Every trade you open is publicly committed on Solana
BEFORE it executes and revealed AFTER it closes; anyone can verify you did what you said.

Rules:
1. The ONLY way to open a position is the tool `oath_open_position`. All other trading, transfer,
   order and wallet-changing tools are blocked; do not try to work around this.
2. v1 is spot LONG only on SOL/USDC. Size must be <= the policy cap (see `oath_policy`).
3. Every thesis needs entry (or "market"), stop < entry < tp, horizon_min, conf in [0,1],
   a short strategy tag, and `why`: a structured reason code + short text (<=140 chars).
   Never put private reasoning in `why`; it is published on-chain.
4. You do NOT close positions. Deterministic code exits at your committed stop, take-profit or
   horizon and reveals your thesis. Choose stop/tp/horizon you are willing to be held to.
5. A firewall may BLOCK a thesis (size, stop distance, slippage, liquidity, drawdown, ...).
   A block is recorded on-chain and counts in your record. Do not immediately resubmit a
   tweaked thesis to get around a block; reassess or stand aside.
6. Not trading is a valid decision: when you stand aside, record it with `oath_stand_aside`.
   Use read-only market tools and `oath_status` first.
7. `strat: "acceptance_test"` is reserved for operator test mode. Use it only when `oath_status`
   shows test_mode.armed = true AND the user explicitly asks for an acceptance test.
Load the `oath:oath-trader` skill for the full strategy playbook.
"""

OPEN_SCHEMA = {
    "name": "oath_open_position",
    "description": (
        "Open a spot LONG position under OATH. Commits a salted hash of your thesis on Solana, "
        "passes the firewall, then executes the entry swap. The thesis is revealed on-chain when the "
        "position is closed by the monitor at stop, take-profit or horizon. Returns the commitment, "
        "the swap signature and the on-chain fill (amounts labelled in SOL / USDC; use fill.summary verbatim), "
        "or {blocked: true, reason} if the firewall refused."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mkt": {"type": "string", "enum": ["SOL/USDC"], "description": "Market (v1: SOL/USDC)"},
            "size_usd": {"type": "string", "description": "USD to spend, e.g. \"1.00\" (<= policy max_trade_usd)"},
            "entry": {"type": "string", "description": "Expected entry price in USDC per SOL, or \"market\""},
            "stop": {"type": "string", "description": "Absolute stop price (give stop OR stop_pct)"},
            "stop_pct": {"type": "string", "description": "Stop distance below entry in percent, e.g. \"3\""},
            "tp": {"type": "string", "description": "Absolute take-profit price (give tp OR tp_pct)"},
            "tp_pct": {"type": "string", "description": "Take-profit distance above entry in percent"},
            "horizon_min": {"type": "integer", "description": "Minutes until the position is closed at market"},
            "conf": {"type": "string", "description": "Confidence 0..1, e.g. \"0.60\""},
            "strat": {"type": "string", "description": "Strategy tag, [a-z0-9_-]{1,32}, e.g. trend_pullback"},
            "why": {"type": "string", "description": "REASON_CODE: short public justification (<=140 chars)"},
        },
        "required": ["size_usd", "entry", "horizon_min", "conf", "strat", "why"],
    },
}
STATUS_SCHEMA = {
    "name": "oath_status",
    "description": "Your OATH record: open positions, recent closed/blocked positions with P&L, and totals.",
    "parameters": {"type": "object", "properties": {}},
}
STAND_ASIDE_SCHEMA = {
    "name": "oath_stand_aside",
    "description": (
        "Record that you looked at the market and chose NOT to trade. Off-chain (no memo, no cost), shown on "
        "the public record as discipline. Call it whenever the playbook says stand aside."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mkt": {"type": "string", "enum": ["SOL/USDC"]},
            "reason_code": {"type": "string", "description": "e.g. INSUFFICIENT_SIGNALS, SIGNAL_AGAINST, OPEN_POSITION"},
            "why": {"type": "string", "description": "Short public explanation (<=280 chars)"},
            "evidence": {"type": "object", "description": "Signal readings you used, e.g. {\"sol_24h_pct\": 1.6, "
                                                           "\"sentiment\": \"neutral\", \"agreeing\": 1}"},
        },
        "required": ["reason_code", "why"],
    },
}
POLICY_SCHEMA = {
    "name": "oath_policy",
    "description": "Read-only view of the firewall policy (max trade size, stop bounds, limits).",
    "parameters": {"type": "object", "properties": {}},
}

_lock = threading.Lock()   # one open at a time: the model must not race two commitments
_state: dict = {}


class HermesClawPump:
    """oath_core ClawPump interface backed by ctx.call_mcp (bypasses pre_tool_call by design)."""

    def __init__(self, ctx, server: str):
        self._ctx, self._server = ctx, server

    def call(self, tool: str, args: dict):
        from oath_core.clawpump import ClawPumpError, decode

        env = self._ctx.call_mcp(self._server, tool, args, timeout=120 if tool == "swap_execute" else 45)
        if not env.get("ok"):
            raise ClawPumpError(f"{tool}: {str(env.get('error'))[:500]}")
        res = env.get("result")
        if isinstance(res, str):
            return decode(False, res, tool)
        return res if res is not None else {}


def _runtime(ctx):
    if "rt" not in _state:
        from oath_core.config import CLAWPUMP_SERVER, LEDGER_PATH, NOTARY_PATH, load_config
        from oath_core.executor import ExecTokens
        from oath_core.flow import Ctx
        from oath_core.keys import load_keypair
        from oath_core.ledger import Ledger
        from oath_core.notary import Notary
        from oath_core.solana_rpc import Rpc

        cfg = load_config()
        rpc = Rpc(cfg.effective_rpc_url)
        _state["rt"] = Ctx(cfg, rpc, Notary(load_keypair(NOTARY_PATH), rpc), Ledger(LEDGER_PATH),
                           HermesClawPump(ctx, CLAWPUMP_SERVER), ExecTokens())
    return _state["rt"]


def _json(obj) -> str:
    return json.dumps(obj, default=str)


def _make_open(ctx):
    def handler(params: dict, **kwargs) -> str:
        from oath_core.flow import FlowError, open_position
        from oath_core.present import present_open_result

        p = dict(params or {})
        try:
            with _lock:
                res = open_position(
                    _runtime(ctx), mkt=p.get("mkt", "SOL/USDC"), size_usd=p.get("size_usd"),
                    entry=p.get("entry"), stop=p.get("stop"), tp=p.get("tp"), stop_pct=p.get("stop_pct"),
                    tp_pct=p.get("tp_pct"), horizon_min=p.get("horizon_min"), conf=p.get("conf"),
                    strat=p.get("strat"), why=p.get("why"))
            return _json(present_open_result(res))  # labelled amounts: never raw lamports to the model
        except FlowError as e:
            return _json({"ok": False, "refused": str(e)})
        except Exception as e:  # noqa: BLE001 - report, never crash the agent loop
            log.exception("oath_open_position failed")
            return _json({"ok": False, "error": f"{type(e).__name__}: {str(e)[:400]}"})
    return handler


def record_stand_aside(ledger, params: dict, session_id: str | None = None) -> dict:
    """Validate and store a stand-aside decision. Bounded so a model can't bloat the ledger."""
    import re

    reason = str(params.get("reason_code", "")).strip().upper()
    why = str(params.get("why", "")).strip()
    mkt = str(params.get("mkt") or "SOL/USDC")
    if not re.fullmatch(r"[A-Z0-9_]{1,32}", reason):
        return {"ok": False, "refused": "reason_code must be [A-Z0-9_]{1,32}"}
    if not why or len(why) > 280:
        return {"ok": False, "refused": "why must be 1..280 chars"}
    if mkt != "SOL/USDC":
        return {"ok": False, "refused": "unsupported market"}
    evidence = params.get("evidence") or {}
    if not isinstance(evidence, dict):
        evidence = {"value": str(evidence)}
    evidence = {str(k)[:40]: (v if isinstance(v, (int, float, bool)) or v is None else str(v)[:120])
                for k, v in list(evidence.items())[:20]}
    rid = ledger.record_decision("stand_aside", mkt, reason, why, evidence, session_id)
    return {"ok": True, "recorded": "stand_aside", "id": rid, "on_chain": False}


def status_summary(ledger) -> dict:
    from decimal import Decimal

    from oath_core import testmode

    rows = ledger.positions()
    closed = [r for r in rows if r["status"] == "revealed" and r["pnl_usd"]]
    return {
        "open": [{"seq": r["seq"], "status": r["status"], "thesis": json.loads(r["thesis_json"]),
                  "swap_sig": r["swap_sig"]} for r in rows if r["status"] in ("committed", "open", "closed")],
        "recent": [{"seq": r["seq"], "status": r["status"], "exit_reason": r["exit_reason"],
                    "pnl_usd": r["pnl_usd"], "reveal_sig": r["reveal_sig"]} for r in rows[-10:]],
        "totals": {
            "positions": len(rows),
            "blocked": sum(1 for r in rows if r["status"] == "blocked"),
            "revealed": sum(1 for r in rows if r["status"] == "revealed"),
            "realised_pnl_usd": str(sum((Decimal(r["pnl_usd"]) for r in closed), Decimal(0))),
            "stand_asides": len(ledger.decisions(limit=100000)),
        },
        "recent_stand_asides": [{k: d[k] for k in ("ts", "reason_code", "why")} for d in ledger.decisions(limit=5)],
        "test_mode": {"armed": bool(testmode.status().get("armed"))},
    }


def _make_status(ctx):
    def handler(params: dict, **kwargs) -> str:
        try:
            return _json(status_summary(_runtime(ctx).ledger))
        except Exception as e:  # noqa: BLE001
            return _json({"ok": False, "error": f"{type(e).__name__}: {str(e)[:400]}"})
    return handler


def _make_stand_aside(ctx):
    def handler(params: dict, **kwargs) -> str:
        try:
            return _json(record_stand_aside(_runtime(ctx).ledger, dict(params or {}), kwargs.get("session_id")))
        except Exception as e:  # noqa: BLE001
            return _json({"ok": False, "error": f"{type(e).__name__}: {str(e)[:400]}"})
    return handler


def _policy_handler(params: dict, **kwargs) -> str:
    from oath_core.policy import load_policy

    try:
        return _json(load_policy().public())
    except Exception as e:  # noqa: BLE001
        return _json({"ok": False, "error": f"{type(e).__name__}: {str(e)[:400]}"})


def _pre_tool_call(tool_name, args, task_id=None, **kwargs):
    from oath_core.guard import decide

    return decide(tool_name, args)


def _cli_setup(parser) -> None:
    parser.add_argument("oath_cmd", choices=["status", "verify", "policy"], help="OATH subcommand")
    parser.add_argument("oath_args", nargs="*", help="extra args, e.g. --set max_trade_usd=3.00")


def _cli_handler(args) -> int:
    from oath_core.__main__ import main as oath_main

    return oath_main([args.oath_cmd, *args.oath_args])


def _slash(raw_args: str) -> str:
    from oath_core.config import LEDGER_PATH
    from oath_core.ledger import Ledger

    return json.dumps(status_summary(Ledger(LEDGER_PATH)), indent=2, default=str)


def register(ctx) -> None:
    # 1. The guard goes first and depends only on the stdlib: trading stays blocked even if
    #    anything below fails to import.
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    # 2. Tools
    ctx.register_tool(name="oath_open_position", toolset="oath", schema=OPEN_SCHEMA, handler=_make_open(ctx),
                      description=OPEN_SCHEMA["description"], emoji="⚖️")
    ctx.register_tool(name="oath_stand_aside", toolset="oath", schema=STAND_ASIDE_SCHEMA,
                      handler=_make_stand_aside(ctx), description=STAND_ASIDE_SCHEMA["description"])
    ctx.register_tool(name="oath_status", toolset="oath", schema=STATUS_SCHEMA, handler=_make_status(ctx),
                      description=STATUS_SCHEMA["description"])
    ctx.register_tool(name="oath_policy", toolset="oath", schema=POLICY_SCHEMA, handler=_policy_handler,
                      description=POLICY_SCHEMA["description"])
    # 3. Guidance + operator surfaces
    ctx.register_system_prompt_section("oath.trading-rules", RULES, max_chars=4000)
    ctx.register_skill("oath-trader", _HERE / "skills" / "oath-trader" / "SKILL.md",
                       description="OATH trading playbook: when to open, how to set stop/tp/horizon honestly.")
    ctx.register_cli_command("oath", "OATH: status | verify | policy", _cli_setup, _cli_handler)
    ctx.register_command("oath", _slash, description="Show the OATH record (open positions, P&L)")
