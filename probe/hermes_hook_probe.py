"""Phase 0 probe: Hermes-side behaviour, no API key or funds needed.

Answers, against the INSTALLED Hermes (not docs):
  1. What registry names do tools from servers `clawpump` and `clawpump-stdio` get?
  2. Does ctx.call_mcp() pass through pre_tool_call hooks?
  3. Does ctx.call_mcp() honour mcp_servers.<name>.tools.include?
  4. Does a pre_tool_call {"action":"block"} stop a direct model-style call?

Uses a throwaway HERMES_HOME and a local stub MCP server that exposes
get_price + swap_execute (stub echoes; nothing touches ClawPump).

Run with Hermes's own interpreter:
  ~/.hermes/hermes-agent/venv/Scripts/python.exe probe/hermes_hook_probe.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

PROBE_DIR = Path(__file__).resolve().parent
HERMES_SRC = Path.home() / ".hermes" / "hermes-agent"

home = Path(tempfile.mkdtemp(prefix="pot_hermes_probe_"))
os.environ["HERMES_HOME"] = str(home)
os.environ.pop("CLAWPUMP_API_KEY", None)

stub = home / "stub_server.py"
stub.write_text(textwrap.dedent('''
    from mcp.server.fastmcp import FastMCP
    app = FastMCP("stub-clawpump")

    @app.tool()
    def get_price(tokens: str) -> str:
        return '{"stub": "price", "tokens": "%s"}' % tokens

    @app.tool()
    def swap_execute(input_mint: str, output_mint: str, amount: str) -> str:
        return '{"stub": "STUB_SWAP_EXECUTED"}'

    app.run()
'''), encoding="utf-8")

plugin_dir = home / "plugins" / "potprobe"
plugin_dir.mkdir(parents=True)
(plugin_dir / "plugin.yaml").write_text(
    'name: potprobe\nversion: "0.0.1"\ndescription: "PoT phase-0 hook probe"\n'
    "hooks:\n  - pre_tool_call\n", encoding="utf-8")
(plugin_dir / "__init__.py").write_text(textwrap.dedent('''
    import json
    HOOK_SEEN = []
    CTX = {}

    def _hook(tool_name, args, task_id=None, **kwargs):
        HOOK_SEEN.append({"tool_name": tool_name, "kwargs_keys": sorted(kwargs)})
        if tool_name.endswith("swap_execute"):
            return {"action": "block", "message": "PoT probe: blocked " + tool_name}
        return None

    def _via_call_mcp(params, **kwargs):
        env = CTX["ctx"].call_mcp(params["server"], "swap_execute",
                                  {"input_mint": "USDC", "output_mint": "SOL", "amount": "1"})
        return json.dumps(env)

    def register(ctx):
        CTX["ctx"] = ctx
        ctx.register_hook("pre_tool_call", _hook)
        ctx.register_tool(
            name="potprobe_call_mcp", toolset="potprobe",
            schema={"name": "potprobe_call_mcp", "description": "probe",
                    "parameters": {"type": "object",
                                   "properties": {"server": {"type": "string"}},
                                   "required": ["server"]}},
            handler=_via_call_mcp)
'''), encoding="utf-8")

# Stub runs under the project venv (Hermes's venv lacks mcp.server.fastmcp).
py = str(PROBE_DIR.parent / ".venv" / "Scripts" / "python.exe").replace("\\", "/")
stub_s = str(stub).replace("\\", "/")
(home / "config.yaml").write_text(textwrap.dedent(f'''
    mcp_servers:
      stubcp:
        command: "{py}"
        args: ["{stub_s}"]
      stubcp-stdio:
        command: "{py}"
        args: ["{stub_s}"]
        tools:
          include: [get_price]
    plugins:
      enabled: [potprobe]
      entries:
        potprobe:
          mcp_allowlist: [stubcp, stubcp-stdio]
'''), encoding="utf-8")

sys.path.insert(0, str(HERMES_SRC))
os.chdir(HERMES_SRC)

from hermes_cli.plugins import discover_plugins  # noqa: E402
from tools.mcp_tool import discover_mcp_tools  # noqa: E402
from model_tools import handle_function_call  # noqa: E402
from tools.mcp_tool import mcp_prefixed_tool_name  # noqa: E402

discover_plugins(force=True)
registered = sorted(discover_mcp_tools())
potprobe = sys.modules.get("potprobe") or next(
    m for n, m in sys.modules.items() if n.endswith("potprobe") and hasattr(m, "HOOK_SEEN"))


def run(label, name, args):
    before = len(potprobe.HOOK_SEEN)
    try:
        out = handle_function_call(name, args, task_id="probe")
    except Exception as e:
        out = f"EXCEPTION {e!r}"
    return {"label": label, "call": name, "result": out,
            "hook_calls_during": potprobe.HOOK_SEEN[before:]}


report = {
    "date": dt.datetime.now(dt.timezone.utc).isoformat(),
    "hermes_src": str(HERMES_SRC),
    # Names starting "clawpump" are special-cased by Hermes (remote URL / key
    # injection), so the stub uses neutral names; real names come from the
    # same function Hermes uses to register them.
    "real_server_tool_names": {
        srv: mcp_prefixed_tool_name(srv, "swap_execute")
        for srv in ("clawpump", "clawpump-stdio", "clawpump-agents")},
    "registered_mcp_tool_names": registered,
    "cases": [
        run("direct get_price on 'stubcp' (hook should pass)",
            "mcp__stubcp__get_price", {"tokens": "SOL"}),
        run("direct swap_execute on 'stubcp' (hook should block)",
            "mcp__stubcp__swap_execute", {"input_mint": "USDC", "output_mint": "SOL", "amount": "1"}),
        run("direct swap_execute on 'stubcp-stdio' (excluded by tools.include)",
            "mcp__stubcp_stdio__swap_execute", {"input_mint": "USDC", "output_mint": "SOL", "amount": "1"}),
        run("plugin tool -> ctx.call_mcp('stubcp', swap_execute)",
            "potprobe_call_mcp", {"server": "stubcp"}),
        run("plugin tool -> ctx.call_mcp('stubcp-stdio', swap_execute) [excluded tool]",
            "potprobe_call_mcp", {"server": "stubcp-stdio"}),
    ],
}
out = PROBE_DIR / f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d}_hermes_hook_probe.json"
out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
print(json.dumps(report, indent=2, default=str))
os._exit(0)  # MCP background loop threads keep the interpreter alive otherwise
