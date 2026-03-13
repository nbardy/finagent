---
name: hedge_modeling
description: Run hedge modeling for EWY or other underlyings in this repo. Use when the user wants macro-thesis scenario inputs, EV calculations, stress grids, ranked hedge vehicles, comparison of verticals/calendars/diagonals/long puts, or typed analysis outputs under analysis/{YYYY-MM-DD}. This is the modeling skill, not order filing.
---

# Hedge Modeling

Use this skill to model and rank hedge vehicles before any order is proposed.

Use `options-pricing` for a fair-value audit of one specific structure.
Use `hedge_proposal` only after the structure and target size are chosen.
Use `hedge_postmortem` when the user wants to compare realized results to the intended payoff shape or capture durable learnings.
Read [`source_playbook.md`](../references/source_playbook.md) when current external facts matter.

## Owns

- objective-first hedge framing
- macro scenario definition
- path-aware scorecards and EV comparisons
- typed analysis inputs and outputs
- `book / hedge / combined` PnL splits
- EV and stress testing
- hedge-universe scans and rankings

## Workflow

1. Start from the live book, not stale notes.
2. Declare `objective`, `intent`, and `path_model` before scoring anything.
3. Refresh market data with strict settings.
4. Build the smallest scenario set that matches the objective:
   - `instant_crash`: include at least `1d crash` and `7d hold-down`
   - `hold_down`: include at least `7d hold-down` and `14d flat-high-vol`
   - `rebound_window`: include at least one rebound path after the drawdown
5. Prefer `multi_step` scenarios for calendars and diagonals. If only `terminal` or `linear_path` is available, state that limitation explicitly.
6. Write typed input under `analysis/{YYYY-MM-DD}/`.
7. Run the smallest tool that answers the question.
8. Report `book`, `hedge`, and `combined` separately.
9. Save machine-readable output beside a short summary when useful.

## Main Scripts

- [`stock_tooling/portfolio_scenario_ev.py`](../../../stock_tooling/portfolio_scenario_ev.py)
- [`stock_tooling/overlay_scenario_ev.py`](../../../stock_tooling/overlay_scenario_ev.py)
- [`stock_tooling/pure_hedge_ev.py`](../../../stock_tooling/pure_hedge_ev.py)
- [`stock_tooling/scan_put_hedge_universe.py`](../../../stock_tooling/scan_put_hedge_universe.py)
- [`stock_tooling/scan_put_overlays.py`](../../../stock_tooling/scan_put_overlays.py)
- [`stock_tooling/audit_option_models.py`](../../../stock_tooling/audit_option_models.py)
  Only when a single structure needs a model sanity check.

## Required Output Contract

- state `objective`, `intent`, and `path_model`
- always separate `book`, `hedge`, and `combined`
- report `return_on_hedge_capital`
- state whether `base` includes short calls
- state whether the candidate is `additive` or `replacement`
- state `entry_pricing`: `mid`, `executable`, and selected assumption when entry cost matters
- if `used_fallback=true`, name the source and the missing IBKR fields or quotes
- if calendars or diagonals are in scope, show at least one near-term crash table beside the slower path tables
- prefer typed JSON under `analysis/{YYYY-MM-DD}/`

## Guardrails

- IBKR-first data paths
- no silent disk, Yahoo, implied-IV, or guessed-mark fallback
- for executable decisions, fail on incomplete IBKR option data rather than inventing inputs
- for learning-only comparisons, fallback is allowed only when explicitly labeled and non-executable
- do not let a calendar or diagonal rank first without showing its `1d crash` and `7d hold-down` behavior
- if calendars or diagonals lead, call out term-structure, front/back vol, and execution sensitivity
