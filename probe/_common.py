"""Shared helpers for Phase 0 probes.

The cpk_ key is read from the environment or a gitignored env file and is never
printed or written to disk. Every saved payload is scrubbed for cpk_ strings.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 0.1.25 (the version claw-agent pins) was published without dist/ and cannot start.
CLAWPUMP_PKG = "@clawpump/agents@0.1.27"

PROBE_DIR = Path(__file__).resolve().parent
ENV_FILES = [
    Path.home() / ".oath" / ".env",
    PROBE_DIR.parent / ".env",
    Path.home() / ".hermes" / ".env",
]
_KEY_RE = re.compile(r"cpk_[A-Za-z0-9_\-]+")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Account-profile fields that identify the operator; not needed by any probe.
_PII_KEYS = {"email", "avatar_url", "auth_id", "x_user_id", "telegram_id", "id_token", "twitter", "display_name",
             "x_username", "x_display_name", "telegram_username", "deposit_wallet", "linked_accounts"}


def _read_env_file(path: Path, name: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == name:
            v = v.strip()
            if v[:1] in ('"', "'"):
                v = v[1:].split(v[0], 1)[0]
            else:
                v = re.split(r"\s+#", v, 1)[0].strip()  # dotenv inline comment
            return v or None
    return None


def load_api_key() -> str:
    key = os.environ.get("CLAWPUMP_API_KEY")
    source = "environment"
    if not key:
        for f in ENV_FILES:
            key = _read_env_file(f, "CLAWPUMP_API_KEY")
            if key:
                source = str(f)
                break
    if not key or not key.startswith("cpk_"):
        raise SystemExit(
            "CLAWPUMP_API_KEY not found (or not a cpk_ key). Put it in one of: "
            + ", ".join(str(f) for f in ENV_FILES)
        )
    print(f"[probe] using CLAWPUMP_API_KEY from {source} (value not shown)")
    return key


def scrub(obj):
    """Remove cpk_ keys, emails and operator-profile fields before anything hits disk."""
    if isinstance(obj, str):
        return _EMAIL_RE.sub("[EMAIL]", _KEY_RE.sub("cpk_[REDACTED]", obj))
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: "[REDACTED]" if k in _PII_KEYS else scrub(v) for k, v in obj.items()}
    return obj


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def save(name: str, payload) -> Path:
    path = PROBE_DIR / f"{today()}_{name}.json"
    if path.exists() and name.startswith("swap"):
        # Never overwrite a fund-moving record; each run keeps its own file.
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%H%M%S")
        path = PROBE_DIR / f"{today()}_{name}_{stamp}.json"
    path.write_text(json.dumps(scrub(payload), indent=2, default=str), encoding="utf-8")
    print(f"[probe] saved {path.name}")
    return path


def decode_result(res) -> dict:
    """Turn an MCP CallToolResult into {is_error, data|text}."""
    texts = [c.text for c in res.content if getattr(c, "type", None) == "text"]
    joined = "\n".join(texts)
    out: dict = {"is_error": bool(res.isError)}
    try:
        out["data"] = json.loads(joined)
    except (json.JSONDecodeError, TypeError):
        out["text"] = joined
    return out


@asynccontextmanager
async def clawpump_session():
    key = load_api_key()
    env = dict(os.environ)
    env.pop("CLAWPUMP_TOKEN", None)  # swap tools refuse when both are set
    env["CLAWPUMP_API_KEY"] = key
    npx = shutil.which("npx") or "npx"
    params = StdioServerParameters(command=npx, args=["-y", CLAWPUMP_PKG], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"[probe] connected: {init.serverInfo.name} {init.serverInfo.version}")
            yield session
