# IKBR Trader — Agent Instructions

## Project Structure

```
ikbr_trader/
  .codex/skills/       # Repo-local Codex skills (source of truth)
  config/              # Persistent configuration
    pmcc_config.json   # IBKR connection, strategy params, execution settings
    portfolio_state.json  # Last portfolio sync snapshot
    probe_config.json  # Probe/scanner config
  orders/{YYYY-MM-DD}/ # Trade proposals by date
    *.json             # Executor-compatible JSON proposals
  analysis/{YYYY-MM-DD}/ # Scenario matrices, forecasts, comparisons
    *.json
  research_sessions/{timestamp}_{topic}/ # Local deep-research workspaces
    loose_notes/
    documents/{statements,filings,articles}/
    analysis/
    conclusions/
    final_report.md
  bespoke/             # Personal trading scripts (gitignored)
  custom_scripts/      # Repo-local custom extensions built on the typed core utils
  stratoforge/         # Strategy forge library (git submodule)
  stratoforge/pricing/      # Pricing models (BS, Heston, VG, Merton, calibration)
  stock_tooling/       # Weekly planner, stock analysis tools
  helpers/             # Shared typed data structures and hedge/execution helpers
  one_off_scripts/     # Small support scripts and repo maintenance helpers
  macro_research/      # Macro regime research
```

## Repo Conventions

- Treat this repo as the codebase for **FinAgent**.
- Use `.codex/skills/` as the source of truth for repo-local skills.
- Modeling outputs belong in `analysis/{YYYY-MM-DD}/`.
- Executable order proposals belong in `orders/{YYYY-MM-DD}/`.
- Deep research artifacts belong in `research_sessions/{timestamp}_{topic}/`.
- `agent_notes/` is historical operating context, not live state. Before acting on a thread note, verify the current IBKR portfolio, open orders, and quote availability.
- Hedge and overlay analysis should report `book`, `hedge`, and `combined` separately.
- Proposal generation should state whether the order is `add`, `replace`, `trim`, or `close`.
- For executable pricing, prefer IBKR and fail loud on missing live data rather than silently falling back.
- Personal trading scripts (session-specific, ticker-hardcoded) belong in `bespoke/`. This directory is gitignored and not part of the public repo.

## Hedge Analysis Contract

- Every hedge analysis must declare `objective`: `instant_crash`, `hold_down`, `carry`, or `rebound_window`.
- Every hedge candidate or proposal must declare `intent`: `add`, `replace`, `trim`, or `close`.
- Hedge comparisons must report `book`, `hedge`, `combined`, and `return_on_hedge_capital`.
- Hedge analysis must state `path_model`: `terminal`, `linear_path`, or `multi_step`.
- If modeling continues without executable IBKR option data, set `used_fallback=true`, name the fallback source, and say why IBKR was insufficient.
- Keep repo-wide hedge rules here; keep step-by-step workflow detail in `.codex/skills/`.

## Extension Model

- Put new repo-specific automation in `custom_scripts/`.
- Custom logic should import and reuse the typed core modules instead of duplicating broker, pricing, or order-state logic.
- Keep reusable primitives in the core modules; keep strategy-specific orchestration in `custom_scripts/`.
- For deep research workflows, prefer creating a dedicated script in `custom_scripts/` that writes into `research_sessions/` and records the Codex thread id it used.
- `bespoke/` is for personal, non-reusable trading scripts — quick checks, one-off order scripts, session experiments. It is gitignored. If a bespoke script proves generally useful, refactor it into `custom_scripts/`.

## Core Utility Modules

When extending the repo, prefer leaning on:

- `ibkr.py`
  Live broker connection, quotes, portfolio, open orders, account summary, and recent fills.
  - Contract qualification only proves the contract exists. It does not prove there is a usable bid/ask or model greek surface for pricing.
  - `Position` now exposes explicit `base_currency`, `fx_rate_to_base`, `base_*`, and `local_*` fields. For new code, prefer those explicit fields over assuming `market_value` or `avg_cost` are native-currency values.
  - `get_recent_fills()` — returns `FillEvent` with `realized_pnl`, `commission`, `currency`
  - `persist_fills()` — appends new fills to `config/fill_ledger.json` (deduped by `exec_id`)
  - `load_fill_ledger(symbol=, side=)` — loads full fill history from ledger with optional filters
  - Fill ledger accumulates automatically via `stock_tooling/get_portfolio.py` — every portfolio check persists all fills
  - To answer "what did I close and at what P&L?" use `load_fill_ledger(symbol="EWY", side="SLD")`
- `stratoforge/pricing/`
  Pricing models, tranche logic, probe construction, and contract/model types.
- `stock_tooling/`
  Scenario analysis, price tools, scanners, planners, and watch rules.
  - Shared console formatting lives in `stock_tooling/reporting.py`. Keep `stock_tooling/get_portfolio.py` as the rich portfolio CLI and reuse `stock_tooling/reporting.py` for simpler watcher/order views.
- `helpers/`
  Shared hedge and scenario dataclasses plus execution-support helpers.

## Stratoforge Usage

Use Stratoforge when the job is:

- turn a macro or thesis tree into a large options candidate universe
- compare many structures under mixed scenario horizons and probabilities
- score candidates by scenario P&L rather than just enumerate them
- return scored analysis artifacts under `analysis/{YYYY-MM-DD}/`

Do not use Stratoforge when the job is:

- price one specific live spread for execution
- build an executable order ticket
- inspect current IBKR position state

For those cases, prefer the narrower pricing / execution tools.

Canonical Stratoforge entrypoint:

- `uv run python custom_scripts/run_stratoforge.py --thesis ... --chain ...`

Legacy compatibility wrapper:

- `uv run python custom_scripts/score_strategy_universe.py --thesis ... --chain ...`

Current model policy:

- `SSVI` is the canonical surface model and diagnostic state
- `Bates` is the default decision model
- `Heston` is the structural fallback when `Bates` is unavailable
- `BS` is the fallback / sanity anchor

Interpretation rules:

- prefer the scored Stratoforge path, not scan-only enumeration, for decision support
- read `model_policy`, `calibration_summary`, and `surface_summary` from the output
- do not assume multi-model blending is the right default; on the current validated snapshot, `Bates` is the preferred decision model
- fixed-grid `Heston/Bates` are active in live scoring; check `fixed_grid_pricers_active` in the output if you need to confirm

## Signature Inspection

The codebase is intentionally typed so agents can inspect and reuse the library surface safely.

Use this command to inspect a symbol signature from the terminal:

```bash
uv run python one_off_scripts/show_signature.py ibkr connect
```

More examples:

```bash
uv run python one_off_scripts/show_signature.py ibkr get_open_orders
uv run python one_off_scripts/show_signature.py stock_tooling.watch_rules load_watch_rules
uv run python one_off_scripts/show_signature.py stratoforge.pricing.probe build_probe_trades
uv run python one_off_scripts/show_signature.py custom_scripts.research_session do_research
uv run python one_off_scripts/show_signature.py custom_scripts.research_session get_users_latest_tweet
```

## Script Output Paths

Scripts auto-write to the correct directory:

| Script | Writes | To |
|--------|--------|----|
| `planner.py` | trade proposals | `orders/{today}/trade_proposal.json` |
| `planner_leap.py` | LEAP proposals | `orders/{today}/trade_proposal.json` |
| `pmcc_portfolio.py` | PMCC strategy inventory sync | `config/portfolio_state.json` |
| `stock_tooling/get_portfolio.py` | general portfolio, multi-currency pricing & fill ledger | `config/fill_ledger.json` |
| `regime_detector.py` | regime state | `config/regime_state.json` |
| `stock_tooling/planner_weekly.py` | weekly probes | user-specified `--output` path |
| `stock_tooling/price_spread.py` | spread proposals | user-specified `--proposal` path |
| `stock_tooling/scenario_analyzer.py` | scenario matrices | user-specified `--output` path |
| `helpers/urgent_hedge.py` | hedge bundles | user-specified path |

When creating proposals manually (e.g. from Claude), write to `orders/{YYYY-MM-DD}/descriptive_name.json`.

## File Conventions

### Order Proposals
All trade proposals go in `orders/{YYYY-MM-DD}/`. Use the trade date, not creation date.

JSON schema — executor.py accepts:
```json
{
  "description": "Human-readable summary",
  "generated": "YYYY-MM-DD",
  "trades": [
    {
      "contract": { "secType": "STK|BAG|OPT", "symbol": "...", "exchange": "SMART", "currency": "USD|GBP|JPY" },
      "action": "BUY|SELL",
      "tif": "GTC|DAY",
      "algo": "Adaptive",           // optional — not available on OTC/Pink Sheet
      "algoPriority": "Normal",     // Urgent | Normal | Patient
      "tranches": [
        { "tranche": 1, "quantity": 100, "lmtPrice": 20.0, "note": "visible in TWS as orderRef" }
      ]
    }
  ]
}
```

### Currency / Price Units (CRITICAL)
IBKR uses major currency codes but some exchanges quote in subunits:
- **GBP stocks (LSE/AIM)**: prices in **pence** (GBX). `20.0` = 20p, NOT `0.20`.
- **JPY stocks (TSE)**: prices in **yen**. TSE requires 100-share lot sizes.
- **USD stocks**: prices in dollars as expected.

`assert_price_units()` in executor.py guards against unit misalignment at submission time.

### Analysis Files
Scenario matrices, early-exit models, EV calculations go in `analysis/{YYYY-MM-DD}/`.

## Execution

```bash
# Submit a trade proposal
uv run python executor.py --file orders/2026-03-10/photonics_stocks.json

# View full multi-currency portfolio state
PYTHONPATH=. uv run python stock_tooling/get_portfolio.py

# Sync PMCC state for bot
uv run python pmcc_portfolio.py

# Run PMCC bot cycle
uv run python main.py
```

## Order Pricing Rules (MANDATORY)

Agents placing live orders MUST follow these rules. Sloppy limit prices cost real money.

1. **Always price at the mid.** Compute `(bid + ask) / 2` and use that as the limit price. Never use the ask for buys or the bid for sells. If you cannot observe the bid/ask (no market data subscription, market closed), you MUST tell the user and get explicit price guidance before submitting.
2. **Never use the day's high/low as a limit price.** A high or low is an extreme print, not a fair price. Using it as your limit is crossing the spread for no reason.
3. **If no live bid/ask is available, do not guess.** Say so. Propose the order with a placeholder price and let the user confirm from TWS or another data source. Submitting a limit order based on stale portfolio snapshots or chart screenshots is not acceptable — those do not show the current spread.
4. **Round limit prices to the instrument's tick size.** Most US equities tick at $0.01. SEK stocks on SFB tick at 0.01 SEK. Options tick at $0.05 (>$3) or $0.01 (<$3). Do not submit prices with spurious precision.
5. **For large orders relative to typical volume, tranche the entry.** Split into 2-4 tranches at staggered limit prices around the mid to reduce market impact. Ask the user for tranche sizing preference if not specified.
6. **State the spread and mid before submitting.** Always print: `bid={bid} ask={ask} mid={mid} → limit={limit}` so the user can verify before the order fires. If the order is urgent and pre-approved, still log it.

Violation of these rules wastes real capital on every fill. There is no "close enough" — a sloppy limit on 20,000 shares at 0.05 SEK over mid is 1,000 SEK lost for nothing.

## IBKR Gotchas
- **Adaptive algo**: Not supported on OTC/Pink Sheet stocks (Error 442). Use plain market orders.
- **Foreign exchange orders**: Require "Bypass Order Precautions" and "Bypass Redirect Order warning" in Gateway → Global Config → API → Precautions.
- **reqGlobalCancel()**: Orders on closed exchanges get stuck in PendingCancel. Don't cancel+resubmit when exchange is closed.
- **Client ID isolation**: Different client IDs can't see each other's orders. Use `reqAllOpenOrders()`.
- **Error 10311**: Direct-routed order precautionary setting. Fix in Gateway API precautions.
- **Execution preflight**: Before submit, validate venue permissions, `Adaptive` availability, `outsideRth` compatibility, and exchange price units. Do not rely on broker rejections as discovery.

## Model Calibration
All pricing models (Heston, VG, MJD) require calibrated parameters — no defaults allowed.
Use `stratoforge/pricing/calibrate.py` to fit params to observed option chain before pricing.
