"""SQLite ledger (SPEC §4.4): append-only events + derived positions. A cache; the chain is truth.

Salts for unrevealed positions live here, so the file sits in OATH_HOME with
owner-only permissions. The thesis + salt are stored BEFORE the commit memo
is sent, so a crash can never leave an on-chain commitment we cannot reveal.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

from .keys import restrict_to_owner

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('prepared','commit','blocked','open','close','reveal','slash','bond_release','error')),
  payload_json TEXT NOT NULL,
  tx_sig TEXT,
  slot INTEGER,
  created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;

CREATE TABLE IF NOT EXISTS positions (
  seq INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('prepared','blocked','committed','open','closed','revealed','unrevealed','slashed')),
  thesis_json TEXT NOT NULL,
  salt_hex TEXT NOT NULL,
  digest TEXT NOT NULL,
  commit_sig TEXT, commit_slot INTEGER,
  open_sig TEXT, swap_sig TEXT, swap_slot INTEGER,
  exit_sig TEXT, exit_slot INTEGER, exit_reason TEXT,
  reveal_sig TEXT, reveal_slot INTEGER,
  entry_fill_json TEXT, exit_fill_json TEXT,
  pnl_usd TEXT,
  bond_amt INTEGER NOT NULL DEFAULT 0, bond_status TEXT,
  opened_at TEXT, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS equity_snapshots (ts TEXT NOT NULL, equity_usd TEXT NOT NULL, source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fee_allocations (ts TEXT NOT NULL, bucket TEXT NOT NULL, amount TEXT NOT NULL, tx_sig TEXT);

-- Off-chain decisions that are not trades (e.g. "looked, chose not to trade"). No memo, no seq.
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('stand_aside')),
  mkt TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  why TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  session_id TEXT
);
CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
"""

POSITION_COLS = {
    "status", "commit_sig", "commit_slot", "open_sig", "swap_sig", "swap_slot", "exit_sig", "exit_slot",
    "exit_reason", "reveal_sig", "reveal_slot", "entry_fill_json", "exit_fill_json", "pnl_usd",
    "bond_status", "opened_at", "closed_at",
}


class LedgerError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    def __init__(self, path: Path):
        new = not path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        # autocommit; explicit txns below. Plugin (Hermes) and monitor are separate processes.
        self.db = sqlite3.connect(path, isolation_level=None, timeout=30, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout = 30000")
        if str(path) != ":memory:":
            self.db.execute("PRAGMA journal_mode = WAL")
        self.db.executescript(SCHEMA)
        if new and str(path) != ":memory:":
            restrict_to_owner(path)

    def next_seq(self, agent: str) -> int:
        row = self.db.execute("SELECT MAX(seq) AS m FROM positions WHERE agent = ?", (agent,)).fetchone()
        return (row["m"] or 0) + 1

    def prepare(self, agent: str, seq: int, thesis: dict, salt_hex: str, digest: str, bond_amt: int = 0) -> None:
        """Persist thesis + salt before anything goes on-chain. Enforces contiguous, unique seq."""
        self.db.execute("BEGIN IMMEDIATE")  # take the write lock before reading next_seq
        try:
            expected = self.next_seq(agent)
            if seq != expected:
                raise LedgerError(f"seq {seq} is not contiguous (expected {expected})")
            self.db.execute(
                "INSERT INTO positions (seq, agent, status, thesis_json, salt_hex, digest, bond_amt) "
                "VALUES (?, ?, 'prepared', ?, ?, ?, ?)",
                (seq, agent, json.dumps(thesis, sort_keys=True), salt_hex, digest, bond_amt))
            self._event(seq, "prepared", {"digest": digest})
            self.db.execute("COMMIT")
        except sqlite3.IntegrityError as e:
            self.db.execute("ROLLBACK")
            raise LedgerError(f"duplicate seq {seq}") from e
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def record(self, seq: int, kind: str, payload: dict, *, tx_sig: str | None = None,
               slot: int | None = None, **position_updates) -> None:
        bad = set(position_updates) - POSITION_COLS
        if bad:
            raise LedgerError(f"unknown position columns {bad}")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._event(seq, kind, payload, tx_sig, slot)
            if position_updates:
                cols = ", ".join(f"{k} = ?" for k in position_updates)
                cur = self.db.execute(f"UPDATE positions SET {cols} WHERE seq = ?", (*position_updates.values(), seq))
                if cur.rowcount != 1:
                    raise LedgerError(f"no position {seq}")
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def _event(self, seq, kind, payload, tx_sig=None, slot=None) -> None:
        self.db.execute("INSERT INTO events (seq, kind, payload_json, tx_sig, slot, created_at) VALUES (?,?,?,?,?,?)",
                        (seq, kind, json.dumps(payload, sort_keys=True, default=str), tx_sig, slot, now_iso()))

    def position(self, seq: int) -> dict:
        row = self.db.execute("SELECT * FROM positions WHERE seq = ?", (seq,)).fetchone()
        if row is None:
            raise LedgerError(f"no position {seq}")
        return dict(row)

    def positions(self, status: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM positions", ()
        if status:
            q, args = q + " WHERE status = ?", (status,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY seq", args)]

    # --- equity + counters for the firewall -------------------------------------------------

    def snapshot_equity(self, equity_usd, source: str) -> None:
        self.db.execute("INSERT INTO equity_snapshots (ts, equity_usd, source) VALUES (?, ?, ?)",
                        (now_iso(), str(equity_usd), source))

    def equity_peak(self):
        rows = [Decimal(r["equity_usd"]) for r in self.db.execute("SELECT equity_usd FROM equity_snapshots")]
        return max(rows) if rows else None

    def equity_day_start(self, day: str):
        """First snapshot on `day` (YYYY-MM-DD, UTC), or None."""
        row = self.db.execute("SELECT equity_usd FROM equity_snapshots WHERE substr(ts, 1, 10) = ? "
                              "ORDER BY ts LIMIT 1", (day,)).fetchone()
        return Decimal(row["equity_usd"]) if row else None

    def count_events_since(self, kind: str, since_iso: str) -> int:
        return self.db.execute("SELECT COUNT(*) AS n FROM events WHERE kind = ? AND created_at >= ?",
                               (kind, since_iso)).fetchone()["n"]

    def open_count(self) -> int:
        """Positions holding (or about to hold) risk: committed, open, or exited-but-unrevealed."""
        return self.db.execute("SELECT COUNT(*) AS n FROM positions WHERE status IN "
                               "('prepared','committed','open','closed')").fetchone()["n"]

    def record_decision(self, kind: str, mkt: str, reason_code: str, why: str, evidence: dict,
                        session_id: str | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO decisions (ts, kind, mkt, reason_code, why, evidence_json, session_id) VALUES (?,?,?,?,?,?,?)",
            (now_iso(), kind, mkt, reason_code, why, json.dumps(evidence, sort_keys=True, default=str), session_id))
        return cur.lastrowid

    def decisions(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))
        return [{**dict(r), "evidence": json.loads(r["evidence_json"])} for r in rows]

    def events(self, seq: int | None = None) -> list[dict]:
        q, args = "SELECT * FROM events", ()
        if seq is not None:
            q, args = q + " WHERE seq = ?", (seq,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY id", args)]
