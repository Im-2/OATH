"""Operator/agent flows: open (firewall -> commit -> swap -> open memo), close (exit -> reveal), recover.

Order of durability: thesis + salt hit the ledger before any memo is sent; every
on-chain step is recorded as soon as it confirms. Any failure leaves the position
in a state `recover` / `close` / the monitor can finish honestly.

Refusal kinds:
  FlowError before a seq is assigned  -> malformed request; nothing recorded anywhere.
  firewall BLOCK                      -> seq consumed, oath1:b memo on-chain (SPEC §4.3).
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable

from . import memo as memos
from .clawpump import ClawPump, ClawPumpError
from .config import SOL_MINT, USDC_MINT, Config
from .executor import ExecTokens, assert_agent_wallet, quote, swap
from .fills import asset_delta, signers
from .firewall import Decision, MarketState, evaluate
from .grader import grade_trade
from .ledger import Ledger, now_iso
from .market import equity_usd, price_info, realised_pnl_today
from .notary import Notary
from .policy import Policy, load_policy
from .solana_rpc import Rpc, RpcError
from . import testmode
from .thesis import ThesisError, build_thesis, canonical_json, digest, fmt_decimal, new_salt
from .verify import collect

MKT_MINTS = {"SOL/USDC": (USDC_MINT, SOL_MINT)}
SWAP_FEE_RESERVE = 105_000  # highest ClawPump swap fee observed (Phase 0), lamports


class FlowError(RuntimeError):
    """Refused (fail closed). Nothing irreversible happened unless the message says so."""


@dataclass
class Ctx:
    cfg: Config
    rpc: Rpc
    notary: Notary
    ledger: Ledger
    cp: ClawPump
    tokens: ExecTokens
    load_policy: Callable[[], Policy] = field(default=load_policy)
    testmode_path: Path = field(default=testmode.TESTMODE_PATH)


def _notary_funded(ctx: Ctx, n_txs: int, dry_run: bool = False) -> None:
    """Refuse before any irreversible step if the notary cannot pay for every memo still owed.
    A dry run only needs the account to exist (simulation charges nothing)."""
    try:
        ctx.notary.assert_funded(n_txs)
    except RpcError as e:
        if not (dry_run and ctx.rpc.get_balance(ctx.notary.pubkey) > 0):
            raise FlowError(str(e)) from e


def _pct(base: Decimal, pct, sign: int) -> Decimal:
    return base * (1 + sign * Decimal(str(pct)) / 100)


def market_state(ctx: Ctx, out_mint: str, quote_price: Decimal | None, *, record: bool) -> MarketState:
    """Gather firewall inputs. Anything unreadable becomes None, which the firewall blocks on."""
    out_info = price_info(ctx.cp, out_mint)
    sol_info = out_info if out_mint == SOL_MINT else price_info(ctx.cp, SOL_MINT)
    eq = None
    if sol_info is not None:
        try:
            eq = equity_usd(ctx.rpc, ctx.cfg.agent_wallet, sol_info.usd)
        except (RpcError, KeyError, TypeError, ValueError):
            eq = None
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    if eq is not None and record:
        ctx.ledger.snapshot_equity(eq, "open")
    peak = ctx.ledger.equity_peak()
    day0 = ctx.ledger.equity_day_start(today)
    if eq is not None:  # a dry run (no snapshot written) still sees the live value
        peak = max(peak, eq) if peak is not None else eq
        day0 = day0 if day0 is not None else eq
    return MarketState(
        quote_price=quote_price,
        out_liquidity_usd=out_info.liquidity_usd if out_info else None,
        open_positions=ctx.ledger.open_count(),
        equity_usd=eq, peak_equity_usd=peak, day_start_equity_usd=day0,
        realised_pnl_today_usd=realised_pnl_today(ctx.ledger),
    )


def open_position(ctx: Ctx, *, mkt: str, size_usd, entry, stop=None, tp=None, stop_pct=None,
                  tp_pct=None, horizon_min: int, conf, strat: str, why: str, dry_run: bool = False) -> dict:
    policy = ctx.load_policy()
    cfg, agent = ctx.cfg, ctx.cfg.agent_wallet
    unresolved = [p["seq"] for p in ctx.ledger.positions() if p["status"] in ("prepared", "committed")]
    if unresolved:
        raise FlowError(f"unresolved positions {unresolved}; operator must run `recover --seq N` first")
    if mkt not in MKT_MINTS:
        raise FlowError(f"unsupported market {mkt} (v1 supports {list(MKT_MINTS)})")
    in_mint, out_mint = MKT_MINTS[mkt]
    try:
        size = Decimal(fmt_decimal(size_usd, 2))
    except ThesisError as e:
        raise FlowError(f"bad size_usd: {e}") from e
    if size <= 0:
        raise FlowError("size_usd must be > 0")
    if (stop is None) == (stop_pct is None) or (tp is None) == (tp_pct is None):
        raise FlowError("give exactly one of stop/stop_pct and one of tp/tp_pct")
    is_test = strat == testmode.TEST_STRAT
    if is_test and not testmode.status(ctx.testmode_path).get("armed"):
        raise FlowError(f"strat '{testmode.TEST_STRAT}' is reserved for operator test mode, which is not armed")

    assert_agent_wallet(ctx.cp, cfg)
    in_raw = int(size * 10**6)
    try:
        q = quote(ctx.cp, cfg, in_mint, out_mint, in_raw, policy.swap_slippage_bps)
        quote_price = q.price
    except ClawPumpError:
        q, quote_price = None, None
    if str(entry).lower() == "market":
        if quote_price is None:
            raise FlowError("entry='market' but no executable quote is available")
        entry_px = quote_price
    else:
        entry_px = Decimal(str(entry))
    stop_px = Decimal(str(stop)) if stop is not None else _pct(entry_px, stop_pct, -1)
    tp_px = Decimal(str(tp)) if tp is not None else _pct(entry_px, tp_pct, +1)

    seq = ctx.ledger.next_seq(agent)
    try:
        thesis = build_thesis(agent=agent, seq=seq, mkt=mkt, in_mint=in_mint, out_mint=out_mint,
                              size_usd=size, entry=entry_px, stop=stop_px, tp=tp_px, horizon_min=int(horizon_min),
                              conf=conf, strat=strat, why=why)
    except (ThesisError, ValueError, TypeError) as e:
        raise FlowError(f"thesis rejected: {e}") from e
    canon = canonical_json(thesis)
    salt = new_salt()
    dg = digest(canon, salt)

    decision: Decision = evaluate(thesis, market_state(ctx, out_mint, quote_price, record=not dry_run), policy)
    base = {"seq": seq, "digest": dg, "thesis": thesis, "quote_price": str(quote_price),
            "firewall": {"approve": decision.approve, "reason": decision.reason, "detail": decision.detail}}

    if dry_run:
        if decision.approve:
            sims = {"simulate_commit": ctx.notary.simulate([memos.commit(agent, seq, dg, 0)]),
                    "simulate_reveal": ctx.notary.simulate([memos.reveal(agent, seq, salt.hex(), "1" * 88, "manual"),
                                                            memos.thesis(seq, canon)])}
        else:
            sims = {"simulate_blocked": ctx.notary.simulate([memos.blocked(agent, seq, dg, decision.reason)])}
        return {"dry_run": True, **base, **sims}

    if not decision.approve:
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if ctx.ledger.count_events_since("blocked", since) >= policy.max_blocked_per_hour:
            raise FlowError(f"blocked by firewall ({decision.reason}: {decision.detail}); blocked-memo rate "
                            f"limit ({policy.max_blocked_per_hour}/h) reached, so this refusal is not recorded on-chain")
        _notary_funded(ctx, 1)
        ctx.ledger.prepare(agent, seq, thesis, salt.hex(), dg)
        b = ctx.notary.blocked(agent, seq, dg, decision.reason)
        ctx.ledger.record(seq, "blocked", {"reason": decision.reason, "detail": decision.detail}, tx_sig=b.sig,
                          slot=b.slot, status="blocked", commit_sig=b.sig, commit_slot=b.slot, closed_at=now_iso())
        # Blocked theses are revealed immediately (SPEC §4.3): thesis + salt are public for this seq.
        return {"ok": False, "blocked": True, **base, "blocked_sig": b.sig, "salt_hex": salt.hex()}

    _notary_funded(ctx, 3)  # commit + open + reveal
    if is_test:
        try:
            testmode.consume(ctx.testmode_path)  # one-shot: spent only when a commit is about to happen
        except testmode.TestModeError as e:
            raise FlowError(str(e)) from e
    ctx.ledger.prepare(agent, seq, thesis, salt.hex(), dg)
    c = ctx.notary.commit(agent, seq, dg, 0)
    ctx.ledger.record(seq, "commit", {"digest": dg}, tx_sig=c.sig, slot=c.slot,
                      status="committed", commit_sig=c.sig, commit_slot=c.slot)
    try:
        res = swap(ctx.cp, ctx.rpc, cfg, ctx.tokens, ctx.tokens.issue(seq), seq, in_mint, out_mint, in_raw,
                   slippage_bps=policy.swap_slippage_bps, allowed_mints=policy.allowed_mints)
    except Exception as e:  # no auto-retry: an errored call may still have landed on-chain
        ctx.ledger.record(seq, "error", {"stage": "entry_swap", "error": repr(e)[:500]})
        raise FlowError(f"COMMITTED seq {seq} ({c.sig}) but entry swap failed: {e}. "
                        f"Operator: run `recover --seq {seq}`.") from e
    fill = res.fill
    alerts = []
    if not fill.slot > c.slot:
        alerts.append(f"entry swap slot {fill.slot} <= commit slot {c.slot}: record is INVALID")
    o = ctx.notary.open(agent, seq, fill.sig)
    ctx.ledger.record(seq, "open", {"fill": fill.to_dict(), "clawpump_response": res.response, "alerts": alerts},
                      tx_sig=o.sig, slot=o.slot, status="open", open_sig=o.sig, swap_sig=fill.sig,
                      swap_slot=fill.slot, entry_fill_json=json.dumps(fill.to_dict()), opened_at=now_iso())
    return {"ok": True, **base, "commit_sig": c.sig, "commit_slot": c.slot, "swap_sig": fill.sig,
            "swap_slot": fill.slot, "open_sig": o.sig, "fill": fill.to_dict(), "alerts": alerts}


def close_position(ctx: Ctx, seq: int, reason: str = "manual") -> dict:
    if reason not in memos.EXIT_REASONS - {"exec_failed"}:
        raise FlowError(f"bad exit reason {reason}")
    policy = ctx.load_policy()
    pos = ctx.ledger.position(seq)
    thesis = json.loads(pos["thesis_json"])
    if pos["status"] in ("open", "closed"):
        _notary_funded(ctx, 1)  # the reveal must be affordable before we exit
    if pos["status"] == "open":
        entry = json.loads(pos["entry_fill_json"])
        qty = int(entry["out_raw"])
        if thesis["out_mint"] == SOL_MINT:
            # Selling SOL wraps it into a temporary wSOL account: the agent must also cover that
            # account's rent (refunded in the same tx), its own rent-exempt minimum and the fee.
            need = qty + ctx.rpc.get_min_rent(165) + ctx.rpc.get_min_rent(0) + SWAP_FEE_RESERVE
            bal = ctx.rpc.get_balance(ctx.cfg.agent_wallet)
            if bal < need:
                raise FlowError(f"agent holds {bal} lamports; selling {qty} needs {need}")
        try:
            res = swap(ctx.cp, ctx.rpc, ctx.cfg, ctx.tokens, ctx.tokens.issue(seq), seq,
                       thesis["out_mint"], thesis["in_mint"], qty,
                       slippage_bps=policy.swap_slippage_bps, allowed_mints=policy.allowed_mints)
        except Exception as e:
            ctx.ledger.record(seq, "error", {"stage": "exit_swap", "reason": reason, "error": repr(e)[:500]})
            raise FlowError(f"exit swap failed for seq {seq}: {e}. Check the agent wallet before retrying.") from e
        f = res.fill
        ctx.ledger.record(seq, "close", {"fill": f.to_dict(), "clawpump_response": res.response},
                          tx_sig=f.sig, slot=f.slot, status="closed", exit_sig=f.sig, exit_slot=f.slot,
                          exit_reason=reason, exit_fill_json=json.dumps(f.to_dict()), closed_at=now_iso())
        pos = ctx.ledger.position(seq)
    if pos["status"] != "closed":
        raise FlowError(f"seq {seq} is {pos['status']}, expected open or closed")
    return _reveal(ctx, pos, thesis, pos["exit_sig"], pos["exit_reason"])


def _reveal(ctx: Ctx, pos: dict, thesis: dict, exit_sig: str, reason: str) -> dict:
    seq = pos["seq"]
    canon = canonical_json(thesis)
    salt = bytes.fromhex(pos["salt_hex"])
    if digest(canon, salt) != pos["digest"]:
        raise FlowError("ledger thesis/salt no longer match the committed digest; refusing to reveal")
    r = ctx.notary.reveal(ctx.cfg.agent_wallet, seq, salt, exit_sig, reason, canon)
    grade = None
    if pos.get("entry_fill_json") and pos.get("exit_fill_json"):
        grade = grade_trade(thesis, json.loads(pos["entry_fill_json"]), json.loads(pos["exit_fill_json"]), reason)
    ctx.ledger.record(seq, "reveal", {"grade": grade}, tx_sig=r.sig, slot=r.slot, status="revealed",
                      reveal_sig=r.sig, reveal_slot=r.slot, pnl_usd=(grade or {}).get("pnl_usd"))
    return {"seq": seq, "reveal_sig": r.sig, "reveal_slot": r.slot, "exit_sig": exit_sig,
            "exit_reason": reason, "grade": grade}


def recover(ctx: Ctx, seq: int) -> dict:
    """Finish a position stuck in 'prepared' or 'committed' without ever hiding it."""
    pos = ctx.ledger.position(seq)
    thesis = json.loads(pos["thesis_json"])
    agent = ctx.cfg.agent_wallet
    if pos["status"] == "prepared":
        found = [t for t in collect(ctx.rpc, ctx.notary.pubkey)
                 for m in t["memos"] if m.kind == "c" and m.seq == seq and m.fields["digest"] == pos["digest"]]
        _notary_funded(ctx, 1 if found else 2)  # (commit +) exec_failed reveal
        if found:
            c_sig, c_slot = found[0]["sig"], found[0]["slot"]
        else:
            c = ctx.notary.commit(agent, seq, pos["digest"], pos["bond_amt"])
            c_sig, c_slot = c.sig, c.slot
        ctx.ledger.record(seq, "commit", {"digest": pos["digest"], "recovered": True}, tx_sig=c_sig,
                          slot=c_slot, status="committed", commit_sig=c_sig, commit_slot=c_slot)
        pos = ctx.ledger.position(seq)
    if pos["status"] != "committed":
        raise FlowError(f"seq {seq} is {pos['status']}; nothing to recover")
    _notary_funded(ctx, 1)  # exec_failed reveal
    # Did an entry swap land after the commit despite the error? Never guess: look at the chain.
    suspects = []
    for s in ctx.rpc.get_signatures_for_address(agent):
        if s.get("err") or (s.get("slot") or 0) <= pos["commit_slot"]:
            continue
        tx = ctx.rpc.get_transaction(s["signature"])
        if tx and agent in signers(tx) and asset_delta(tx, agent, thesis["in_mint"])[0] < 0:
            suspects.append(s["signature"])
    if suspects:
        raise FlowError(f"agent wallet has swaps after the commit: {suspects}. Inspect them; if one is this "
                        f"position's entry, it must be linked manually (not automated).")
    return _reveal(ctx, pos, thesis, memos.NO_SIG, "exec_failed")
