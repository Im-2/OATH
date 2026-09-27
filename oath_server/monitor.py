"""oath-server monitor (SPEC §5.3): deterministic exits + reveals + deadline sweeper.

    python -m oath_server.monitor              # loop every 20 s (executes exits and reveals)
    python -m oath_server.monitor --once       # one pass
    python -m oath_server.monitor --dry-run    # decide only: print what it would do, send nothing

Per open position, each tick:
  price <= stop -> exit 'stop';  price >= tp -> exit 'tp';  now >= entry + horizon -> exit 'expiry'
  exit = swap exactly the entry quantity back, then reveal thesis + salt on-chain.
Unknown price -> hold (never exit on a guess), except expiry, which needs no price.
'closed' positions (exit done, reveal failed) are re-revealed. Past the reveal deadline
(entry + horizon + grace) the sweeper posts one oath1:s memo; the position is still closed
and revealed (late), and verify reports it as late.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import time
from decimal import Decimal

from oath_core.flow import Ctx, close_position
from oath_core.config import SOL_MINT
from oath_core.market import price_info, snapshot_equity

log = logging.getLogger("oath.monitor")
INTERVAL_S = 20


def _iso_to_ts(s: str | None) -> float | None:
    if not s:
        return None
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()


def entry_time(pos: dict) -> float | None:
    """Horizon starts at the entry swap's on-chain time; ledger time is the fallback."""
    if pos.get("entry_fill_json"):
        bt = json.loads(pos["entry_fill_json"]).get("block_time")
        if bt:
            return float(bt)
    return _iso_to_ts(pos.get("opened_at"))


def decide(thesis: dict, price: Decimal | None, now: float, t_entry: float | None) -> str | None:
    """Exit reason, or None to hold. Pure."""
    if price is not None:
        if price <= Decimal(thesis["stop"]):
            return "stop"
        if price >= Decimal(thesis["tp"]):
            return "tp"
    if t_entry is not None and now >= t_entry + int(thesis["horizon_min"]) * 60:
        return "expiry"
    return None


def _slashed(ctx: Ctx, seq: int) -> bool:
    return any(e["kind"] == "slash" for e in ctx.ledger.events(seq))


def run_once(ctx: Ctx, *, now: float | None = None, dry_run: bool = False) -> list[dict]:
    now = now or time.time()
    policy = ctx.load_policy()
    actions: list[dict] = []
    prices: dict[str, Decimal | None] = {}

    def price(mint: str) -> Decimal | None:
        if mint not in prices:
            info = price_info(ctx.cp, mint)
            prices[mint] = info.usd if info else None
        return prices[mint]

    for pos in ctx.ledger.positions():
        seq, status = pos["seq"], pos["status"]
        if status not in ("open", "closed", "committed"):
            continue
        thesis = json.loads(pos["thesis_json"])
        t0 = entry_time(pos) or _iso_to_ts(pos.get("opened_at"))
        deadline = (t0 + (int(thesis["horizon_min"]) + policy.reveal_grace_min) * 60) if t0 else None

        # Deadline sweeper: one slash memo per overdue position (bond slashing lands in Phase 3).
        if deadline and now > deadline and not _slashed(ctx, seq):
            act = {"seq": seq, "action": "slash", "reason": "missed_reveal"}
            if not dry_run:
                try:
                    s = ctx.notary.slash(ctx.cfg.agent_wallet, seq, "missed_reveal")
                    ctx.ledger.record(seq, "slash", {"reason": "missed_reveal"}, tx_sig=s.sig, slot=s.slot,
                                      bond_status="slashed")
                    act["sig"] = s.sig
                except Exception as e:  # noqa: BLE001 - logged, retried next tick
                    act["error"] = repr(e)[:300]
            actions.append(act)

        if status == "committed":
            continue  # entry never confirmed: needs the operator's `recover` (never automated)
        if status == "closed":
            act = {"seq": seq, "action": "reveal", "reason": pos["exit_reason"]}
            if not dry_run:
                try:
                    act["result"] = close_position(ctx, seq, pos["exit_reason"])
                except Exception as e:  # noqa: BLE001
                    act["error"] = repr(e)[:300]
            actions.append(act)
            continue

        px = price(thesis["out_mint"])
        reason = decide(thesis, px, now, t0)
        if reason is None:
            if px is None:
                actions.append({"seq": seq, "action": "hold", "note": "price_unavailable"})
            continue
        act = {"seq": seq, "action": "exit", "reason": reason, "price": str(px)}
        if not dry_run:
            try:
                act["result"] = close_position(ctx, seq, reason)
            except Exception as e:  # noqa: BLE001 - FlowError or RPC failure; never crash the loop
                act["error"] = repr(e)[:300]
        actions.append(act)

    if not dry_run:
        sol = price(SOL_MINT)
        if sol is not None:
            try:
                snapshot_equity(ctx.ledger, ctx.rpc, ctx.cfg.agent_wallet, sol, "monitor")
            except Exception as e:  # noqa: BLE001
                log.warning("equity snapshot failed: %r", e)
    return actions


def build_ctx():
    from oath_core.clawpump import StdioClawPump
    from oath_core.config import LEDGER_PATH, NOTARY_PATH, load_config
    from oath_core.executor import ExecTokens
    from oath_core.keys import load_keypair
    from oath_core.ledger import Ledger
    from oath_core.notary import Notary
    from oath_core.solana_rpc import Rpc

    cfg = load_config()
    rpc = Rpc(cfg.effective_rpc_url)
    cp = StdioClawPump(timeout_s=120)
    return cp, Ctx(cfg, rpc, Notary(load_keypair(NOTARY_PATH), rpc), Ledger(LEDGER_PATH), cp, ExecTokens())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OATH monitor: stop/TP/expiry exits, reveals, deadline sweeper")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="decide only; send nothing")
    ap.add_argument("--interval", type=int, default=INTERVAL_S)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cp, ctx = build_ctx()
    with cp:
        while True:
            try:
                actions = run_once(ctx, dry_run=a.dry_run)
            except Exception as e:  # noqa: BLE001 - keep the loop alive; fail closed per position
                log.exception("tick failed: %r", e)
                actions = []
            for act in actions:
                log.info(json.dumps(act, default=str))
            if not actions:
                log.info("tick: nothing to do (%d open)", len(ctx.ledger.positions("open")))
            if a.once or a.dry_run:
                return 0
            time.sleep(a.interval)


if __name__ == "__main__":
    raise SystemExit(main())

