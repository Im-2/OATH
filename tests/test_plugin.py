"""The Hermes plugin module, loaded exactly as Hermes would, against a recording fake ctx."""
import importlib.util
import json
from pathlib import Path

import pytest

from oath_core.clawpump import ClawPumpError

PLUGIN = Path(__file__).resolve().parent.parent / "plugin" / "oath" / "__init__.py"


def load_plugin():
    spec = importlib.util.spec_from_file_location("oath_plugin_under_test", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RecordingCtx:
    def __init__(self, envelope=None):
        self.calls = []
        self.envelope = envelope

    def __getattr__(self, name):
        if name.startswith("register_"):
            return lambda *a, **k: self.calls.append((name, a, k))
        raise AttributeError(name)

    def call_mcp(self, server, tool, args, timeout=30):
        self.calls.append(("call_mcp", (server, tool, args), {"timeout": timeout}))
        return self.envelope


def test_hook_is_registered_before_anything_else():
    ctx = RecordingCtx()
    load_plugin().register(ctx)
    assert ctx.calls[0][0] == "register_hook" and ctx.calls[0][1][0] == "pre_tool_call"
    tools = [c[2]["name"] for c in ctx.calls if c[0] == "register_tool"]
    assert tools == ["oath_open_position", "oath_stand_aside", "oath_status", "oath_policy"]
    section = next(c for c in ctx.calls if c[0] == "register_system_prompt_section")
    assert len(section[1][1]) <= 4000
    skill = next(c for c in ctx.calls if c[0] == "register_skill")
    assert Path(skill[1][1]).is_file()


def test_registered_hook_blocks_fund_movers_and_passes_reads():
    ctx = RecordingCtx()
    load_plugin().register(ctx)
    hook = ctx.calls[0][1][1]
    assert hook("mcp__clawpump_stdio__swap_execute", {}, "t", session_id="s")["action"] == "block"
    assert hook("mcp__clawpump__wallet_transfer", {}, "t")["action"] == "block"
    assert hook("mcp__clawpump_stdio__get_price", {"tokens": "SOL"}, "t") is None


def test_open_schema_matches_manifest_and_requires_thesis_fields():
    mod = load_plugin()
    req = set(mod.OPEN_SCHEMA["parameters"]["required"])
    assert {"size_usd", "entry", "horizon_min", "conf", "strat", "why"} <= req
    manifest = (PLUGIN.parent / "plugin.yaml").read_text()
    for name in ("oath_open_position", "oath_stand_aside", "oath_status", "oath_policy", "pre_tool_call"):
        assert name in manifest


def test_call_mcp_adapter_decodes_envelopes():
    mod = load_plugin()
    ok_json = RecordingCtx({"ok": True, "result": json.dumps({"status": "executed", "txHash": "x"})})
    cp = mod.HermesClawPump(ok_json, "clawpump-stdio")
    assert cp.call("swap_execute", {"amount": "1"}) == {"status": "executed", "txHash": "x"}
    assert ok_json.calls[-1][2]["timeout"] == 120 and ok_json.calls[-1][1][0] == "clawpump-stdio"
    text = mod.HermesClawPump(RecordingCtx({"ok": True, "result": "Address removed."}), "clawpump-stdio")
    assert text.call("remove_from_whitelist", {}) == {"text": "Address removed."}
    err = mod.HermesClawPump(RecordingCtx({"ok": False, "error": "Authentication failed"}), "clawpump-stdio")
    with pytest.raises(ClawPumpError):
        err.call("get_price", {"tokens": "SOL"})
