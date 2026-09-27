"""SQLite ledger (SPEC §4.4): append-only events + derived positions. A cache; the chain is truth.

Salts for unrevealed positions live here, so the file sits in OATH_HOME with
owner-only permissions. The thesis + salt are stored BEFORE the commit memo
is sent, so a crash can never leave an on-chain commitment we cannot reveal.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
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
        self.db = sqlite3.connect(path, isolation_level=None)  # autocommit; explicit txns below
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        if new and str(path) != ":memory:":
            restrict_to_owner(path)

    def next_seq(self, agent: str) -> int:
        row = self.db.execute("SELECT MAX(seq) AS m FROM positions WHERE agent = ?", (agent,)).fetchone()
        return (row["m"] or 0) + 1

    def prepare(self, agent: str, seq: int, thesis: dict, salt_hex: str, digest: str, bond_amt: int = 0) -> None:
        """Persist thesis + salt before anything goes on-chain. Enforces contiguous, unique seq."""
        expected = self.next_seq(agent)
        if seq != expected:
            raise LedgerError(f"seq {seq} is not contiguous (expected {expected})")
        self.db.execute("BEGIN IMMEDIATE")
        try:
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

    def events(self, seq: int | None = None) -> list[dict]:
        q, args = "SELECT * FROM events", ()
        if seq is not None:
            q, args = q + " WHERE seq = ?", (seq,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY id", args)]
