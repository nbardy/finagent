---
name: hedge_modeling
description: Run hedge modeling for EWY or other underlyings in this repo. Use when the user wants macro-thesis scenario inputs, EV calculations, stress grids, ranked hedge vehicles, comparison of verticals/calendars/diagonals/long puts, or typed analysis outputs under analysis/{YYYY-MM-DD}. This is the modeling skill, not order filing.
---

# Hedge Modeling

Use this skill to model and rank hedge vehicles before any order is proposed.

Use `options-pricing` for a fair-value audit of one specific structure.
Use `hedge_proposal` only after the structure and target size are chosen.
Read [`source_playbook.md`](../references/source_playbook.md) when current external facts matter.

## Owns

- macro scenario definition
- typed analysis inputs and outputs
- `book / hedge / combined` PnL splits
- EV and stress testing
- hedge-universe scans and rankings

## Workflow

1. Start from the live book, not stale notes.
2. Refresh market data with strict settings.
3. Write typed input under `analysis/{YYYY-MM-DD}/`.
4. Run the smallest tool that answers the question.
5. Report `book`, `hedge`, and `combined` separately.
6. Save machine-readable output beside a short summary when useful.

## Main Scripts

- [`stock_tooling/portfolio_scenario_ev.py`](../../../stock_tooling/portfolio_scenario_ev.py)
- [`stock_tooling/overlay_scenario_ev.py`](../../../stock_tooling/overlay_scenario_ev.py)
- [`stock_tooling/pure_hedge_ev.py`](../../../stock_tooling/pure_hedge_ev.py)
- [`stock_tooling/scan_put_hedge_universe.py`](../../../stock_tooling/scan_put_hedge_universe.py)
- [`stock_tooling/scan_put_overlays.py`](../../../stock_tooling/scan_put_overlays.py)
- [`stock_tooling/audit_option_models.py`](../../../stock_tooling/audit_option_models.py)
  Only when a single structure needs a model sanity check.

## Required Output Contract

- always separate `book`, `hedge`, and `combined`
- state whether `base` includes short calls
- state whether the candidate is `additive` or `replacement`
- prefer typed JSON under `analysis/{YYYY-MM-DD}/`

## Guardrails

- IBKR-first data paths
- no silent disk, Yahoo, implied-IV, or guessed-mark fallback
- if calendars or diagonals lead, call out term-structure and execution sensitivity
- if data is incomplete, fail the modeling step rather than inventing inputs
