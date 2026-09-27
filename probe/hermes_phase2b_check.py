"""Phase 2b live check in REAL Hermes: arg repair, new tool registered, test-mode gate. No funds, no memos."""
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
discover_mcp_tools()


def call(name, args):
    raw = handle_function_call(name, args, task_id="oath-phase2b-check")
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw


im = call("mcp__clawpump_stdio__intelligence_market", {"token": "SOL"})
st = call("oath_status", {})
acc = call("oath_open_position", {"size_usd": "1.00", "entry": "market", "stop_pct": "3", "tp_pct": "5",
                                  "horizon_min": 15, "conf": "0.50", "strat": "acceptance_test",
                                  "why": "OPERATOR_TEST: live gate check"})
im_text = json.dumps(im)
checks = {
    "intelligence_market_SOL_now_returns_data": "price_changes" in im_text and "request failed" not in im_text,
    "oath_stand_aside_registered": "oath_stand_aside" in registry.get_all_tool_names(),
    "status_shows_test_mode": isinstance(st, dict) and "test_mode" in st and "stand_asides" in st.get("totals", {}),
    "unarmed_acceptance_test_refused": "not armed" in json.dumps(acc),
}
report = {"date": dt.datetime.now(dt.timezone.utc).isoformat(), "checks": checks, "pass": all(checks.values()),
          "status": st, "acceptance_refusal": acc, "intelligence_market_head": im_text[:400]}
(PROBE_DIR / f"{dt.date.today():%Y-%m-%d}_phase2b_hermes_check.json").write_text(
    json.dumps(scrub(report), indent=2, default=str), encoding="utf-8")
print(json.dumps({k: report[k] for k in ("checks", "pass")}, indent=2))
print("acceptance ->", json.dumps(acc)[:200])
sys.stdout.flush()
os._exit(0)
