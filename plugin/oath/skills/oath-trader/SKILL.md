---
name: oath-trader
description: OATH trading playbook for SOL/USDC spot longs. How to decide, how to size, and how to set stop, take-profit and horizon you will be held to on-chain.
---

# OATH trader playbook

Everything you commit is public. Before the swap executes, a salted hash of your thesis goes on
Solana. When the position closes, the thesis itself is revealed and graded against what you said.
Missing a reveal counts as a full loss. The goal is not to trade often. It is to make calls you
are proud to have on the record.

## What you can do
- Read: `mcp__clawpump_stdio__get_price`, `swap_quote`, `get_indicators`, `get_market_signals`,
  `intelligence_market`, `intelligence_signals`, `intelligence_macro`, `get_news_feed`,
  `get_portfolio`, `token_search`.
- Act: `oath_open_position` (the only way to trade). `oath_status` shows your record and open positions.
  `oath_policy` shows the limits.
- You cannot close positions, transfer funds or place other orders. Exits are automatic at your
  committed stop, take-profit or horizon.

## Decision procedure (run it in this order)
1. `oath_status`. If you already have an open position in SOL/USDC, do not add another unless the
   user explicitly asks. If your last thesis was blocked, read the reason before doing anything else.
2. `oath_policy`. Note `max_trade_usd`, `stop_distance_pct_min/max` and `max_horizon_min`.
3. Gather evidence (at least three independent reads):
   - `get_price` for SOL: price and 24h change.
   - `intelligence_market` with `token: "SOL"`, plus `intelligence_signals`.
   - `get_indicators` (fear/greed, volume trend) or `get_market_signals` with `type: "top-movers"`.
4. Score the setup. Count the signals that agree on "up over the next 1-4 hours":
   - 24h change > 0 and price not in a sharp spike (24h change < +8%)
   - a bullish or neutral-to-bullish read from `intelligence_market` / `intelligence_signals`
   - a risk-on macro/indicator read (for example fear/greed not in extreme fear with falling volume)
   Trade only with **>= 2 agreeing signals and none strongly against**. Otherwise stand aside
   and explain why in one or two sentences to the user. Standing aside is a good outcome.
5. Get a live `swap_quote` for USDC -> SOL at your size and use `entry: "market"`, or give an
   explicit entry within 1% of the quote.

## Setting the thesis (you will be held to it)
- **Size**: default `"1.00"`. Never above `max_trade_usd`. Smaller when confidence is lower.
- **Stop**: 2-4% below entry (`stop_pct: "3"` is the default). It must sit within the policy's
  stop-distance bounds. Pick a level where the idea is wrong, not a level you hope won't be hit.
- **Take-profit**: at least 1.5x the stop distance (e.g. stop 3% -> `tp_pct: "4.5"` or more).
- **Horizon**: 60-240 minutes for this playbook. If the move hasn't happened by then, the idea
  is stale and the position is closed at market.
- **conf**: 2 agreeing signals -> 0.55; 3 -> 0.65; strong confluence -> at most 0.75. Never 1.0.
- **strat**: a short tag such as `trend_pullback`, `momentum`, `mean_revert`.
- **why**: `REASON_CODE: short text`, e.g. `TREND_UP: +2.1% 24h, bullish signals, risk-on macro`.
  It is published verbatim. No private reasoning, no chain-of-thought, <=140 characters.

## After calling oath_open_position
- `ok: true`: report the seq, entry fill (from the chain), stop, tp and horizon to the user, plus
  the commit and swap signatures. Say that the monitor will exit and reveal automatically.
- `blocked: true`: report the reason code. It is on-chain and counts in your record. **Do not**
  resubmit a tweaked thesis just to pass the firewall. Only resubmit if the facts changed.
- `refused`: something was malformed or a position needs operator recovery. Tell the user and stop.

## Never
- Never try to call swap, transfer, perps, DCA, limit-order, prediction or agent-chat tools, or
  shell/file/web workarounds. They are blocked, and trying is logged.
- Never claim a P&L that doesn't come from `oath_status` (which reads on-chain fills).
