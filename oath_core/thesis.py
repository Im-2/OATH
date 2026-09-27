"""Thesis schema, validation, canonical encoding and commitment digest (SPEC §4.1–4.2).

Canonical encoding: JSON, sorted keys, no whitespace, UTF-8, every value a
string; decimals are fixed-precision strings so no float ever enters the hash.
digest = sha256(canonical_json(thesis) || salt), salt = 32 random bytes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import secrets
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from .config import is_pubkey

VERSION = "1"
SALT_BYTES = 32
WHY_MAX = 140

# Fixed decimals per numeric field. Prices get 6 dp so low-priced tokens stay exact.
DECIMALS = {"size_usd": 2, "entry": 6, "stop": 6, "tp": 6, "conf": 2}
FIELDS = ("v", "agent", "seq", "ts", "mkt", "side", "in_mint", "out_mint", "size_usd",
          "entry", "stop", "tp", "horizon_min", "conf", "strat", "why")

_MKT_RE = re.compile(r"^[A-Z0-9]{1,12}/[A-Z0-9]{1,12}$")
_STRAT_RE = re.compile(r"^[a-z0-9_\-]{1,32}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class ThesisError(ValueError):
    """Thesis failed validation. Callers must refuse the trade."""


def fmt_decimal(value, places: int) -> str:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        raise ThesisError(f"not a number: {value!r}") from e
    if not d.is_finite():
        raise ThesisError(f"not finite: {value!r}")
    return str(d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN))


def utc_now_ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_thesis(*, agent: str, seq: int, mkt: str, in_mint: str, out_mint: str,
                 size_usd, entry, stop, tp, horizon_min: int, conf, strat: str, why: str,
                 side: str = "long", ts: str | None = None) -> dict:
    """Normalise raw inputs into a thesis dict (all strings). Validates; raises ThesisError."""
    if isinstance(seq, bool) or not isinstance(seq, int):
        raise ThesisError("seq must be int")
    if isinstance(horizon_min, bool) or not isinstance(horizon_min, int):
        raise ThesisError("horizon_min must be int")
    t = {
        "v": VERSION, "agent": agent, "seq": str(seq), "ts": ts or utc_now_ts(),
        "mkt": mkt, "side": side, "in_mint": in_mint, "out_mint": out_mint,
        "size_usd": fmt_decimal(size_usd, DECIMALS["size_usd"]),
        "entry": fmt_decimal(entry, DECIMALS["entry"]),
        "stop": fmt_decimal(stop, DECIMALS["stop"]),
        "tp": fmt_decimal(tp, DECIMALS["tp"]),
        "horizon_min": str(horizon_min),
        "conf": fmt_decimal(conf, DECIMALS["conf"]),
        "strat": strat, "why": why,
    }
    validate(t)
    return t


def validate(t: dict, *, max_size_usd: Decimal | None = None, max_horizon_min: int | None = None) -> None:
    """Structural + semantic checks (SPEC §4.1). Policy caps are optional here; the firewall enforces them."""
    if set(t) != set(FIELDS):
        raise ThesisError(f"fields mismatch: missing={set(FIELDS) - set(t)} extra={set(t) - set(FIELDS)}")
    if any(not isinstance(v, str) for v in t.values()):
        raise ThesisError("all thesis values must be strings")
    if t["v"] != VERSION:
        raise ThesisError("unsupported version")
    if t["side"] != "long":
        raise ThesisError("v1 is spot long only")
    for k in ("agent", "in_mint", "out_mint"):
        if not is_pubkey(t[k]):
            raise ThesisError(f"{k} is not a base58 pubkey")
    if t["in_mint"] == t["out_mint"]:
        raise ThesisError("in_mint == out_mint")
    if not (t["seq"].isdigit() and int(t["seq"]) >= 1 and str(int(t["seq"])) == t["seq"]):
        raise ThesisError("seq must be a positive integer without leading zeros")
    if not _TS_RE.match(t["ts"]):
        raise ThesisError("ts must be YYYY-MM-DDTHH:MM:SSZ")
    if not _MKT_RE.match(t["mkt"]):
        raise ThesisError("mkt must look like SOL/USDC")
    if not _STRAT_RE.match(t["strat"]):
        raise ThesisError("strat must be [a-z0-9_-]{1,32}")
    if not t["why"] or len(t["why"]) > WHY_MAX or any(ord(c) < 32 for c in t["why"]):
        raise ThesisError(f"why must be 1..{WHY_MAX} printable chars")
    for k, places in DECIMALS.items():
        if fmt_decimal(t[k], places) != t[k]:
            raise ThesisError(f"{k} is not canonical fixed-decimal ({places} dp)")
    size, entry, stop, tp, conf = (Decimal(t[k]) for k in ("size_usd", "entry", "stop", "tp", "conf"))
    if size <= 0:
        raise ThesisError("size_usd must be > 0")
    if not (Decimal(0) < stop < entry < tp):
        raise ThesisError("long requires 0 < stop < entry < tp")
    if not (Decimal(0) <= conf <= Decimal(1)):
        raise ThesisError("conf must be in [0, 1]")
    if not (t["horizon_min"].isdigit() and int(t["horizon_min"]) >= 1):
        raise ThesisError("horizon_min must be a positive integer")
    if max_size_usd is not None and size > max_size_usd:
        raise ThesisError(f"size_usd {size} exceeds cap {max_size_usd}")
    if max_horizon_min is not None and int(t["horizon_min"]) > max_horizon_min:
        raise ThesisError(f"horizon_min exceeds cap {max_horizon_min}")


def canonical_json(t: dict) -> bytes:
    validate(t)
    return json.dumps(t, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def parse_canonical(raw: bytes | str) -> dict:
    """Parse a revealed thesis and insist it is byte-for-byte canonical."""
    b = raw.encode("utf-8") if isinstance(raw, str) else raw
    try:
        t = json.loads(b.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ThesisError("revealed thesis is not JSON") from e
    if not isinstance(t, dict) or canonical_json(t) != b:
        raise ThesisError("revealed thesis is not in canonical form")
    return t


def new_salt() -> bytes:
    return secrets.token_bytes(SALT_BYTES)


def digest(canonical: bytes, salt: bytes) -> str:
    if len(salt) != SALT_BYTES:
        raise ThesisError("salt must be 32 bytes")
    return hashlib.sha256(canonical + salt).hexdigest()
