"""Notary keypair storage (Solana CLI JSON format) with owner-only permissions."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from solders.keypair import Keypair


def restrict_to_owner(path: Path) -> None:
    """chmod 600/700 equivalent. On Windows: drop inherited ACLs, grant only the current user."""
    if sys.platform == "win32":
        user = os.environ.get("USERNAME") or os.getlogin()
        grant = f"{user}:(OI)(CI)F" if path.is_dir() else f"{user}:F"
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", grant],
                       check=True, capture_output=True)
    else:
        path.chmod(0o700 if path.is_dir() else 0o600)


def generate_keypair(path: Path) -> Keypair:
    """Create a new keypair file. Refuses to overwrite: losing a notary key orphans every commitment."""
    if path.exists():
        raise FileExistsError(f"{path} already exists; refusing to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    restrict_to_owner(path.parent)
    kp = Keypair()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(list(bytes(kp)), f)
    restrict_to_owner(path)
    return kp


def load_keypair(path: Path) -> Keypair:
    if not path.is_file():
        raise SystemExit(f"No keypair at {path}. Run: python -m oath_core init")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Keypair.from_bytes(bytes(raw))
