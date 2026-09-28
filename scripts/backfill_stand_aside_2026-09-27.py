"""ONE-OFF: backfill the 2026-09-27 stand-aside (before oath_stand_aside existed) from its source.

    uv run python scripts/backfill_stand_aside_2026-09-27.py

Reads Hermes session 20260927_195911_f2a8f6 (read-only) for the tool readings and the agent's
decision, and records it in the ledger's off-chain `decisions` table with the ORIGINAL decision
time, labelled backfilled + source session. Idempotent: does nothing if already recorded.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oath_core.config import LEDGER_PATH  # noqa: E402
from oath_core.ledger import Ledger  # noqa: E402

SESSION = "20260927_195911_f2a8f6"
STATE_DB = Path.home() / ".hermes" / "state.db"


def inner_json(content: str) -> dict:
    """Tool results are wrapped: <untrusted_tool_result ...> {"result": "<json text>"} </...>."""
    m = re.search(r"(\{.*\})\s*</untrusted_tool_result>", content, re.S)
    outer = json.loads(m.group(1))
    res = outer.get("result", outer)
    return json.loads(res) if isinstance(res, str) else res


def main() -> int:
    ledger = Ledger(LEDGER_PATH)
    if any(d["evidence"].get("source_session") == SESSION for d in ledger.decisions(limit=100000)):
        print("already backfilled; nothing to do")
        return 0
    db = sqlite3.connect(f"file:{STATE_DB.as_posix()}?mode=ro", uri=True)
    rows = db.execute("SELECT role, content, tool_name, timestamp FROM messages WHERE session_id=? ORDER BY id",
                      (SESSION,)).fetchall()
    price = indicators = market = None
    decision_ts = decision_text = None
    for role, content, tool, ts in rows:
        if role == "tool" and tool == "mcp__clawpump_stdio__get_price":
            price = inner_json(content)
        elif role == "tool" and tool == "mcp__clawpump_stdio__get_indicators":
            indicators = inner_json(content)
        elif role == "tool" and tool == "mcp__clawpump_stdio__intelligence_market":
            market = inner_json(content)
        elif role == "assistant" and content and "STAND ASIDE" in content:
            decision_ts, decision_text = float(ts), content
    if not (price and indicators and decision_text):
        raise SystemExit("source session is missing the readings or the decision; refusing to backfill")
    sol = next(v for v in price["prices"].values())
    change = float(sol["change24h"])
    agreeing = int(re.search(r"(\d+)\s+agreeing", decision_text).group(1))
    against = int(re.search(r"(\d+)\s+strongly against", decision_text).group(1))
    evidence = {
        "signals": [
            {"name": "24h trend", "reading": f"+{change:.2f}%", "agrees": 0 < change < 8},
            {"name": "Momentum (intelligence_market)", "reading": "unavailable" if "error" in (market or {}) else "ok",
             "agrees": False},
            {"name": "Risk appetite (sentiment)", "reading": indicators.get("sentiment"), "agrees": False},
            {"name": "SOL flow (intelligence_signals)", "reading": "no SOL-specific signal", "agrees": False},
        ],
        "agreeing": agreeing, "against": against, "needs": 2,
        "sol_price_usd": round(float(sol["usd"]), 4),
        "backfilled": True, "source_session": SESSION,
        "backfilled_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    ts = dt.datetime.fromtimestamp(decision_ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rid = ledger.record_decision("stand_aside", "SOL/USDC", "INSUFFICIENT_SIGNALS",
                                 f"{agreeing}/4 signals agreeing, needs 2. Stood aside.", evidence,
                                 session_id=SESSION, ts=ts)
    print(f"backfilled decision id={rid} at {ts}: {agreeing} agreeing / {against} against")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
