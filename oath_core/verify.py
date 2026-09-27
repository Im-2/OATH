"""Independent verification from chain data alone (SPEC §5.5).

    python -m oath_core.verify --notary <pubkey> [--rpc URL] [--out report.json]

Needs no account, no API and no ledger: only the notary pubkey and an RPC.
Exit code 0 = every check passed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from collections import defaultdict
from decimal import Decimal

from . import memo as memos
from .config import DEFAULT_RPC_URL, MEMO_PROGRAM_ID, USDC_MINT
from .fills import FillError, asset_delta, compute_fill, signers
from .grader import aggregate, grade_trade
from .solana_rpc import Rpc
from .thesis import ThesisError, digest, parse_canonical

# Public policy bounds used before a thesis is revealed (its own horizon is still secret).
MAX_HORIZON_MIN = 360
REVEAL_GRACE_MIN = 30
SIZE_TOLERANCE = Decimal("0.01")   # entry USDC within ±1% of committed size_usd
QTY_TOLERANCE = Decimal("0.005")   # exit sells the entry quantity within 0.5%


def memo_texts(tx: dict) -> list[str]:
    return [ix["parsed"] for ix in tx["transaction"]["message"]["instructions"]
            if ix.get("programId") == MEMO_PROGRAM_ID and isinstance(ix.get("parsed"), str)]


def collect(rpc, notary: str) -> list[dict]:
    """Every successful tx SIGNED by the notary, oldest first, with its oath1 memos."""
    out = []
    for s in reversed(rpc.get_signatures_for_address(notary)):
        if s.get("err"):
            continue
        tx = rpc.get_transaction(s["signature"])
        if not tx or tx["meta"].get("err") is not None or notary not in signers(tx):
            continue  # memos in txs that merely mention the notary are not the notary's word
        parsed = []
        for text in memo_texts(tx):
            try:
                parsed.append(memos.parse(text))
            except memos.MemoError:
                continue
        if parsed:
            out.append({"sig": s["signature"], "slot": tx["slot"], "block_time": tx.get("blockTime"),
                        "memos": parsed})
    return out


def verify(rpc, notary: str, *, now: float | None = None, scan_agent: bool = True) -> dict:
    now = now or time.time()
    txs = collect(rpc, notary)
    issues: list[str] = []
    by_agent: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for t in txs:
        theses = {m.seq: m.fields["thesis"] for m in t["memos"] if m.kind == "t"}
        for m in t["memos"]:
            if m.kind == "t":
                continue
            rec = {"sig": t["sig"], "slot": t["slot"], "block_time": t["block_time"], **m.fields}
            if m.kind == "r":
                rec["thesis_raw"] = theses.get(m.seq)
            by_agent[m.agent][m.seq][m.kind].append(rec)

    report_agents = {}
    for agent, seqs in by_agent.items():
        rows, trades, unrevealed = [], [], []
        committed = open_count = 0
        numbered = sorted(s for s, k in seqs.items() if k.get("c") or k.get("b"))
        expected = list(range(1, (max(numbered) if numbered else 0) + 1))
        gaps = sorted(set(expected) - set(numbered))
        if gaps:
            issues.append(f"{agent}: sequence gaps {gaps}")
        orphans = sorted(set(seqs) - set(numbered))
        if orphans:
            issues.append(f"{agent}: memos for seqs with no commitment {orphans}")
        swap_sigs: set[str] = set()

        for seq in numbered:
            k = seqs[seq]
            row = {"seq": seq, "problems": []}
            p = row["problems"]
            if len(k.get("c", [])) + len(k.get("b", [])) > 1:
                p.append("duplicate commitment for seq")
            if k.get("b"):
                row["status"] = "blocked"
                rows.append(row)
                continue
            committed += 1
            c = k["c"][0]
            row.update(commit_sig=c["sig"], commit_slot=c["slot"], digest=c["digest"])
            o = k.get("o", [None])[0]
            r = k.get("r", [None])[0]
            entry = exit_fill = None
            swap_tx = None
            if o:
                row.update(open_sig=o["sig"], swap_sig=o["swap_sig"])
                swap_sigs.add(o["swap_sig"])
                swap_tx = rpc.get_transaction(o["swap_sig"])
                if not swap_tx:
                    p.append("entry swap tx not found")
                else:
                    row["swap_slot"] = swap_tx["slot"]
                    if not swap_tx["slot"] > c["slot"]:
                        p.append(f"entry swap (slot {swap_tx['slot']}) did not land after commit (slot {c['slot']})")
                    if not o["slot"] > c["slot"]:
                        p.append("open memo did not land after commit")
            if not r:
                ref_time = (swap_tx or {}).get("blockTime") or c["block_time"] or now
                deadline = ref_time + (MAX_HORIZON_MIN + REVEAL_GRACE_MIN) * 60
                if now > deadline:
                    row["status"] = "unrevealed"
                    p.append("reveal deadline passed without reveal")
                    # The thesis (and its size) is still secret; the entry swap's USDC spend is on-chain.
                    spent = -asset_delta(swap_tx, agent, USDC_MINT)[0] if swap_tx else 0
                    unrevealed.append({"seq": seq, "size_usd": str(Decimal(max(spent, 0)).scaleb(-6))})
                else:
                    row["status"] = "open" if o else "committed"
                    open_count += 1
                row["reveal_deadline"] = dt.datetime.fromtimestamp(deadline, dt.timezone.utc).isoformat()
                rows.append(row)
                continue

            row.update(reveal_sig=r["sig"], exit_sig=r["exit_sig"], exit_reason=r["exit_reason"])
            try:
                thesis = parse_canonical(r["thesis_raw"] or "")
            except ThesisError as e:
                p.append(f"revealed thesis invalid: {e}")
                row["status"] = "invalid"
                rows.append(row)
                continue
            recomputed = digest(r["thesis_raw"].encode("utf-8"), bytes.fromhex(r["salt_hex"]))
            row["digest_ok"] = recomputed == c["digest"]
            if not row["digest_ok"]:
                p.append("sha256(thesis || salt) != committed digest")
            if thesis["seq"] != str(seq) or thesis["agent"] != agent:
                p.append("revealed thesis seq/agent does not match memo")
            if not r["slot"] > c["slot"]:
                p.append("reveal did not land after commit")
            row["thesis"] = thesis

            if o and swap_tx:
                try:
                    entry = compute_fill(swap_tx, o["swap_sig"], agent, thesis["in_mint"], thesis["out_mint"])
                except FillError as e:
                    p.append(f"entry swap does not match thesis: {e}")
                if entry:
                    size_raw = Decimal(thesis["size_usd"]) * 10**6
                    if abs(Decimal(entry.in_raw) - size_raw) > size_raw * SIZE_TOLERANCE:
                        p.append(f"entry spent {entry.in_raw} raw vs committed size {thesis['size_usd']}")
            if r["exit_reason"] == "exec_failed":
                if o:
                    p.append("exec_failed reveal but an open memo exists")
            elif not o:
                p.append("reveal with an exit but no open memo")
            elif entry:
                exit_tx = rpc.get_transaction(r["exit_sig"])
                try:
                    exit_fill = compute_fill(exit_tx, r["exit_sig"], agent, thesis["out_mint"], thesis["in_mint"])
                except FillError as e:
                    p.append(f"exit swap invalid: {e}")
                if exit_fill:
                    swap_sigs.add(r["exit_sig"])
                    row["exit_slot"] = exit_fill.slot
                    if not exit_fill.slot > entry.slot:
                        p.append("exit swap did not land after entry")
                    if not r["slot"] > exit_fill.slot:
                        p.append("reveal did not land after exit swap")
                    if abs(exit_fill.in_raw - entry.out_raw) > entry.out_raw * QTY_TOLERANCE:
                        p.append(f"exit sold {exit_fill.in_raw} vs entry qty {entry.out_raw}")
            if entry:
                row["entry_fill"] = entry.to_dict()
            if exit_fill:
                row["exit_fill"] = exit_fill.to_dict()
            if entry and (exit_fill or r["exit_reason"] == "exec_failed"):
                g = grade_trade(thesis, entry.to_dict(), exit_fill.to_dict() if exit_fill else None, r["exit_reason"])
                row["grade"] = g
                trades.append(g)
            elif r["exit_reason"] == "exec_failed" and not o:
                trades.append({"seq": seq, "closed": False, "exit_reason": "exec_failed"})
            row["status"] = "revealed" if not p else "invalid"
            rows.append(row)

        for row in rows:
            issues.extend(f"{agent} seq {row['seq']}: {msg}" for msg in row["problems"])

        uncommitted = []
        if scan_agent and txs:
            first_commit_time = min((t["block_time"] or 0) for t in txs)
            uncommitted = scan_uncommitted(rpc, agent, swap_sigs, first_commit_time)
            issues.extend(f"{agent}: uncommitted trade {u['sig']}" for u in uncommitted)

        report_agents[agent] = {
            "positions": rows, "gaps": gaps,
            "stats": aggregate(trades, committed=committed, open_count=open_count, unrevealed=unrevealed),
            "uncommitted_trades": uncommitted,
        }

    return {
        "notary": notary,
        "checked_at": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(),
        "notary_txs_with_oath1_memos": len(txs),
        "agents": report_agents,
        "issues": issues,
        "pass": not issues and bool(txs),
    }


def scan_uncommitted(rpc, agent: str, known_sigs: set[str], since: int) -> list[dict]:
    """Agent-wallet txs after the first commitment that moved USDC but are no committed entry/exit."""
    out = []
    for s in rpc.get_signatures_for_address(agent):
        if (s.get("blockTime") or 0) < since:
            continue
        if s.get("err") or s["signature"] in known_sigs:
            continue
        tx = rpc.get_transaction(s["signature"])
        if not tx or agent not in signers(tx):
            continue
        d_usdc, _, _ = asset_delta(tx, agent, USDC_MINT)
        if d_usdc != 0:
            out.append({"sig": s["signature"], "slot": tx["slot"], "usdc_delta_raw": d_usdc})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify an OATH record from chain data alone.")
    ap.add_argument("--notary", required=True, help="notary public key")
    ap.add_argument("--rpc", default=DEFAULT_RPC_URL)
    ap.add_argument("--out", help="write the JSON report here")
    ap.add_argument("--no-agent-scan", action="store_true", help="skip the uncommitted-trade scan")
    a = ap.parse_args(argv)
    report = verify(Rpc(a.rpc), a.notary, scan_agent=not a.no_agent_scan)
    text = json.dumps(report, indent=2, default=str)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    for agent, ag in report["agents"].items():
        print(f"agent {agent}: {ag['stats']}")
        for row in ag["positions"]:
            g = row.get("grade") or {}
            print(f"  seq {row['seq']:>3} {row.get('status'):<10} digest_ok={row.get('digest_ok')} "
                  f"pnl={g.get('pnl_usd')} reason={row.get('exit_reason')}")
    print("ISSUES:" if report["issues"] else "no issues", *report["issues"], sep="\n  ")
    print("PASS" if report["pass"] else "FAIL")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
