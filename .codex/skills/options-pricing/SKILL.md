---
name: options-pricing
description: Price and audit option structures in the ikbr_trader repo using IBKR-first quotes and the repo's pricing models. Use when the user wants fair value, model consensus, or quote sanity checks for a single option, vertical spread, calendar spread, or diagonal before deciding whether to trade it.
---

# Options Pricing

Use this skill to decide whether an option or multi-leg structure is priced well.

Use this skill only for fair-value and quote sanity checks on one chosen structure.
Use `hedge_modeling` for macro EV and vehicle ranking.
Use `options-execution` or `hedge_proposal` for live order files.

## Owns

- single-leg model audits
- same-expiry vertical pricing
- calendar pricing
- fair-value vs market comparisons

## Main Scripts

- `stock_tooling/audit_option_models.py`
- `stock_tooling/price_spread.py`
- `stock_tooling/price_calendar.py`

## Guardrails

- IBKR-first data
- no silent Yahoo or stale-disk fallback for live pricing
- reported mid is reference, not executable truth
- contract qualification is not quote availability; if bid/ask or greeks are empty, say so explicitly
- if model consensus is weak, say so
