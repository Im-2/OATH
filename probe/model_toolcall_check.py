"""Can a free OpenRouter model drive oath_open_position correctly? Nothing executes.

Sends the model the REAL plugin rules + oath_open_position schema (+ a read-only price tool
whose result we stub), with the acceptance-test prompt. Validates the returned tool call with
the real thesis validator, offline. The key is read from ~/.hermes/.env and never printed.

  uv run python probe/model_toolcall_check.py [model ...]
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oath_core.config import SOL_MINT, USDC_MINT, _read_env_file  # noqa: E402
from oath_core.thesis import ThesisError, build_thesis  # noqa: E402

PROBE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("oath_plugin", PROBE.parent / "plugin" / "oath" / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

URL = "https://openrouter.ai/api/v1/chat/completions"
PRICE = Decimal("122.10")
PROMPT = ("Run your OATH playbook on SOL/USDC. This is an acceptance test: if the firewall allows it, open one "
          "position of size 1.00 with stop_pct 3, tp_pct 5 and horizon_min 15, then report what happened.")
PRICE_TOOL = {"type": "function", "function": {
    "name": "mcp__clawpump_stdio__get_price", "description": "Get current spot price for tokens (SOL, USDC...).",
    "parameters": {"type": "object", "properties": {"tokens": {"type": "string"}}, "required": ["tokens"]}}}
OPEN_TOOL = {"type": "function", "function": {k: plugin.OPEN_SCHEMA[k] for k in ("name", "description", "parameters")}}
PRICE_RESULT = json.dumps({"prices": {"SOL": {"usd": float(PRICE), "change24h": 1.8, "source": "stub"}}})


def validate_args(args: dict) -> tuple[bool, str]:
    """Would this call pass OATH's own schema + thesis validation? (offline, stubbed price)"""
    try:
        missing = [k for k in plugin.OPEN_SCHEMA["parameters"]["required"] if k not in args]
        if missing:
            return False, f"missing {missing}"
        entry = PRICE if str(args["entry"]).lower() == "market" else Decimal(str(args["entry"]))
        stop = Decimal(str(args["stop"])) if args.get("stop") is not None else entry * (1 - Decimal(str(args["stop_pct"])) / 100)
        tp = Decimal(str(args["tp"])) if args.get("tp") is not None else entry * (1 + Decimal(str(args["tp_pct"])) / 100)
        build_thesis(agent="9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY", seq=2, mkt=args.get("mkt", "SOL/USDC"),
                     in_mint=USDC_MINT, out_mint=SOL_MINT, size_usd=args["size_usd"], entry=entry, stop=stop, tp=tp,
                     horizon_min=int(args["horizon_min"]), conf=args["conf"], strat=args["strat"], why=args["why"])
    except (ThesisError, KeyError, ValueError, TypeError, ArithmeticError) as e:
        return False, f"{type(e).__name__}: {e}"
    ok_params = (Decimal(str(args["size_usd"])) == Decimal("1.00") and int(args["horizon_min"]) == 15)
    return ok_params, "valid thesis" if ok_params else "valid thesis but not the requested size/horizon"


def run(model: str, key: str) -> dict:
    msgs = [{"role": "system", "content": plugin.RULES}, {"role": "user", "content": PROMPT}]
    tools = [PRICE_TOOL, OPEN_TOOL]
    trace = []
    for turn in range(4):
        r = httpx.post(URL, headers={"Authorization": f"Bearer {key}"}, timeout=120,
                       json={"model": model, "messages": msgs, "tools": tools, "temperature": 0.2})
        if r.status_code != 200:
            return {"model": model, "ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}", "trace": trace}
        msg = r.json()["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        trace.append({"turn": turn, "content": (msg.get("content") or "")[:300],
                      "tool_calls": [{"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                                     for c in calls]})
        if not calls:
            return {"model": model, "ok": False, "error": "model answered without calling oath_open_position",
                    "trace": trace}
        msgs.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                return {"model": model, "ok": False, "error": "tool arguments are not valid JSON", "trace": trace}
            if name == OPEN_TOOL["function"]["name"]:
                ok, why = validate_args(args)
                return {"model": model, "ok": ok, "verdict": why, "open_args": args, "turns": turn + 1,
                        "trace": trace}
            result = PRICE_RESULT if name == PRICE_TOOL["function"]["name"] else json.dumps({"error": "unknown tool"})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
    return {"model": model, "ok": False, "error": "no oath_open_position call within 4 turns", "trace": trace}


def main() -> int:
    key = _read_env_file(Path.home() / ".hermes" / ".env", "OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY not found in ~/.hermes/.env")
    models = sys.argv[1:] or ["nvidia/nemotron-3-ultra-550b-a55b:free"]
    results = []
    for m in models:
        t0 = time.time()
        res = run(m, key)
        res["seconds"] = round(time.time() - t0, 1)
        results.append(res)
        print(json.dumps({k: res.get(k) for k in ("model", "ok", "verdict", "error", "open_args", "turns", "seconds")},
                         indent=1))
    out = PROBE / f"{dt.date.today():%Y-%m-%d}_model_toolcall_check.json"
    prev = json.loads(out.read_text()) if out.exists() else []
    out.write_text(json.dumps(prev + results, indent=2, default=str), encoding="utf-8")
    return 0 if any(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
