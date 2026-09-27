"""OATH operator CLI.

  python -m oath_core init --agent-id ID --agent-wallet PUBKEY
  python -m oath_core status
  python -m oath_core open --mkt SOL/USDC --size 1.00 --entry market --stop-pct 3 --tp-pct 5 \
                           --horizon 60 --conf 0.6 --strat manual_test --why "..." [--dry-run]
  python -m oath_core close --seq N [--reason manual]
  python -m oath_core recover --seq N
  python -m oath_core verify [--out report.json]
  python -m oath_core policy [--set key=value ...]      # e.g. --set max_trade_usd=3.00
  python -m oath_core testmode {arm,status,disarm} [--minutes 30]   # operator acceptance test
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal

from .config import CONFIG_PATH, LEDGER_PATH, NOTARY_PATH, Config, load_config, save_config
from .keys import generate_keypair, load_keypair


def _ctx(cfg: Config):
    from .clawpump import StdioClawPump
    from .executor import ExecTokens
    from .flow import Ctx
    from .ledger import Ledger
    from .notary import Notary
    from .solana_rpc import Rpc

    rpc = Rpc(cfg.effective_rpc_url)
    cp = StdioClawPump()
    return cp, Ctx(cfg, rpc, Notary(load_keypair(NOTARY_PATH), rpc), Ledger(LEDGER_PATH), cp, ExecTokens())


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_init(a) -> int:
    if NOTARY_PATH.exists():
        pub = load_keypair(NOTARY_PATH).pubkey()
        print(f"notary keypair already exists (not overwritten): {pub}")
    else:
        pub = generate_keypair(NOTARY_PATH).pubkey()
        print(f"created notary keypair: {pub}")
    if a.agent_id and a.agent_wallet:
        save_config(Config(agent_id=a.agent_id, agent_wallet=a.agent_wallet))
        print(f"wrote {CONFIG_PATH}")
    return 0


def cmd_status(a) -> int:
    from .ledger import Ledger
    from .solana_rpc import Rpc

    cfg = load_config()
    rpc = Rpc(cfg.effective_rpc_url)
    from .notary import Notary

    nt = Notary(load_keypair(NOTARY_PATH), rpc)
    notary = nt.pubkey
    lam = rpc.get_balance(notary)
    need = nt.required_lamports(3)  # rent-exempt + commit/open/reveal, live rent and fee
    positions = Ledger(LEDGER_PATH).positions()
    _print({
        "notary": notary, "notary_sol": f"{Decimal(lam).scaleb(-9):f}",
        "notary_ok_for_round_trip": lam >= need, "notary_needs_lamports": need,
        "agent_id": cfg.agent_id, "agent_wallet": cfg.agent_wallet,
        "agent_sol": f"{Decimal(rpc.get_balance(cfg.agent_wallet)).scaleb(-9):f}",
        "positions": [{k: p[k] for k in ("seq", "status", "digest", "commit_sig", "swap_sig", "exit_sig",
                                          "reveal_sig", "pnl_usd")} for p in positions],
    })
    return 0


def cmd_open(a) -> int:
    from .flow import open_position

    if (a.stop is None) == (a.stop_pct is None) or (a.tp is None) == (a.tp_pct is None):
        raise SystemExit("give exactly one of --stop/--stop-pct and one of --tp/--tp-pct")
    cp, ctx = _ctx(load_config())
    with cp:
        _print(open_position(ctx, mkt=a.mkt, size_usd=a.size, entry=a.entry, stop=a.stop, tp=a.tp,
                             stop_pct=a.stop_pct, tp_pct=a.tp_pct, horizon_min=a.horizon, conf=a.conf,
                             strat=a.strat, why=a.why, dry_run=a.dry_run))
    return 0


def cmd_close(a) -> int:
    from .flow import close_position

    cp, ctx = _ctx(load_config())
    with cp:
        _print(close_position(ctx, a.seq, a.reason))
    return 0


def cmd_recover(a) -> int:
    from .flow import recover

    cp, ctx = _ctx(load_config())
    with cp:
        _print(recover(ctx, a.seq))
    return 0


def cmd_policy(a) -> int:
    from .policy import load_policy, save_policy, set_value

    pol = load_policy()
    for kv in a.set or []:
        if "=" not in kv:
            raise SystemExit(f"--set expects key=value, got {kv!r}")
        k, v = kv.split("=", 1)
        pol = set_value(pol, k.strip(), v.strip())
    if a.set:
        save_policy(pol)
    _print(pol.public())
    return 0


def cmd_testmode(a) -> int:
    from . import testmode

    if a.action == "arm":
        s = testmode.arm(a.minutes)
        print(f"ARMED: one '{testmode.TEST_STRAT}' position allowed until {s['expires_at']} "
              "(firewall, commit and reveal still apply)")
    elif a.action == "disarm":
        testmode.disarm()
        print("disarmed")
    _print(testmode.status())
    return 0


def cmd_verify(a) -> int:
    from .verify import main as verify_main

    cfg = load_config()
    argv = ["--notary", str(load_keypair(NOTARY_PATH).pubkey()), "--rpc", cfg.effective_rpc_url]
    if a.out:
        argv += ["--out", a.out]
    return verify_main(argv)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="oath")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create the notary keypair (never overwrites) and config")
    p.add_argument("--agent-id")
    p.add_argument("--agent-wallet")
    p.set_defaults(fn=cmd_init)

    sub.add_parser("status", help="balances + ledger positions").set_defaults(fn=cmd_status)

    p = sub.add_parser("open", help="commit a thesis, then execute the entry swap")
    p.add_argument("--mkt", default="SOL/USDC")
    p.add_argument("--size", required=True, help="USD size (Phase 1 cap in config)")
    p.add_argument("--entry", required=True, help="entry price, or 'market' to commit the live quote")
    p.add_argument("--stop", type=Decimal)
    p.add_argument("--stop-pct", type=Decimal)
    p.add_argument("--tp", type=Decimal)
    p.add_argument("--tp-pct", type=Decimal)
    p.add_argument("--horizon", type=int, required=True, help="minutes")
    p.add_argument("--conf", required=True)
    p.add_argument("--strat", required=True)
    p.add_argument("--why", required=True, help="<=140 chars, structured reason, not chain-of-thought")
    p.add_argument("--dry-run", action="store_true", help="all checks + memo simulation; no memo, no swap")
    p.set_defaults(fn=cmd_open)

    p = sub.add_parser("close", help="exit swap (if open) then reveal")
    p.add_argument("--seq", type=int, required=True)
    p.add_argument("--reason", default="manual", choices=["manual", "tp", "stop", "expiry"])
    p.set_defaults(fn=cmd_close)

    p = sub.add_parser("recover", help="finish a position stuck in prepared/committed")
    p.add_argument("--seq", type=int, required=True)
    p.set_defaults(fn=cmd_recover)

    p = sub.add_parser("policy", help="show or change the firewall policy (~/.oath/policy.json)")
    p.add_argument("--set", action="append", metavar="KEY=VALUE")
    p.set_defaults(fn=cmd_policy)

    p = sub.add_parser("testmode", help="operator acceptance-test mode (one forced position)")
    p.add_argument("action", choices=["arm", "status", "disarm"])
    p.add_argument("--minutes", type=int, default=30)
    p.set_defaults(fn=cmd_testmode)

    p = sub.add_parser("verify", help="independent chain-only verification of this notary")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_verify)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except Exception as e:  # surface refusals plainly; nothing is swallowed silently
        from .flow import FlowError
        if isinstance(e, FlowError):
            print(f"REFUSED: {e}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
