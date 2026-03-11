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
  agent_notes/         # Tracked operating notes and thread retrospectives
  custom_scripts/      # Repo-local custom extensions built on the typed core utils
  option_pricing/      # Pricing models (BS, Heston, VG, Merton, calibration)
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
- Hedge and overlay analysis should report `book`, `hedge`, and `combined` separately.
- Proposal generation should state whether the order is `add`, `replace`, `trim`, or `close`.
- For executable pricing, prefer IBKR and fail loud on missing live data rather than silently falling back.
- `agent_notes/` is tracked. Do not treat it as throwaway local output.

## Extension Model

- Put new repo-specific automation in `custom_scripts/`.
- Custom logic should import and reuse the typed core modules instead of duplicating broker, pricing, or order-state logic.
- Keep reusable primitives in the core modules; keep strategy-specific orchestration in `custom_scripts/`.
- For deep research workflows, prefer creating a dedicated script in `custom_scripts/` that writes into `research_sessions/` and records the Codex thread id it used.

## Core Utility Modules

When extending the repo, prefer leaning on:

- `ibkr.py`
  Live broker connection, quotes, portfolio, open orders, account summary, and recent fills.
- `option_pricing/`
  Pricing models, tranche logic, probe construction, and contract/model types.
- `stock_tooling/`
  Scenario analysis, price tools, scanners, planners, and watch rules.
- `helpers/`
  Shared hedge and scenario dataclasses plus execution-support helpers.

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
uv run python one_off_scripts/show_signature.py option_pricing.probe build_probe_trades
uv run python one_off_scripts/show_signature.py custom_scripts.research_session do_research
```

## Script Output Paths

Scripts auto-write to the correct directory:

| Script | Writes | To |
|--------|--------|----|
| `planner.py` | trade proposals | `orders/{today}/trade_proposal.json` |
| `planner_leap.py` | LEAP proposals | `orders/{today}/trade_proposal.json` |
| `portfolio.py` | portfolio snapshot | `config/portfolio_state.json` |
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

# Sync portfolio state
uv run python portfolio.py

# Run PMCC bot cycle
uv run python main.py
```

## IBKR Gotchas
- **Adaptive algo**: Not supported on OTC/Pink Sheet stocks (Error 442). Use plain market orders.
- **Foreign exchange orders**: Require "Bypass Order Precautions" and "Bypass Redirect Order warning" in Gateway → Global Config → API → Precautions.
- **reqGlobalCancel()**: Orders on closed exchanges get stuck in PendingCancel. Don't cancel+resubmit when exchange is closed.
- **Client ID isolation**: Different client IDs can't see each other's orders. Use `reqAllOpenOrders()`.
- **Error 10311**: Direct-routed order precautionary setting. Fix in Gateway API precautions.

## Model Calibration
All pricing models (Heston, VG, MJD) require calibrated parameters — no defaults allowed.
Use `option_pricing/calibrate.py` to fit params to observed option chain before pricing.
