# Phase 0 findings — ClawPump / Hermes probe

Date: 2026-09-27 · Host: Windows 11 (laptop) · Hermes: **ClawPump v0.20.6 (2026.8.27), upstream 7b81ee98**, Python 3.11.16
Stdio MCP package: `@clawpump/agents@0.1.27` · HERMES_HOME: `C:\Users\hp\.hermes`

Status legend: ✅ verified · ❌ contradicts spec (SPEC.md now corrected) · ⏳ pending

Evidence (all in `probe/`, dated 2026-09-27; PII such as account email/avatar is redacted by `_common.scrub`):
`clawpump_tools.json` (132 live schemas + annotations), `spec_tool_presence.json`, `read_calls.json`,
`hermes_hook_probe.json`, `hermes_live_check.json`, `ansem_mint.json`; `swap_test.json` after the swap.

Re-run:
```
uv run python probe/clawpump_tools.py                         # live read-only calls
uv run python probe/swap_test.py --dry-run                    # all pre-swap checks, no swap
~/.hermes/hermes-agent/venv/Scripts/python.exe probe/hermes_hook_probe.py   # hooks vs call_mcp (stub server)
~/.hermes/hermes-agent/venv/Scripts/python.exe probe/hermes_live_check.py   # real config: what the model sees
```

---

## Our ClawPump account (live)

| | |
|---|---|
| Agent | **OATH**, `agent_id = 2b9abb41-60e1-4b62-b1ec-ce772445003e`, status `stopped`, model `moonshotai/kimi-k2.5` |
| Agent wallet | **`9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY`** |
| Balances (pre-swap) | 2.000176 USDC · 0.005935253 SOL (≈ $2.72 total) |
| Hosted-agent skills | defi-trading, market-intel, portfolio, wallet-ops, token-launch, action-plans, web-browsing, private-transfers, bitget-intel, self-learning, skill-management (**no perps-trading**) |
| Transfer whitelist | empty |
| Auth | `api_key_direct` (cpk_ key from `~/.hermes/.env`) |

---

## Answers to every `VERIFY` in SPEC.md

| # | Spec § | Question | Status | Answer |
|---|---|---|---|---|
| 1 | 2.2 | Exact `pre_tool_call` signature | ✅ | `cb(tool_name: str, args: dict, task_id: str, **kwargs)`. Observed kwargs: `api_request_id, middleware_trace, session_id, telemetry_schema_version, tool_call_id, turn_id`. `{"action":"block","message":m}` → model gets `{"error": m}` (live). Also `approve`, `modify`. Timeout `plugins.hook_callback_timeout` = **30 s**; timeout/exception ⇒ fail closed. |
| 2 | 2.2 | MCP tool-name prefixes | ❌ | **`mcp__<server>__<tool>`**: `mcp__clawpump__swap_execute` (remote), `mcp__clawpump_stdio__swap_execute` (stdio). Live registry confirms. Match `name.rsplit("__",1)[-1]`. |
| 3 | 2.4 | Tool list / schemas | ✅ live | 132 tools. **Missing:** `agent_balance`, `fee_earnings`, `agent_send`. Transfer tool = `wallet_transfer`. 39 tools `destructiveHint`, 71 `readOnlyHint`, 22 neither (incl. fund movers `place_bid`, `set_external_wallet`, `add_to_whitelist`). |
| 4 | 2.4 | `swap_execute` schema | ✅ live | `{agent_id?, input_mint, output_mint, amount: str (int, smallest unit), slippage_bps?: 1..5000 (default 50)}`. No confirm flag. Returns backend JSON verbatim. |
| 5 | 2.4 | **Does `swap_execute` return tx signature + fill amounts?** | ✅ **signature yes; response amounts are NOT the fill** | Live swap 2026-09-27 15:11:44Z: response `data.txHash` = `2yVvHjqByEtJEk6Xh8GQcLJ4Um6KBTJosFaxtQMfS7nTnYLTXVEasmWfQ9McNJUsEuuLkq3XK6wPNqFrvYLEHDDu` (+ `explorerUrl`, `status: executed`, `venue: jupiter`, route `GoonFi V2`), latency 2.1 s. On-chain (slot 451033522): `err: null`, sole signer = agent wallet, agent USDC −1,000,000 raw, agent native SOL **+8,221,767 lamports net** (tx fee 5,002 paid by agent → gross 8,226,769 = the pool's SOL delta). Response `output.rawAmount` = 8,227,098 **does not match** the fill (+329 vs gross). It's the route's expected out, not the settlement. SOL output arrives **unwrapped** (native lamports, no wSOL left). ⇒ Link commit→trade by `txHash`; compute fills and P&L from on-chain balance deltas only (SPEC §5.1, user decision). |
| 6 | 2.4 | Launchpad MCP `clawpump.tech/api/mcp` | ❌ | **404**; not in llms.txt. |
| 7 | 5.2 | `ctx.call_mcp` passes through `pre_tool_call`? | ✅ **No** | Live test with stub server: hook saw only the plugin's own tool name. |
| 7b | 5.2 | `call_mcp` honours `tools.include`? | ✅ **No** | Excluded `swap_execute` still executed via `call_mcp`. |
| 8 | 5.3 | Server exit swaps hit the same wallet | ✅ | Same key + explicit `agent_id` ⇒ `get_agent` / `get_portfolio` return wallet `9jxu…32bY` from both the standalone Python client and Hermes. |
| 9 | 2.3 | Perps for our account | ✅ **No** | `perps_account` → *"Access denied: Phoenix perps requires the perps-trading skill to be enabled on this agent."* `perps_markets` (read) works. **v1 spot-only.** |
| 10 | 7 | $ANSEM mint | ✅ **user-confirmed** | **`9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump`**, 6 dp. ClawPump `token_search` (`well_known, verified: true`) = CoinGecko `the-black-bull` = on-chain mint. Owner **Token-2022** today; mint/freeze authority null. Look-alike "ANSEM" `SPqTn8…` also returned (never select by symbol). Token program is **detected at runtime** (SPEC §7). |
| 11 | 9 | Python x402 lib | deferred | Phase-4 gate. |

Other live read results: `swap_quote` 1 USDC → 0.008211757 SOL, `venue: jupiter`, route `TesseraV`, price impact ≈ 0, `platformFee: null`. `get_price` source birdeye (SOL ≈ $121.9). `get_wallet_history` gives `{signature, timestamp, status, memo}` only, with no amounts or mints.

---

## Model lockout (user instruction 3): layer 1 done, layer 2 specified

**Layer 1: config (✅ done, verified live).** Appended to `C:\Users\hp\.hermes\config.yaml` (backup: `config.yaml.bak-2026-09-27`):
- `mcp_servers.clawpump`: `enabled: false`, `tools.include: []`. claw-agent's overlay (`hermes_cli/distribution.py:123`) otherwise registers all ~134 remote tools, fund movers included, even before login.
- `mcp_servers.clawpump-stdio`: `npx -y @clawpump/agents@0.1.27`, key via `${CLAWPUMP_API_KEY}`, `CLAWPUMP_DEFAULT_AGENT` = OATH, and a **14-tool read-only allowlist**.
- `hermes_live_check.json`: model registry = exactly those 14 + 4 MCP helpers; **0 unexpected, 0 remote `mcp__clawpump__*`**; `get_portfolio` works through the model dispatch path. `pass: true`.

**Layer 2: hook (specified in SPEC §5.2, built in Phase 2).** Default-deny: any `mcp__clawpump*__*` whose suffix isn't on the read allowlist is blocked, with a fixture list of 33 known fund movers so regressions fail tests.

---

## Other findings

1. **Hosted-agent bypass.** OATH on ClawPump is itself an LLM agent with trading and wallet skills. `chat_with_agent`, `create_agent_run` and `trigger_automation` can make it trade server-side, outside PoT. They're excluded from the model; keep the agent `stopped`. Disclose that dashboard/hosted-agent trades aren't covered; the indexer flags agent-wallet swaps with no `pot1:o` memo.
2. **Broken catalog pin.** `@clawpump/agents@0.1.25` has no `dist/`; use 0.1.27. The installer's stdio setup hung because of it.
3. **`.env` inline comments aren't stripped by Hermes.** The key line had a trailing `# comment`, and Hermes (and my first loader) sent the comment as part of the key → "Invalid or deactivated API key". Fixed by moving the comment to its own line; key value untouched. Probe loader now handles dotenv inline comments.
4. **Windows/MSIX redirect.** Installs from inside Claude desktop to `%LOCALAPPDATA%` land in its package sandbox. Reinstalled to `C:\Users\hp\.hermes`. A stale `C:\Users\hp\AppData\Local\hermes\bin` user-PATH entry remains (harmless).
5. Names starting `clawpump` are special-cased by Hermes; stub/test servers use other names. `hermes plugins validate` → `hermes plugins doctor`. `mcp` SDK pinned `<2`.
6. PII: `get_account_status` returns the ClawPump account email, X handle and avatar. Probe outputs are scrubbed before saving.

## Swap test notes
- Record: `2026-09-27_swap_test.json`. Balances around the recorded run: USDC 1.000176 → 0.000176, SOL 0.014049888 → 0.022271655.
- **Unrecorded earlier swap:** `4RSqNho6WXUd…` at 15:10:42Z (slot 451033295), also 1 USDC → SOL via Jupiter, signed by the agent wallet, fee 105,000 lamports, net +8,114,635 lamports. It has no probe record (`probe/2026-09-27_swap_unrecorded_tx.json` holds its chain summary). Most likely a first run of `swap_test.py`, whose record was overwritten because `save()` used one filename per day and saved only at the end. **Fixed:** swap records never overwrite and are persisted right after `swap_execute`. Origin to be confirmed by the user.
- This is exactly the "agent-wallet swap without a commitment" case the OATH indexer must flag.

Phase 0 is complete: every VERIFY row is answered.
