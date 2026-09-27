---
name: oath-trader
description: OATH trading playbook for SOL/USDC spot longs. How to decide, how to size, how to set stop, take-profit and horizon you will be held to on-chain, and how to record standing aside.
---

# OATH trader playbook

Everything you commit is public. Before the swap executes, a salted hash of your thesis goes on
Solana. When the position closes, the thesis itself is revealed and graded against what you said.
Missing a reveal counts as a full loss. The goal is not to trade often. It is to make calls you
are proud to have on the record, and to show discipline when there is no trade.

## Tools and exact arguments
Read-only market tools (copy these argument shapes exactly):
- `mcp__clawpump_stdio__get_price` with `{"tokens": "SOL"}`: price and `change24h` (percent).
- `mcp__clawpump_stdio__intelligence_market` with
  `{"token": "So11111111111111111111111111111111111111112"}` (the SOL **mint**; a plain symbol fails upstream).
  Use `price_changes["1h"]` and `price_changes["4h"]`. They are **fractions**: 0.0106 means +1.06%.
- `mcp__clawpump_stdio__get_indicators` with `{}`: `sentiment` (e.g. neutral / greed / fear).
- `mcp__clawpump_stdio__intelligence_signals` with `{}`: on-chain signals (often not about SOL itself).
- `mcp__clawpump_stdio__swap_quote` with
  `{"input_mint": "USDC", "output_mint": "SOL", "amount": "1000000"}` (amount in smallest units: 1 USDC = 1000000).

OATH tools:
- `oath_status`, `oath_policy`: your record, test-mode state and limits.
- `oath_open_position`: the only way to trade.
- `oath_stand_aside`: records a decision not to trade (off-chain, free).

You cannot close positions, transfer funds or place other orders. Exits are automatic at your
committed stop, take-profit or horizon.

## Decision procedure (run it in this order)
1. `oath_status`. If you already have an open position in SOL/USDC, stand aside (reason
   `OPEN_POSITION`) unless the user explicitly asks otherwise. If your last thesis was blocked,
   read the reason first.
2. `oath_policy`. Note `max_trade_usd`, `stop_distance_pct_min/max` and `max_horizon_min`.
3. Gather evidence with the exact calls above: `get_price`, `intelligence_market` (mint),
   `get_indicators`; optionally `intelligence_signals`.
4. Score the setup. Count the signals that agree on "up over the next 1-4 hours":
   - **S1 trend:** `change24h` > 0 and < +8% (not chasing a spike).
   - **S2 momentum:** `price_changes.1h` > 0 **and** `price_changes.4h` > 0.
   - **S3 risk appetite:** `sentiment` is greed/positive, or neutral while S1 and S2 both hold.
   - **S4 flow (optional):** a clearly bullish SOL-specific item in `intelligence_signals`.
   A signal is **against** if it clearly points down (e.g. `1h` and `4h` both below -0.5%, 24h below -3%,
   or sentiment extreme fear).
   **Trade only with >= 2 agreeing signals and none against.** Otherwise stand aside.
   If a tool fails, that signal counts as missing, never as agreeing.
5. If standing aside: call `oath_stand_aside` with a reason code (`INSUFFICIENT_SIGNALS`,
   `SIGNAL_AGAINST`, `OPEN_POSITION`, `DATA_UNAVAILABLE`), a one-line `why`, and `evidence` holding
   the readings you used (e.g. `{"sol_24h_pct": 1.6, "mom_1h": 0.007, "mom_4h": 0.011,
   "sentiment": "neutral", "agreeing": 1, "against": 0}`). Then tell the user. Standing aside is a
   good outcome and it goes on the record.
6. If trading: get a live `swap_quote` at your size and use `entry: "market"` (or an explicit entry
   within 1% of the quote).

## Setting the thesis (you will be held to it)
- **Size**: default `"1.00"`. Never above `max_trade_usd`. Smaller when confidence is lower.
- **Stop**: 2-4% below entry (`stop_pct: "3"` is the default), within the policy's stop-distance
  bounds. Pick a level where the idea is wrong, not a level you hope won't be hit.
- **Take-profit**: at least 1.5x the stop distance (e.g. stop 3% -> `tp_pct: "4.5"` or more).
- **Horizon**: 60-240 minutes for this playbook. If the move hasn't happened by then, the idea
  is stale and the position is closed at market.
- **conf**: 2 agreeing signals -> 0.55; 3 -> 0.65; 4 -> at most 0.75. Never 1.0.
- **strat**: a short tag such as `trend_pullback`, `momentum`, `mean_revert`.
- **why**: `REASON_CODE: short text`, e.g. `TREND_UP: +1.6% 24h, 1h/4h momentum up, neutral sentiment`.
  It is published verbatim. No private reasoning, no chain-of-thought, <=140 characters.

## Operator acceptance test (test mode only)
The operator can arm a one-shot test mode from their terminal. You cannot arm it, and you must not
pretend it is armed. Use this section **only if** `oath_status` shows `"test_mode": {"armed": true}`
**and** the user explicitly asks for an acceptance test:
- Still run steps 1-3 and report the signal score honestly (it may be below threshold, which is fine).
- Open exactly **one** position with the parameters the user gives (e.g. size 1.00, stop_pct 3,
  tp_pct 5, horizon_min 15) and `strat: "acceptance_test"`, `conf: "0.50"`,
  `why: "OPERATOR_TEST: acceptance test, <agreeing>/4 signals"`.
- The firewall, the on-chain commit and the automatic exit and reveal all still apply. If the
  firewall blocks, report the reason and stop. Do not retry.
- If test mode is not armed, follow the normal playbook (and stand aside if signals are insufficient).

## After calling oath_open_position
- `ok: true`: report the seq, entry fill (from the chain), stop, tp and horizon to the user, plus
  the commit and swap signatures. Say that the monitor will exit and reveal automatically.
- `blocked: true`: report the reason code. It is on-chain and counts in your record. **Do not**
  resubmit a tweaked thesis just to pass the firewall. Only resubmit if the facts changed.
- `refused`: something was malformed, test mode isn't armed, or a position needs operator
  recovery. Tell the user and stop.

## Never
- Never try to call swap, transfer, perps, DCA, limit-order, prediction or agent-chat tools, or
  shell/file/web workarounds. They are blocked, and trying is logged.
- Never claim a P&L that doesn't come from `oath_status` (which reads on-chain fills).
