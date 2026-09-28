# OATH (Proof-of-Thesis) — Backend Spec

> Hand this file to Claude Code. It is the source of truth for the backend.
> Built for **The AnsemHack Clawrena** — track: **ClawPump × pump.fun** (+ automatic Overall Winner).
> Hard deadline: token live + registered by **1 Oct 2026, 24:00 EST (UTC−5)** = 2 Oct 06:00 Lagos.
>
> **Changelog**
> - 2026-09-27: Phase 0 corrections applied (evidence in `probe/FINDINGS.md`): tool-name format `mcp__<server>__<tool>`; `call_mcp` bypasses hooks and `tools.include`; claw-agent pre-wires all ClawPump tools, now handled by a two-layer model lockout (config allowlist + default-deny hook, §5.2); launchpad MCP gone, server uses stdio with the same key + `agent_id`; `agent_balance`/`fee_earnings`/`agent_send` don't exist; pin `@clawpump/agents@0.1.27`; perps denied (spot-only confirmed); $ANSEM mint confirmed, token program detected at runtime (§7); hook signature verified; Windows install notes; `mcp<2`; hosted-agent bypass disclosed.
> - 2026-09-28 (Phase 2 exit criterion MET): Hermes agent (nvidia/nemotron-3-ultra-550b-a55b:free via OpenRouter, locked to `-t oath,mcp-clawpump-stdio`) opened seq 2 itself through `oath_open_position` (operator test mode, `acceptance_test`, 3/4 signals); commit slot 451088313 < swap 451088333; monitor exited at expiry (held 945 s vs 900 s) and revealed; `python -m oath_core.verify` PASS (2/2 revealed, digest_ok, completeness 1, 0 adherence violations, 0 uncommitted trades). Direct swap_execute blocked (probe/2026-09-27_phase2_hermes_check.json). Added: stand-aside records (`oath_stand_aside`, off-chain `decisions` table), operator test mode, intelligence_market mint repair, labelled amounts in model-facing results (`oath_core/present.py`) after the model misreported lamports as SOL.
> - 2026-09-27 (Phase 2): firewall + policy.json (§6), `oath_core/guard.py` default-deny hook + sensitive-argument heuristic, Hermes plugin `plugin/oath` (junctioned into `~/.hermes/plugins/oath`; `oath_core` installed editable into Hermes's venv with `--no-deps`, because **Hermes ships `mcp` 2.0.0** and our stdio client pins `mcp<2`, now imported lazily), rules via `register_system_prompt_section`, playbook skill `oath:oath-trader` (plugin skills aren't indexed; preload with `-s`), `oath_server/monitor.py` (stop/tp/expiry exits, pending-reveal retry, deadline sweeper → `oath1:s`), verify adds adherence (exit honoured stop/tp/horizon) + late-reveal checks. Trading agent runs locked down: `hermes chat -t oath,mcp-clawpump-stdio -s oath:oath-trader`.
> - 2026-09-27: Swap test passed (`swap_execute` returns `data.txHash`). Fills and P&L are on-chain balance deltas only (§5.6). Renamed PoT → **OATH** everywhere: `oath_core`, `oath` plugin, `hermes oath` CLI, `oath1:` memo prefix, `oath_open_position`, `~/.oath/`, `oath-server`.

---

## 0. Instructions for Claude Code (read first)

1. **Probe before you build.** Several ClawPump behaviours below are *assumptions* (marked `VERIFY`). Phase 0 exists to confirm them against the live MCP with a real API key. Save every probe result to `probe/` as dated JSON/markdown. If a probe contradicts this spec, stop and tell the user; do not silently work around it.
2. **Never fake data.** Every number the API returns must come from the ledger or the chain. No mock P&L, no placeholder trades in production paths. Fixtures only inside `tests/`.
3. **Fail closed.** If a price, balance, signature or policy cannot be read or verified, refuse the trade.
4. **Secrets:** keypairs and API keys live in `~/.oath/` or `.env`, never in the repo. Add them to `.gitignore` on day one.
5. **Mainnet, tiny size.** Real money, but cap every trade at a few dollars until the user raises limits.
6. Python 3.11, `uv` for env management, `pytest` for tests. Keep dependencies minimal.

---

## 1. What we are building (one paragraph)

A Hermes plugin plus a small server that make an autonomous trading agent **provably honest**. Before any trade, the agent must write a structured thesis (asset, direction, entry, stop, take-profit, size, confidence, horizon). The thesis is salted, hashed, and the hash is **committed on Solana (memo)**, optionally with a **$ANSEM bond**. Only then can the trade execute. When the position closes, the thesis and salt are **revealed on-chain**, anyone can recompute the hash, and the result is graded against what the agent said it would do. Every commitment has a sequence number; **an unrevealed commitment counts as a loss and forfeits its bond**, so the agent can't hide bad calls.

The one-line pitch: *"Redline-style firewalls limit what an agent can do. Proof-of-Thesis proves what it meant to do, before the market moved."*

---

## 2. Context the builder must know (researched)

### 2.1 The "Hermes DeFi harness"
- It is **ClawPump's own distribution of Nous Research's Hermes Agent**: repo `github.com/Clawpump/claw-agent`. It is upstream Hermes plus the ClawPump MCP wired in natively (132 tools in `@clawpump/agents@0.1.27`). *Verified: ClawPump v0.20.6 (2026.8.27), upstream 7b81ee98, Python 3.11.16.*
- Setup: install via `curl -fsSL https://raw.githubusercontent.com/Clawpump/claw-agent/main/scripts/install.sh | bash` (Linux/macOS) or `scripts/install.ps1` (Windows), then `hermes clawpump setup` (choose stdio with a `cpk_` API key, or remote OAuth at `https://mcp.clawpump.tech/mcp`).
  - **Windows:** install with `-HermesHome C:\Users\<you>\.hermes`. Anything run from an MSIX-packaged app (e.g. Claude desktop) that writes to `%LOCALAPPDATA%` is redirected into that app's package sandbox and is invisible to a normal terminal.
  - `hermes clawpump setup` is interactive-only (non-TTY silently picks remote OAuth). We configure `mcp_servers` directly instead (see §5.2 config).
  - `.env` values: Hermes does **not** strip inline `# comments` on a value line. Keep `CLAWPUMP_API_KEY=cpk_…` alone on its line.
- Our deliverable is a **Hermes plugin**, which is literally "net-new tooling on the Hermes harness", the track's scoring language.

### 2.2 Hermes plugin API (from hermes-agent docs)
- Location: `~/.hermes/plugins/<name>/` with `plugin.yaml` + `__init__.py` exposing `register(ctx)`.
- `ctx.register_tool(name=..., toolset=..., schema=..., handler=...)`; handler signature `handler(params, **kwargs) -> str (JSON)`.
- `ctx.register_hook("pre_tool_call", cb)` — *verified live:* `cb(tool_name: str, args: dict, task_id: str, **kwargs)`; kwargs currently include `api_request_id, middleware_trace, session_id, telemetry_schema_version, tool_call_id, turn_id` (always accept `**kwargs`). Returning `{"action": "block", "message": "..."}` blocks the call and the model receives `{"error": "<message>"}`. Other directives: `approve` (escalate to human), `modify` (merge args). A valid `block` from any plugin wins. Callbacks that time out (`plugins.hook_callback_timeout`, default **30 s**) or raise **fail closed**.
- `ctx.call_mcp(server, tool, arguments, timeout=30)` → `{"ok": bool, "result"|"error": ...}`. Requires `plugins.entries.<plugin>.mcp_allowlist: ["clawpump-stdio"]` in `~/.hermes/config.yaml` (default-deny, per server). *Verified live:*
  - `call_mcp` does **not** pass through `pre_tool_call` (it calls `tools.mcp_tool._make_tool_handler` directly; hooks only fire in `model_tools.handle_function_call`, i.e. for the model's calls).
  - `call_mcp` does **not** honour `mcp_servers.<s>.tools.include`: a tool hidden from the model is still callable by an allowlisted plugin. This is how OATH executes swaps while the model cannot see `swap_execute` at all.
  - Consequence to disclose: any *other* plugin with `clawpump-stdio` in its `mcp_allowlist` can also trade. OATH's guarantee is against the model, not against other installed plugins.
- `ctx.register_skill(name, path)` to ship a SKILL.md; `ctx.register_cli_command(...)` for `hermes oath <sub>`; `ctx.register_command(...)` for `/oath` slash commands.
- `plugin.yaml` supports `requires_env: [...]`. Plugins are opt-in: `hermes plugins enable oath`. Validate with **`hermes plugins doctor`** (`hermes plugins validate` does not exist in this build).
- **Tool names (verified):** Hermes registers MCP tools as **`mcp__<server>__<tool>`** (double underscore; any char outside `[A-Za-z0-9_]` in the server name becomes `_`). Remote server `clawpump` → `mcp__clawpump__swap_execute`; stdio server `clawpump-stdio` → `mcp__clawpump_stdio__swap_execute`. Match on the suffix: `tool_name.rsplit("__", 1)[-1]`. Hermes also adds `list_resources, read_resource, list_prompts, get_prompt` per server.
- Hermes special-cases every server name starting with `clawpump` (key injection for stdio, remote-URL overlay for `clawpump`). Test/stub servers must use other names.

### 2.3 Competitor: Redline (`github.com/Yonkoo11/redline`)
Already entered in this hackathon. It is a Hermes `pre_tool_call` firewall: signed operator policy (trade cap, daily loss, drawdown halt, leverage, allowlists), refusals posted as Solana memos. **Do not rebuild Redline.** Our firewall is deliberately small; our novelty is commit-reveal, sequence completeness, thesis grading and bonds. OATH must be able to run *alongside* Redline (both register `pre_tool_call`; nothing we do should conflict).

Facts Redline measured, re-verified in Phase 0 (2026-09-27):
- ClawPump spot swaps route via Jupiter (and OKX). *Verified:* `swap_quote` USDC→SOL returned `venue: "jupiter"`. Mainnet fill: see §2.4.
- **Perps are not available to our agent.** *Verified:* `perps_account` → "Access denied: Phoenix perps requires the perps-trading skill to be enabled on this agent." (A `perps_trader_register` tool now exists.) → **v1 is spot-only.** Shorts are out of scope.
- Hosted ClawPump agents cannot load plugins; the plugin runs on a self-hosted Hermes (VPS or laptop).
- **Hosted-agent bypass (new):** our ClawPump agent (OATH) is itself an LLM agent with `defi-trading` and `wallet-ops` skills. `chat_with_agent`, `create_agent_run`, `trigger_automation`/`create_automation` can make it trade **server-side**, outside Hermes and outside OATH. These tools are off for the model (§5.2). Keep the hosted agent `stopped` and disclose in the README that OATH covers trades initiated through Hermes, not ones made via the ClawPump dashboard.

### 2.4 ClawPump tools we rely on (verified against `@clawpump/agents@0.1.27`, live)
`swap_quote`, `swap_execute`, `get_price`, `get_portfolio`, `token_search`, `intelligence_market` (requires `token`), `intelligence_signals`, `get_market_signals`, `get_wallet_history`, `list_agents`, `get_agent`.
- **Do not exist:** `agent_balance` (use `get_portfolio`), `fee_earnings`, `agent_send` (the transfer tool is `wallet_transfer`).
- **Launchpad MCP (`https://clawpump.tech/api/mcp`) is gone (404)**, not listed in clawpump.tech/llms.txt. oath-server uses the **same stdio package with the same `cpk_` key and explicit `agent_id`** (or the REST API with that key), so exits act on the same agent wallet.
- Agent MCP (`npx -y @clawpump/agents@0.1.27`, `CLAWPUMP_API_KEY`) is the one Hermes uses. **Pin 0.1.27**: 0.1.25 (claw-agent's catalog pin) was published without `dist/` and cannot start.
- Our agent: **OATH**, `agent_id = 2b9abb41-60e1-4b62-b1ec-ce772445003e`, wallet **`9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY`**. Always pass `agent_id` explicitly; verify the wallet via `get_agent` before any trade (fail closed on mismatch).
- `swap_execute` args: `{agent_id?, input_mint (mint or symbol), output_mint, amount: str (positive integer, smallest unit), slippage_bps?: 1..5000 (default 50)}`. `destructiveHint: true`, no confirm flag. The MCP returns the backend `POST /swap/execute` JSON verbatim. Refuses if both `CLAWPUMP_TOKEN` and `CLAWPUMP_API_KEY` are set.
- `swap_quote` returns `{venue, input{rawAmount,decimals}, output{rawAmount,decimals}, priceImpactPct, otherAmountThreshold, route, platformFee}`.
- `get_wallet_history` returns only `{signature, timestamp, status, memo}`, with **no mints or amounts**. The fallback match must read each tx from Solana RPC.
- **Critical VERIFY (pending the $1 swap):** does `swap_execute` return the on-chain **transaction signature** and the filled in/out amounts? OATH needs the signature to link commit → trade. If it doesn't, fall back to `get_wallet_history` + Solana RPC for the agent wallet right after execution, matching by mint + amount + time.

---

## 3. Architecture

```
┌───────────────────────── self-hosted box (VPS) ──────────────────────────┐
│                                                                          │
│  Hermes (claw-agent)                                                     │
│   ├─ LLM decides → calls tool  oath_open_position(thesis)                │
│   ├─ config: model sees ONLY read-only ClawPump tools (allowlist)        │
│   ├─ pre_tool_call hook: BLOCK every other mcp__clawpump*__* call        │
│   │   (default-deny; see §5.2)                                           │
│   └─ oath plugin ──► oath_core (python package)                          │
│                                                                          │
│  oath_core                                                               │
│   ├─ thesis.py      schema, canonical encoding, salt, hash               │
│   ├─ firewall.py    small rule set → APPROVE | BLOCK(reason)             │
│   ├─ notary.py      builds/sends memo txs (+ $ANSEM bond transfer)       │
│   ├─ executor.py    ClawPump swap via MCP, returns fill + tx sig         │
│   ├─ ledger.py      SQLite, append-only events                           │
│   └─ grader.py      P&L, adherence, stats                                │
│                                                                          │
│  oath-server (FastAPI, separate process)                                 │
│   ├─ monitor loop   stop / TP / expiry exits → close → reveal            │
│   ├─ indexer        re-reads memos from chain, independent verification  │
│   ├─ public API     /v1/... for the frontend + judges                    │
│   └─ (phase 4) x402 Firewall-as-a-service endpoint                       │
└──────────────────────────────────────────────────────────────────────────┘
        │ memos, bonds                     │ swaps
        ▼                                  ▼
   Solana mainnet (Memo program, SPL)   ClawPump MCP → Jupiter
```

**Why exits live in the server, not the LLM:** stops and take-profits must fire even if the model is idle or wrong. The LLM opens positions; deterministic code closes them.

**Source of truth:** the chain. The ledger is a cache; the indexer must be able to rebuild the full record from memos + swap txs alone.

### Wallets
| Key | Holds | Purpose |
|---|---|---|
| Agent wallet | USDC, SOL, traded tokens | ClawPump-managed; executes swaps via MCP. We never hold its key. |
| Notary keypair (`~/.oath/notary.json`) | small SOL for fees, $ANSEM for bonds | Signs every OATH memo; its pubkey is the public identity of the record. |
| Bond escrow keypair (`~/.oath/escrow.json`) | $ANSEM in escrow | Receives bonds at commit; releases or slashes. (Custodial by the server — disclose this; roadmap = on-chain program.) |

---

## 4. Data model

### 4.1 Thesis (what the agent commits to)
Short keys keep memos small. Canonical encoding = JSON with **sorted keys, no whitespace, UTF-8, numbers as strings with fixed decimals** (avoid float drift).

```json
{
  "v": "1",
  "agent": "<agent wallet pubkey>",
  "seq": "42",
  "ts": "2026-09-28T14:03:11Z",
  "mkt": "SOL/USDC",
  "side": "long",
  "in_mint": "<USDC mint>",
  "out_mint": "<SOL mint>",
  "size_usd": "5.00",
  "entry": "214.20",
  "stop": "208.50",
  "tp": "225.00",
  "horizon_min": "240",
  "conf": "0.78",
  "strat": "momentum",
  "why": "<=140 chars, structured reason code + short text"
}
```
Validation rules:
- `side` ∈ {`long`} in v1 (spot). `stop < entry < tp` for long.
- `size_usd` ≤ policy cap. `horizon_min` ≤ policy max (default 360) so trades resolve before judging.
- `why` is a short, structured justification — **never raw chain-of-thought.**
- `seq` = last seq + 1 for this agent (strictly contiguous, starts at 1).

### 4.2 Commitment
```
salt   = 32 random bytes (secrets.token_bytes)
digest = sha256( canonical_json(thesis) || salt )      # hex
```
Salt is mandatory: the thesis space is small enough to brute-force otherwise.

### 4.3 Memo formats (Solana Memo program, prefix `oath1`)
| Event | Memo | Notes |
|---|---|---|
| Commit | `oath1:c:<agent>:<seq>:<digest>:<bond_amt>` | Same tx may include the $ANSEM bond transfer notary → escrow (atomic). |
| Blocked | `oath1:b:<agent>:<seq>:<digest>:<reason_code>` | Firewall refused. Thesis + salt revealed immediately via API; still counts in the sequence. |
| Open | `oath1:o:<agent>:<seq>:<swap_sig>` | Links the entry swap tx. Must land in a later slot than the commit. |
| Reveal | `oath1:r:<agent>:<seq>:<salt_hex>:<exit_sig>:<exit_reason>` | Posted at close. Full canonical thesis is published at `/v1/theses/<seq>` and must hash-match. If it fits (<~600 bytes total), also put the canonical thesis JSON in a second memo instruction in the same tx so verification needs zero trust in our API. |
| Slash | `oath1:s:<agent>:<seq>:<reason>` | Reveal missed deadline or stop breached. Bond burned or sent to treasury. |

`exit_reason` ∈ {`tp`, `stop`, `expiry`, `manual`} (+ `exec_failed` with `exit_sig=none`, §5.1).

**Memo tx cost (measured on mainnet, 2026-09-27).** The Memo program's compute cost grows with memo length: a commit (~140 B) uses 58,112 CU, and a reveal + thesis tx (897 B) uses 265,329 CU, so a fixed 200k CU limit fails. Every memo tx is **simulated first** (free); the CU limit is set to measured use × 1.2 (+2,000, max 1.4M), and the CU price is scaled so the priority fee stays ≤ 1,000 lamports. Every memo tx therefore costs ≤ 6,000 lamports (5,000 base + ≤ 1,000 priority), and a failed simulation sends nothing. Notary funding needed = rent-exempt minimum (live `getMinimumBalanceForRentExemption(0)`, 650,240 today) + 6,000 × memo txs still owed. Phase 1 round trip = 3 txs.
Reveal deadline = open time + `horizon_min` + grace (default 30 min). Missing it ⇒ `unrevealed`, counted as **full loss of size** in stats, bond slashed.

### 4.4 SQLite tables (ledger, append-only events + derived views)
- `events(id, seq, kind, payload_json, tx_sig, slot, created_at)` — kind ∈ commit/blocked/open/close/reveal/slash/bond_release.
- `positions(seq PK, status, thesis_json, salt_hex, digest, commit_sig, open_sig, exit_sig, reveal_sig, entry_px_fill, exit_px_fill, qty, fees_usd, pnl_usd, bond_amt, bond_status, opened_at, closed_at)` — status ∈ blocked/committed/open/closed/revealed/unrevealed/slashed.
- `equity_snapshots(ts, equity_usd, source)` — for drawdown.
- `fee_allocations(ts, bucket, amount, tx_sig)` — phase 3.
Store `salt_hex` encrypted-at-rest or at least file-permission 600; it must stay secret until reveal.

---

## 5. Flows

### 5.1 Open (called by the LLM through the plugin tool)
```
oath_open_position(thesis_fields)
  1. validate schema, assign seq, fill ts/agent
  2. price check: get_price / swap_quote; reject if |quote - entry| > max_entry_slippage (default 1%)
  3. firewall.evaluate(thesis, state)
        BLOCK → notary.post(blocked memo) → store → return {blocked, reason}
  4. salt, digest
  5. notary.commit(digest, bond) → wait for confirmation, record slot S1
  6. issue one-time exec token (in-memory, bound to seq, TTL 60s)
  7. executor.swap(in_mint → out_mint, size) via ctx.call_mcp("clawpump-stdio","swap_execute", {agent_id, …})
        (exec token checked in-process by the executor; call_mcp bypasses the hook, see §2.2)
        tx sig = response `data.txHash`; then read the tx from Solana RPC: require err == null,
        signer == agent wallet, slot S2 > S1 (else mark invalid, alert); fill = on-chain balance deltas (§5.6)
  8. notary.post(open memo with swap_sig)
  9. store position(status=open) → return {seq, digest, commit_sig, swap_sig}
```
If step 7 fails after commit: position → `committed`, **no automatic retry** (an errored `swap_execute` can still have landed on-chain, and a retry could double-buy). `oath recover --seq N` scans the agent wallet for any swap after the commit slot. If there is none, it reveals immediately with `exit_reason=exec_failed`, `exit_sig=none` (no bond slash: honest failure is recorded, not hidden). If there is one, it stops for manual linking. A seq stuck in `prepared` (commit memo never landed) is resolved the same way: recover finds or re-posts the commit, then reveals `exec_failed`, so the on-chain sequence never has a gap. `open` refuses while any position is `prepared`/`committed`.

### 5.2 Enforcement hook (the core "no trade without a commitment" guarantee)
Goal: the **only** way the model can trade is the plugin's open-position tool. Two independent layers; either one alone must be sufficient.

**Layer 1: config (model never sees fund movers).** claw-agent's distribution overlay (`hermes_cli/distribution.py`) pre-wires the remote `clawpump` server with **all** tools, including `swap_execute`, `wallet_transfer`, perps and token launch, even before login. `~/.hermes/config.yaml` must contain:
```yaml
mcp_servers:
  clawpump:            # pre-wired remote, disabled
    enabled: false
    tools: {include: []}          # include: [] = register nothing (belt and braces)
  clawpump-stdio:
    command: npx
    args: ["-y", "@clawpump/agents@0.1.27"]
    env: {CLAWPUMP_API_KEY: "${CLAWPUMP_API_KEY}", CLAWPUMP_DEFAULT_AGENT: "<agent_id>"}
    tools:
      include: [get_price, swap_quote, token_search, get_portfolio, get_wallet_history,
                get_market_signals, get_indicators, get_news_feed, intelligence_capabilities,
                intelligence_market, intelligence_signals, intelligence_macro, list_agents, get_agent]
plugins:
  entries:
    oath: {mcp_allowlist: ["clawpump-stdio"]}
```
This is an **allowlist**: a tool not listed is unavailable. Tool annotations can't be trusted as a denylist (`place_bid`, `set_external_wallet`, `add_to_whitelist` are not marked `destructiveHint` but move funds or redirect withdrawals). *Verified live (probe/…_hermes_live_check.json):* exactly these 14 tools plus 4 MCP helpers are registered; zero remote `mcp__clawpump__*` tools.

**Layer 2: `pre_tool_call` hook (default-deny for ClawPump).** `cb(tool_name, args, task_id, **kwargs)`:
- If `tool_name` starts with `mcp__clawpump` (any ClawPump server, any prefix variant) and its suffix `tool_name.rsplit("__",1)[-1]` is **not** in the read allowlist above (or the 4 MCP helpers) → `{"action":"block","message":"OATH: trades must go through oath_open_position (commit first)."}`.
- Default-deny means new ClawPump tools are blocked until reviewed. The known fund movers it covers today (39 `destructiveHint` tools + non-annotated fund movers), kept as a test fixture so a config regression fails CI: `swap_execute, perps_order_execute, perps_collateral_deposit, perps_collateral_withdraw, perps_order_cancel, perps_trader_register, perps_account_prepare, dca_create, dca_cancel, limit_order_create, limit_order_cancel, predictions_open, predictions_close, wallet_transfer, set_external_wallet, add_to_whitelist, remove_from_whitelist, place_bid, accept_marketplace_bid, withdraw_marketplace_bid, x402_pay, pay_sh_execute_approved, usepod_deposit, usepod_provision, agent_card_create, agent_card_withdraw, launch_token_gasless, launch_metaplex_genesis_token, chat_with_agent, create_agent_run, trigger_automation, create_automation, update_agent`.
- Everything that is not a ClawPump tool passes untouched (coexists with Redline).
- *Verified:* `ctx.call_mcp` does **not** pass through `pre_tool_call`, so the hook only sees the model's direct calls and the executor needs no hook whitelist. The one-time exec token is still issued and checked **inside the executor**, so no code path can call `swap_execute` without a committed seq.

### 5.3 Close + reveal (oath-server monitor loop, every 15–30 s)
For each open position:
- read price (Jupiter price via ClawPump `get_price`, fallback Jupiter price API v3).
- `price <= stop` → exit `stop`; `price >= tp` → exit `tp`; `now >= opened_at + horizon` → exit `expiry`.
- exit = swap full qty back to USDC via ClawPump `swap_execute`. The server spawns its own `npx -y @clawpump/agents@0.1.27` stdio client (Python `mcp<2` client) with the same `cpk_` key and passes `agent_id` explicitly. It verifies `get_agent(agent_id).wallet == configured agent wallet` at startup and before every exit (fail closed). The launchpad MCP no longer exists.
- compute realised P&L from **on-chain balance deltas** of the entry and exit txs (§5.6): USDC received on exit − USDC spent on entry − network fees (lamports × SOL price at exit).
- `notary.reveal(seq, salt, exit_sig, exit_reason)` → release bond (escrow → notary) → status `revealed`.
Deadline sweeper: any position past reveal deadline → `unrevealed` + slash memo + bond slashed.

### 5.4 Grading (grader.py)
Per trade: realised P&L, R-multiple (pnl / (entry−stop)·qty), exit reason, **adherence**: did the exit honour the committed stop/TP (slippage tolerance), was size ≤ committed size, did open land after commit.
Aggregate: trades, blocked count by reason, volume (entry + exit notional), realised P&L, win rate, max drawdown (from equity snapshots), **completeness = revealed / (committed − open)** (target 100%), bonds posted / slashed.

### 5.5 Independent verification (indexer + `oath verify`)
Given only the notary pubkey and an RPC endpoint (Helius — free credits for registered teams):
1. fetch all memo txs signed by notary, parse `oath1:*`.
2. check seq contiguity; list gaps.
3. for each reveal: recompute sha256(canonical_thesis || salt) == committed digest.
4. check commit slot < open swap slot; swap tx signer = agent wallet; mints/size match thesis within tolerance.
5. output a verification report. Ship this as `hermes oath verify` **and** a standalone `python -m oath_core.verify --notary <pubkey>` so judges can run it with no account.

### 5.6 Fills are on-chain balance deltas (source of truth)
ClawPump's `swap_execute` response is **not** a fill: its `output.rawAmount` is the route's expected out (Phase 0: response 8,227,098 lamports vs actual gross 8,226,769). Fills and P&L come **only** from the confirmed transaction (`getTransaction`, `jsonParsed`, commitment `confirmed`):
- Token legs: `postTokenBalances − preTokenBalances` for entries whose `owner == agent wallet` and `mint == leg mint`.
- SOL legs: ClawPump delivers/takes **native** SOL (wSOL is wrapped and unwrapped inside the tx). SOL delta = native lamport delta of the agent wallet (`postBalances − preBalances` at its account index) **+ any residual wSOL token delta**. If the agent is fee payer, `gross = native_delta + fee` and the fee is recorded separately.
- Record per swap: `in_raw`, `out_raw` (gross), `fee_lamports`, `slot`, `block_time`. Refuse (fail closed) if the tx is missing, `err != null`, the agent is not a signer, or either leg delta has the wrong sign.
- The exit sells exactly the entry's gross `out_raw` (the position's quantity), never "whole balance".
- The ClawPump response is stored for reference only; if it disagrees with the chain, the chain wins.

---

## 6. Firewall (deliberately small — Redline territory)
Rules, fail closed, config at `~/.oath/policy.json`:
- `max_trade_usd` (**configurable**; default 2.00 while sizes are tiny: `python -m oath_core policy --set max_trade_usd=3.00`), `max_open_positions` (default 2), `allowed_markets` (SOL/USDC), `allowed_mints` (USDC, SOL; JUP / $ANSEM later), `max_daily_loss_pct` (5), `max_drawdown_pct` (15 → halt), `max_entry_slippage_pct` (1), `min_liquidity_usd` (1,000,000) for the out-mint, `stop_distance_pct_min/max` (1–10%) so theses can't declare meaningless stops, `max_horizon_min` (360), `reveal_grace_min` (30), `swap_slippage_bps` (100), `max_blocked_per_hour` (5).
- Reason codes (in the `blocked` memo): `market_not_allowed, mint_not_allowed, size_cap, horizon_cap, max_open, stop_too_tight, stop_too_wide, price_unavailable, entry_slippage, price_outside_range, liquidity_unavailable, low_liquidity, equity_unavailable, drawdown_halt, daily_loss, insufficient_equity`. Missing data blocks (fail closed).
- *Implemented (Phase 2):* `oath_core/policy.py` + `oath_core/firewall.py` (pure). Inputs: live quote; out-mint liquidity from ClawPump `get_price` (its CoinGecko path, seen live, has **no liquidity**, which is then filled from Jupiter Price API v3); equity = on-chain USDC + SOL × price, snapshotted to `equity_snapshots` (peak → drawdown, first-of-day → daily loss).
- Malformed requests (bad schema, unsupported market, no quote for a `market` entry) are refused **without** a seq or memo. Policy blocks consume a seq and post `oath1:b` (thesis + salt returned to the caller; public via API in Phase 3). Blocked memos are rate-limited (`max_blocked_per_hour`) so a looping model can't drain the notary; beyond the limit the refusal is not recorded on-chain.

---

## 7. $ANSEM thesis bond
- Config: `bond_ansem_per_trade` (e.g. small fixed amount), `slash_mode` ∈ {`burn`, `treasury`}.
- Commit tx: memo + token transfer notary → escrow (atomic), using `transferChecked` (decimals from the mint).
- Timely valid reveal → escrow returns bond to notary.
- Missed reveal or stop breach beyond tolerance → slash.
- The bond punishes **breaking its word**, not losing money. Say this in docs.
- **$ANSEM mint (user-confirmed 2026-09-27): `9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump`**, 6 decimals. Matches ClawPump `token_search("ANSEM")` (`source: well_known, verified: true`) and CoinGecko `the-black-bull`; mint and freeze authority are `null`. Store in config, not code. `token_search` also returns look-alikes named "ANSEM" (e.g. `SPqTn8…`); never pick by symbol.
- **Token program: detect at runtime, never hardcode.** Read the mint account's `owner` via `getAccountInfo` and use it for the transfer instruction and ATA derivation. Accept only SPL Token (`TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA`) or Token-2022 (`TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb`); anything else ⇒ refuse (fail closed). Today the owner is **Token-2022**. If it is Token-2022, also read mint extensions (e.g. transfer fee / transfer hook) and refuse bonding if any extension would make the escrowed amount differ from the committed amount.

---

## 8. Public API (oath-server, read-only, CORS open)
```
GET /v1/health
GET /v1/agent                 → agent pubkey, notary pubkey, policy (public fields), token mint
GET /v1/stats                 → aggregates from §5.4
GET /v1/positions?status=&limit=&offset=
GET /v1/positions/{seq}       → full record, tx links; thesis+salt only if revealed/blocked
GET /v1/theses/{seq}          → canonical thesis JSON (post-reveal only) + digest + verify result
GET /v1/verify                → latest independent verification report
GET /v1/feed                  → recent events (for the live "trade #127" stream demo)
GET /v1/fees                  → phase 3: creator fees earned + allocation buckets
```
Never expose salts for open positions. Rate-limit lightly.

---

## 9. Phase 4 (stretch): Firewall-as-a-service over x402
Hosted ClawPump agents can't load plugins (Redline's own caveat) — but they can pay x402 services. Expose `POST /v1/check` taking a proposed trade + agent wallet, returning `approve|block` + reasons + a notary-signed verdict. Priced per call in USDC via x402. **VERIFY** a Python x402 server library with Solana support before starting; if none is quick to integrate, skip this phase and mention it on the roadmap.

---

## 10. Repo layout
```
OATH/
  plugin/oath/                  # the Hermes plugin (junction: ~/.hermes/plugins/oath -> here)
    plugin.yaml
    __init__.py                 # register(ctx): hook first, tools, prompt rules, skill, cli, /oath
    skills/oath-trader/SKILL.md # strategy playbook + "always use oath_open_position" rules
  oath_core/
    config.py policy.py thesis.py memo.py firewall.py guard.py notary.py executor.py fills.py
    market.py ledger.py grader.py verify.py flow.py clawpump.py solana_rpc.py keys.py __main__.py
    (bond.py: Phase 3)
  oath_server/
    monitor.py                  # (app.py, indexer.py: Phase 3)
  probe/                        # dated probe outputs + FINDINGS.md
  scripts/                      # operator one-offs (never model-facing)
  tests/                        # unit + integration (fixtures only here)
  pyproject.toml  .env.example  .gitignore  SPEC.md
```
Plugin tools to register: `oath_open_position`, `oath_status` (open positions + stats), `oath_policy` (read-only view). CLI: `hermes oath {init,verify,status,policy}`.

Dependencies (keep lean): `solders`, `solana` (solana-py) or raw JSON-RPC via `httpx`, `fastapi`, `uvicorn`, `pydantic`, `mcp>=1.9,<2` (Python MCP client for the server; 2.x renamed FastMCP and changed the client API), `pytest`.

---

## 11. Build plan (≈5 days)

**Phase 0 — Probe + ship the token (today/tomorrow, blocks everything)**
- User (non-code): register on clawpump.tech/ansemhack, post the X announcement, follow @clawpumptech, create the ClawPump agent + API key, **launch the token now** (early deploy is scored).
- Code: install claw-agent; `hermes clawpump setup`; write `probe/clawpump_tools.py` that lists tools and schemas and saves them; call `get_portfolio`, `swap_quote`, `get_price`; do ONE $1 USDC→SOL `swap_execute` and record exactly what it returns (sig? fill?). Check the MCP tool prefixes inside Hermes. Check `ctx.call_mcp` vs `pre_tool_call` interaction. Check perps availability.
- Exit criterion: `probe/FINDINGS.md` answering every `VERIFY` in this spec.

**Phase 1 — oath_core, manual mainnet round trip**
- thesis/canonical/hash with tests (incl. golden vectors); notary memo sending; ledger; executor; grader; verify.
- CLI script does commit → swap → open memo → (manual) close → reveal on mainnet with $1–2.
- Exit: `python -m oath_core.verify` passes on that real trade.

**Phase 2 — Hermes plugin + monitor**
- plugin tools, enforcement hook, SKILL.md, firewall; oath-server monitor (stop/TP/expiry) + deadline sweeper.
- Exit: Hermes agent opens a trade by itself, direct `swap_execute` is blocked, monitor closes and reveals automatically.

**Phase 3 — API, bond, fees**
- public API; $ANSEM bond + slash; fee allocation tracking.
- Exit: `/v1/stats`, `/v1/feed`, `/v1/verify` serve real data; one bonded trade revealed and bond released on-chain.

**Phase 4 — stretch + hardening**
- x402 firewall service (if lib exists), adversarial tests (seq gaps, replayed exec tokens, NaN sizes, stop ≥ entry, price feed down), run agent live continuously until judging.

---

## 12. Tests that must exist
- canonical encoding is deterministic (key order, number formatting) — golden vectors.
- digest mismatch on any 1-char change to thesis or salt.
- seq gap detection; duplicate seq rejected.
- hook blocks direct swap calls; allows executor with valid token; rejects expired/replayed token.
- hook default-denies every `mcp__clawpump*__*` tool not on the read allowlist (fixture: the §5.2 fund-mover list, both `mcp__clawpump__` and `mcp__clawpump_stdio__` prefixes); non-ClawPump tools pass.
- config check: a live Hermes discovery exposes only allowlisted ClawPump tools and no remote `mcp__clawpump__*` (port of `probe/hermes_live_check.py`).
- bond: token program detected from the mint owner; unknown owner or unsafe Token-2022 extension ⇒ refuse.
- firewall: each rule's block + fail-closed on missing price/equity.
- open-before-commit (S2 ≤ S1) flagged invalid by verifier.
- monitor: stop, TP, expiry each trigger correct exit + reveal.
- deadline sweeper marks unrevealed + slashes.
- verify rebuilds stats from chain data alone and matches ledger.

---

## 13. Honesty rules for docs/README (judges will check)
Keep a "What's real / what's not" table like Redline's. Don't claim perps, shorts, on-chain enforcement program, or trustless escrow unless built. Custodial escrow and self-hosted notary are disclosed limitations with a roadmap entry. Also disclose: (a) OATH constrains the **model**; another Hermes plugin granted `clawpump-stdio` in its `mcp_allowlist` could trade (call_mcp bypasses hooks and tool filters); (b) trades placed through the ClawPump dashboard or the hosted agent (chat/automations) happen outside Hermes and are not covered. The indexer should flag any agent-wallet swap without a matching `oath1:o` memo as "uncommitted trade".
