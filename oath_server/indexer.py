"""Chain indexer (SPEC §5.5): rebuilds the full OATH record from notary memos + chain alone.

    python -m oath_server.indexer --once     # build and write OATH_HOME/index.json, print a summary

No ledger input: the index is exactly what `python -m oath_core.verify --notary <pubkey>` sees,
so the API can never serve a record the chain doesn't prove. The API keeps serving the last good
index if a refresh fails (and reports the error + index age).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import threading
import time
from pathlib import Path

from oath_core.config import NOTARY_PATH, OATH_HOME, load_config
from oath_core.keys import load_keypair
from oath_core.solana_rpc import Rpc
from oath_core.verify import verify

INDEX_PATH = OATH_HOME / "index.json"
REFRESH_S = 60
log = logging.getLogger("oath.indexer")


def build_index(rpc, notary: str, *, now: float | None = None) -> dict:
    report = verify(rpc, notary, now=now, scan_agent=True)
    report["indexed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["source"] = "chain"  # every field below is derived from notary memos + on-chain txs
    return report


def save_index(index: dict, path: Path = INDEX_PATH) -> None:
    """Atomic replace so the API never reads a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, default=str), encoding="utf-8")
    os.replace(tmp, path)


def load_index(path: Path = INDEX_PATH) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class Indexer:
    """Holds the latest good index in memory; refreshes on a background thread."""

    def __init__(self, rpc, notary: str, *, path: Path | None = INDEX_PATH, refresh_s: int = REFRESH_S):
        self.rpc, self.notary, self.path, self.refresh_s = rpc, notary, path, refresh_s
        self.index: dict | None = load_index(path) if path else None
        self.last_error: str | None = None
        self.last_attempt: float | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def refresh(self) -> dict | None:
        self.last_attempt = time.time()
        try:
            idx = build_index(self.rpc, self.notary)
        except Exception as e:  # noqa: BLE001 - keep serving the last good index
            self.last_error = f"{type(e).__name__}: {str(e)[:300]}"
            log.warning("index refresh failed: %s", self.last_error)
            return self.index
        with self._lock:
            self.index, self.last_error = idx, None
        if self.path:
            save_index(idx, self.path)
        return idx

    def get(self) -> dict | None:
        with self._lock:
            return self.index

    def start(self) -> None:
        def loop():
            while not self._stop.is_set():
                self.refresh()
                self._stop.wait(self.refresh_s)
        threading.Thread(target=loop, daemon=True, name="oath-indexer").start()

    def stop(self) -> None:
        self._stop.set()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rebuild the OATH record from chain data alone")
    ap.add_argument("--once", action="store_true", help="build once, write index.json, print a summary")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = load_config()
    rpc = Rpc(cfg.effective_rpc_url)
    notary = str(load_keypair(NOTARY_PATH).pubkey())
    ix = Indexer(rpc, notary)
    while True:
        idx = ix.refresh()
        if idx:
            for agent, ag in idx["agents"].items():
                print(f"agent {agent}: {ag['stats']}")
                for row in ag["positions"]:
                    print(f"  seq {row['seq']:>3} {row.get('status'):<10} digest_ok={row.get('digest_ok')}")
            print("PASS" if idx["pass"] else f"FAIL: {idx['issues']}", f"| events {len(idx['events'])}")
        if a.once:
            return 0 if idx and not ix.last_error else 1
        time.sleep(ix.refresh_s)


if __name__ == "__main__":
    raise SystemExit(main())
