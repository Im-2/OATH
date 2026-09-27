"""ClawPump access with one sync interface: `call(tool, args) -> dict`, raising on any error.

StdioClawPump runs `npx -y @clawpump/agents@0.1.27` over MCP stdio on a
background event loop (CLI, oath-server). The Hermes plugin (Phase 2) will
provide the same interface backed by ctx.call_mcp("clawpump-stdio", ...).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
from typing import Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import CLAWPUMP_PKG, load_clawpump_key


class ClawPumpError(RuntimeError):
    pass


class ClawPump(Protocol):
    def call(self, tool: str, args: dict) -> dict | list: ...


def decode(is_error: bool, text: str, tool: str) -> dict | list:
    """isError -> raise. Success with JSON -> parsed. Success with plain text (some ClawPump tools,
    e.g. remove_from_whitelist, reply in prose) -> {"text": text}. Callers that need specific fields
    (txHash, rawAmount, ...) still fail closed because those keys are absent."""
    if is_error:
        raise ClawPumpError(f"{tool}: {text[:500]}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}


class StdioClawPump:
    """The MCP session lives inside ONE long-running task (anyio requires cancel scopes to be
    entered and exited by the same task); calls are submitted to the same loop from any thread."""

    def __init__(self, timeout_s: float = 60.0):
        self.timeout_s = timeout_s
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._ready = threading.Event()
        self._closing: asyncio.Event | None = None
        self._life = None
        self._session: ClientSession | None = None

    def __enter__(self) -> "StdioClawPump":
        self._thread.start()
        self._life = asyncio.run_coroutine_threadsafe(self._lifecycle(), self._loop)
        while not self._ready.wait(0.1):
            if self._life.done():
                self._life.result()  # re-raise the startup failure
        if self._life.done():
            self._life.result()
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._closing is not None and not self._life.done():
                self._loop.call_soon_threadsafe(self._closing.set)
            self._life.result(self.timeout_s)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(self.timeout_s)

    async def _lifecycle(self) -> None:
        env = dict(os.environ)
        env.pop("CLAWPUMP_TOKEN", None)  # swap tools refuse when both are set
        env["CLAWPUMP_API_KEY"] = load_clawpump_key()
        params = StdioServerParameters(command=shutil.which("npx") or "npx",
                                       args=["-y", CLAWPUMP_PKG], env=env)
        self._closing = asyncio.Event()
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    await self._closing.wait()
        finally:
            self._session = None
            self._ready.set()

    def call(self, tool: str, args: dict) -> dict | list:
        if self._session is None:
            raise ClawPumpError("session not open")
        res = self._run(self._session.call_tool(tool, args))
        text = "\n".join(c.text for c in res.content if getattr(c, "type", None) == "text")
        return decode(bool(res.isError), text, tool)
