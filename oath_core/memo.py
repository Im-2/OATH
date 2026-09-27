"""oath1 memo formats (SPEC §4.3): build and strictly parse.

  c  oath1:c:<agent>:<seq>:<digest>:<bond_amt>
  b  oath1:b:<agent>:<seq>:<digest>:<reason_code>
  o  oath1:o:<agent>:<seq>:<swap_sig>
  r  oath1:r:<agent>:<seq>:<salt_hex>:<exit_sig>:<exit_reason>
  s  oath1:s:<agent>:<seq>:<reason>
  t  oath1:t:<seq>:<canonical thesis JSON>   (rides in the reveal tx, so verify needs no API)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import is_pubkey, is_signature

PREFIX = "oath1"
EXIT_REASONS = {"tp", "stop", "expiry", "manual", "exec_failed"}
NO_SIG = "none"  # exit_sig placeholder when nothing was executed (exec_failed)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[a-z0-9_]{1,32}$")
_UINT = re.compile(r"^(0|[1-9][0-9]*)$")


class MemoError(ValueError):
    pass


@dataclass(frozen=True)
class Memo:
    kind: str
    agent: str | None
    seq: int
    fields: dict


def _seq(s: str) -> int:
    if not _UINT.match(s) or int(s) < 1:
        raise MemoError(f"bad seq {s!r}")
    return int(s)


def commit(agent: str, seq: int, digest: str, bond_amt: int = 0) -> str:
    return _check(f"{PREFIX}:c:{agent}:{seq}:{digest}:{bond_amt}")


def blocked(agent: str, seq: int, digest: str, reason_code: str) -> str:
    return _check(f"{PREFIX}:b:{agent}:{seq}:{digest}:{reason_code}")


def open_(agent: str, seq: int, swap_sig: str) -> str:
    return _check(f"{PREFIX}:o:{agent}:{seq}:{swap_sig}")


def reveal(agent: str, seq: int, salt_hex: str, exit_sig: str, exit_reason: str) -> str:
    return _check(f"{PREFIX}:r:{agent}:{seq}:{salt_hex}:{exit_sig}:{exit_reason}")


def slash(agent: str, seq: int, reason: str) -> str:
    return _check(f"{PREFIX}:s:{agent}:{seq}:{reason}")


def thesis(seq: int, canonical: bytes) -> str:
    return _check(f"{PREFIX}:t:{seq}:" + canonical.decode("utf-8"))


def _check(s: str) -> str:
    parse(s)  # never emit a memo our own parser would reject
    return s


def parse(s: str) -> Memo:
    if not isinstance(s, str) or not s.startswith(PREFIX + ":"):
        raise MemoError("not an oath1 memo")
    head = s.split(":", 3)
    if len(head) < 3:
        raise MemoError("truncated memo")
    kind = head[1]
    if kind == "t":
        if len(head) != 4:
            raise MemoError("t memo needs seq and body")
        return Memo("t", None, _seq(head[2]), {"thesis": head[3]})

    parts = s.split(":")
    agent = parts[2]
    if not is_pubkey(agent):
        raise MemoError("bad agent pubkey")
    arity = {"c": 6, "b": 6, "o": 5, "r": 7, "s": 5}
    if kind not in arity:
        raise MemoError(f"unknown kind {kind!r}")
    if len(parts) != arity[kind]:
        raise MemoError(f"{kind} memo has {len(parts)} parts, expected {arity[kind]}")
    seq = _seq(parts[3])
    if kind == "c":
        if not _HEX64.match(parts[4]) or not _UINT.match(parts[5]):
            raise MemoError("bad commit digest/bond")
        return Memo(kind, agent, seq, {"digest": parts[4], "bond_amt": int(parts[5])})
    if kind == "b":
        if not _HEX64.match(parts[4]) or not _CODE.match(parts[5]):
            raise MemoError("bad blocked digest/reason")
        return Memo(kind, agent, seq, {"digest": parts[4], "reason_code": parts[5]})
    if kind == "o":
        if not is_signature(parts[4]):
            raise MemoError("bad swap signature")
        return Memo(kind, agent, seq, {"swap_sig": parts[4]})
    if kind == "r":
        salt, exit_sig, reason = parts[4], parts[5], parts[6]
        if not _HEX64.match(salt):
            raise MemoError("bad salt")
        if reason not in EXIT_REASONS:
            raise MemoError("bad exit reason")
        if not (is_signature(exit_sig) or (exit_sig == NO_SIG and reason == "exec_failed")):
            raise MemoError("bad exit signature")
        return Memo(kind, agent, seq, {"salt_hex": salt, "exit_sig": exit_sig, "exit_reason": reason})
    if not _CODE.match(parts[4]):
        raise MemoError("bad slash reason")
    return Memo(kind, agent, seq, {"reason": parts[4]})
