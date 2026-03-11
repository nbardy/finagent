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
  option_pricing/      # Pricing models (BS, Heston, VG, Merton, calibration)
  stock_tooling/       # Weekly planner, stock analysis tools
  macro_research/      # Macro regime research
```

## Repo Conventions

- Use `.codex/skills/` as the source of truth for repo-local skills.
- Modeling outputs belong in `analysis/{YYYY-MM-DD}/`.
- Executable order proposals belong in `orders/{YYYY-MM-DD}/`.
- Hedge and overlay analysis should report `book`, `hedge`, and `combined` separately.
- Proposal generation should state whether the order is `add`, `replace`, `trim`, or `close`.
- For executable pricing, prefer IBKR and fail loud on missing live data rather than silently falling back.

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
