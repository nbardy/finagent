---
name: hedge_modeling
description: Run hedge modeling for EWY or other underlyings in this repo. Use when the user wants macro-thesis scenario inputs, EV calculations, stress grids, ranked hedge vehicles, comparison of verticals/calendars/diagonals/long puts, or typed analysis outputs under analysis/{YYYY-MM-DD}. This is the modeling skill, not order filing.
---

# Hedge Modeling

Use this skill to model and rank hedge vehicles before any order is proposed.

## Scope

This skill owns:

- macro scenario definition
- typed analysis inputs and outputs
- book / hedge / combined PnL splits
- EV calculations under weighted scenario probabilities
- broad hedge-universe scans
- stress tables across spot moves and timelines

This skill does not own broker-ready order JSON. If the user wants executable proposals, use `hedge_proposal`.
Use `options-pricing` when a specific leg, spread, or calendar needs fair-value audit before execution.

## Default Workflow

1. Start from the live book, not stale notes.
2. Refresh market data from IBKR with strict settings.
3. Write a typed analysis input under `analysis/{YYYY-MM-DD}/`.
4. Run the smallest tool that answers the question:
   - scenario EV for a shortlist
   - broad universe scan for discovery
   - spot-grid stress table for sanity checks
5. Report `book`, `hedge`, and `combined` separately.
6. Save machine-readable output and, if useful, a short markdown summary beside it.
7. Hand the winner to `hedge_proposal` or `options-execution` only after structure and target size are settled.

## Strict Data Rules

- Prefer IBKR-first data paths.
- Default to strict refresh behavior.
- Do not silently fall back to disk snapshots, Yahoo, inferred IV, or guessed marks.
- If data is incomplete, say so and fail the modeling step rather than inventing inputs.

## Main Tools

- [`stock_tooling/portfolio_scenario_ev.py`](../../../stock_tooling/portfolio_scenario_ev.py)
  Use for scenario-level `book / overlay / combined` EV.
- [`stock_tooling/overlay_scenario_ev.py`](../../../stock_tooling/overlay_scenario_ev.py)
  Use when comparing overlay candidates on top of the current book.
- [`stock_tooling/pure_hedge_ev.py`](../../../stock_tooling/pure_hedge_ev.py)
  Use when the user wants hedge-only evaluation.
- [`stock_tooling/scan_put_hedge_universe.py`](../../../stock_tooling/scan_put_hedge_universe.py)
  Use for broad scans across verticals, calendars, diagonals, and long puts.
- [`stock_tooling/scan_put_overlays.py`](../../../stock_tooling/scan_put_overlays.py)
  Use for narrower strike/date sweeps when the user already knows the relevant window.

## Required Output Shape

When presenting results, keep these fields explicit:

- `book_pnl`
- `hedge_pnl` or `overlay_pnl`
- `combined_pnl`
- `probability`
- `expected_book_pnl`
- `expected_hedge_pnl`
- `expected_combined_pnl`

If you generate a spot-grid table, keep both:

- weekly horizon rows
- monthly or event-window rows

## File Placement

- typed inputs: `analysis/{YYYY-MM-DD}/descriptive_name_input.json`
- typed outputs: `analysis/{YYYY-MM-DD}/descriptive_name_output.json`
- short summaries: `analysis/{YYYY-MM-DD}/descriptive_name.md`

## Interpretation Rules

- Separate the income sleeve from the hedge sleeve.
- State whether `base` includes short calls.
- Be explicit about whether a candidate is being evaluated:
  - as an additive hedge
  - as a replacement hedge
  - against the live book excluding an existing hedge
- Prefer practical structures over fragile ones when model EVs are close.
- If calendars or diagonals lead, call out term-structure dependence and execution sensitivity.

## Response Style

- Lead with the winner and the reason it won.
- Then show the best simple fallback.
- Then show the key failure mode.
- Keep the answer tied to the user's stated macro probabilities and time window.
