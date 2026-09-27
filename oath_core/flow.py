"""Operator flows: open (commit -> swap -> open memo), close (exit swap -> reveal), recover.

Order of durability: thesis + salt hit the ledger before the commit memo is
sent; every on-chain step is recorded as soon as it confirms. Any failure
leaves the position in a state `recover` / `close` can finish honestly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from . import memo as memos
from .clawpump import ClawPump
from .config import SOL_MINT, USDC_MINT, Config
from .executor import ExecTokens, assert_agent_wallet, quote, swap
from .fills import asset_delta, signers
from .grader import grade_trade
from .ledger import Ledger, now_iso
from .notary import Notary
from .solana_rpc import Rpc, RpcError
from .thesis import ThesisError, build_thesis, canonical_json, digest, fmt_decimal, new_salt, validate
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


def open_position(ctx: Ctx, *, mkt: str, size_usd, entry, stop=None, tp=None, stop_pct=None,
                  tp_pct=None, horizon_min: int, conf, strat: str, why: str, dry_run: bool = False) -> dict:
    cfg, agent = ctx.cfg, ctx.cfg.agent_wallet
    unresolved = [p["seq"] for p in ctx.ledger.positions() if p["status"] in ("prepared", "committed")]
    if unresolved:
        raise FlowError(f"unresolved positions {unresolved}; run `recover --seq N` first")
    if mkt not in MKT_MINTS:
        raise FlowError(f"unsupported market {mkt} (v1: {list(MKT_MINTS)})")
    in_mint, out_mint = MKT_MINTS[mkt]
    size = Decimal(fmt_decimal(size_usd, 2))
    if not Decimal(0) < size <= Decimal(cfg.max_trade_usd):
        raise FlowError(f"size_usd {size} outside (0, {cfg.max_trade_usd}]")
    if horizon_min > cfg.max_horizon_min:
        raise FlowError(f"horizon_min {horizon_min} > cap {cfg.max_horizon_min}")

    _notary_funded(ctx, 3, dry_run)  # commit + open + reveal
    assert_agent_wallet(ctx.cp, cfg)
    pf = ctx.cp.call("get_portfolio", {"agent_id": cfg.agent_id})
    if Decimal(str(pf.get("usdc_balance", "0"))) < size:
        raise FlowError(f"agent USDC balance {pf.get('usdc_balance')} < size {size}")

    in_raw = int(size * 10**6)
    q = quote(ctx.cp, cfg, in_mint, out_mint, in_raw)
    if str(entry).lower() == "market":
        entry_px = q.price
    else:
        entry_px = Decimal(str(entry))
        dev = abs(q.price - entry_px) / entry_px * 100
        if dev > Decimal(cfg.max_entry_slippage_pct):
            raise FlowError(f"quote {q.price:.6f} is {dev:.2f}% from entry {entry_px} (> {cfg.max_entry_slippage_pct}%)")
    stop_px = Decimal(str(stop)) if stop is not None else _pct(entry_px, stop_pct, -1)
    tp_px = Decimal(str(tp)) if tp is not None else _pct(entry_px, tp_pct, +1)

    seq = ctx.ledger.next_seq(agent)
    try:
        thesis = build_thesis(agent=agent, seq=seq, mkt=mkt, in_mint=in_mint, out_mint=out_mint,
                              size_usd=size, entry=entry_px, stop=stop_px, tp=tp_px, horizon_min=horizon_min,
                              conf=conf, strat=strat, why=why)
        validate(thesis, max_size_usd=Decimal(cfg.max_trade_usd), max_horizon_min=cfg.max_horizon_min)
    except ThesisError as e:
        raise FlowError(f"thesis rejected: {e}") from e
    canon = canonical_json(thesis)
    salt = new_salt()
    dg = digest(canon, salt)

    if dry_run:
        sim_commit = ctx.notary.simulate([memos.commit(agent, seq, dg, 0)])
        sim_reveal = ctx.notary.simulate([memos.reveal(agent, seq, salt.hex(), "1" * 88, "manual"),
                                          memos.thesis(seq, canon)])
        return {"dry_run": True, "thesis": thesis, "digest": dg, "quote_price": str(q.price),
                "quote_out_raw": q.out_raw, "simulate_commit": sim_commit, "simulate_reveal": sim_reveal}

    ctx.ledger.prepare(agent, seq, thesis, salt.hex(), dg)
    c = ctx.notary.commit(agent, seq, dg, 0)
    ctx.ledger.record(seq, "commit", {"digest": dg}, tx_sig=c.sig, slot=c.slot,
                      status="committed", commit_sig=c.sig, commit_slot=c.slot)

    try:
        res = swap(ctx.cp, ctx.rpc, cfg, ctx.tokens, ctx.tokens.issue(seq), seq, in_mint, out_mint, in_raw)
    except Exception as e:  # no auto-retry: an errored call may still have landed on-chain
        ctx.ledger.record(seq, "error", {"stage": "entry_swap", "error": repr(e)[:500]})
        raise FlowError(f"COMMITTED seq {seq} ({c.sig}) but entry swap failed: {e}. "
                        f"Run `recover --seq {seq}`.") from e
    fill = res.fill
    alerts = []
    if not fill.slot > c.slot:
        alerts.append(f"entry swap slot {fill.slot} <= commit slot {c.slot}: record is INVALID")
    o = ctx.notary.open(agent, seq, fill.sig)
    ctx.ledger.record(seq, "open", {"fill": fill.to_dict(), "clawpump_response": res.response, "alerts": alerts},
                      tx_sig=o.sig, slot=o.slot, status="open", open_sig=o.sig, swap_sig=fill.sig,
                      swap_slot=fill.slot, entry_fill_json=json.dumps(fill.to_dict()), opened_at=now_iso())
    return {"seq": seq, "digest": dg, "commit_sig": c.sig, "commit_slot": c.slot, "swap_sig": fill.sig,
            "swap_slot": fill.slot, "open_sig": o.sig, "fill": fill.to_dict(), "thesis": thesis, "alerts": alerts}


def close_position(ctx: Ctx, seq: int, reason: str = "manual") -> dict:
    if reason not in memos.EXIT_REASONS - {"exec_failed"}:
        raise FlowError(f"bad exit reason {reason}")
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
                       thesis["out_mint"], thesis["in_mint"], qty)
        except Exception as e:
            ctx.ledger.record(seq, "error", {"stage": "exit_swap", "error": repr(e)[:500]})
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
                        f"position's entry, it must be linked manually (not automated in Phase 1).")
    return _reveal(ctx, pos, thesis, memos.NO_SIG, "exec_failed")
