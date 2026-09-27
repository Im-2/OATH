"""Operator acceptance-test mode: one forced position, armed by the operator only.

  python -m oath_core testmode arm [--minutes 30]   # one-shot, expires
  python -m oath_core testmode status
  python -m oath_core testmode disarm

When armed, oath_open_position accepts ONE thesis with strat == "acceptance_test" even though
the playbook's signal threshold wasn't met. Nothing else changes: the firewall, commit, entry
swap, monitor exit and on-chain reveal all run as normal, and the committed thesis itself says
`acceptance_test`, so the public record shows it was a forced test, not a market call.
The model cannot arm this (it has no tool for it); without an armed token, a thesis using the
acceptance_test strategy is refused before anything is recorded.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .config import OATH_HOME

TEST_STRAT = "acceptance_test"
TESTMODE_PATH = OATH_HOME / "test_mode.json"


class TestModeError(PermissionError):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def arm(minutes: int = 30, path: Path = TESTMODE_PATH) -> dict:
    if not 1 <= minutes <= 240:
        raise ValueError("minutes must be 1..240")
    state = {"armed": True, "uses_left": 1,
             "armed_at": _now().isoformat(), "expires_at": (_now() + dt.timedelta(minutes=minutes)).isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def disarm(path: Path = TESTMODE_PATH) -> None:
    if path.exists():
        path.unlink()


def status(path: Path = TESTMODE_PATH) -> dict:
    """{'armed': bool, ...}. Expired or used-up tokens report armed=False."""
    if not path.is_file():
        return {"armed": False}
    try:
        s = json.loads(path.read_text(encoding="utf-8"))
        live = (s.get("armed") and s.get("uses_left", 0) > 0
                and dt.datetime.fromisoformat(s["expires_at"]) > _now())
    except (ValueError, KeyError, TypeError):
        return {"armed": False, "error": "unreadable test_mode.json"}
    return {**s, "armed": bool(live)}


def consume(path: Path = TESTMODE_PATH) -> dict:
    """Use the one-shot token. Raises unless the operator armed it and it is still valid."""
    s = status(path)
    if not s.get("armed"):
        raise TestModeError(f"strat '{TEST_STRAT}' needs operator test mode: "
                            f"`python -m oath_core testmode arm` (current: {s})")
    s.update(uses_left=s["uses_left"] - 1, armed=False, used_at=_now().isoformat())
    path.write_text(json.dumps(s, indent=2), encoding="utf-8")
    return s
