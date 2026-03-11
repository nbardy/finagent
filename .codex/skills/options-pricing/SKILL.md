---
name: options-pricing
description: Price and audit option structures in the ikbr_trader repo using IBKR-first quotes and the repo's pricing models. Use when the user wants fair value, model consensus, or quote sanity checks for a single option, vertical spread, calendar spread, or diagonal before deciding whether to trade it.
---

# Options Pricing

Use this skill to decide whether an option or multi-leg structure is priced well.

## Scope

This skill owns:

- single-leg model audits
- same-expiry vertical pricing
- calendar pricing
- fair-value vs market comparisons
- quote sanity checks before execution

This skill does not own order submission. Use `options-execution` for probes, fills, and cancellations.

## Workflow

1. Pull fresh IBKR quotes.
2. Use the correct structure-specific pricer:
   - `stock_tooling/audit_option_models.py` for one leg
   - `stock_tooling/price_spread.py` for same-expiry verticals
   - `stock_tooling/price_calendar.py` for calendars
3. Report:
   - market bid, ask, and mid
   - model fair-value range
   - model consensus
   - whether the market is rich or cheap versus the models
4. If the market looks attractive but execution is uncertain, hand off to `options-execution`.

## Guardrails

- Use IBKR-first data.
- Do not silently fall back to Yahoo or stale disk data for live pricing.
- Treat displayed mid as reference, not executable truth.
- State clearly when the quote source is delayed or incomplete.
- If a multi-model audit is weak or inconsistent, say so instead of forcing a strong conclusion.
