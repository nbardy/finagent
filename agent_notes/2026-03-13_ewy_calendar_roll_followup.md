# EWY Calendar And Roll Follow-Up
**Date:** 2026-03-13
**Scope:** Late-thread practical state after reviewing the EWY put calendar, updating hedge-modeling assumptions, and placing the overwrite roll.

## Hedge Diagnosis

### 1. The live hedge is a calendar, not a diagonal
- short `173x EWY Apr 10 2026 120P`
- long `173x EWY Apr 24 2026 120P`
- same strike, different expiries

Main consequence:
- this is a long-vega, short-front-gamma structure
- it was never guaranteed to be immediately green on the first sharp down day while spot was still well above `120`

### 2. The user's frustration about entry price was directionally valid
The broad scan that ranked this structure used a much cheaper assumed entry than what was actually paid.

- broad scan assumption: about `1.05` per spread
- actual live basis: about `1.4626` per spread
- gap: about `+0.4126` per spread
- percent richer than scan assumption: about `+39.3%`
- total extra debit versus scan assumption on the actual `173x`: about `$7.1k`

Important nuance:
- later single-structure model audit was much less negative than the broad scan comparison
- later audit market mid was about `1.20`
- later richer-model mean was about `1.5719`
- actual basis was above the market mid but below richer-model consensus

### 3. The endpoint thesis still made sense
Rough path check done during the thread:
- if EWY is around `120-123` by `Apr 2, 2026`, the calendar still looks reasonable
- approximate value at that window was around `2.73-2.89`
- that implies roughly `+86%` to `+97%` versus actual entry

Main interpretation:
- bad immediate crash behavior did not prove the endpoint thesis wrong
- it mainly showed path dependence plus a richer-than-scan entry

## Tooling Changes Made

### 1. Hedge-universe scans now model entry more honestly
Updated:
- `stock_tooling/scan_put_hedge_universe.py`
- `stock_tooling/scan_put_overlays.py`

Added:
- `--entry-pricing {mid,blended,executable}`
- `--entry-slippage-frac`
- stored `entry_cost_mid`
- stored `entry_cost_executable`
- stored selected entry method metadata

Purpose:
- avoid ranking structures off unrealistically optimistic mid-only debits

### 2. Scenario bands were added to EV summaries
Updated:
- `stock_tooling/portfolio_scenario_ev.py`

Added scenario-distribution outputs:
- `p10`
- `p50`
- `p90`
- `stddev`
- `min`
- `max`

Important note:
- these are scenario bands, not full statistical confidence intervals
- still useful as a first-pass uncertainty read

### 3. Single-option audit summaries were improved
Updated:
- `stock_tooling/audit_option_models.py`

Added:
- `consensus_summary`
- `rich_model_summary`

Purpose:
- expose model dispersion directly for overwrite pricing decisions

## Short-Call Management Conclusions

### 1. Most of the April sleeve had not met an early-close threshold
At the time of review:
- only `Mar 13 2026 151C` was effectively done at about `99.7%` captured
- the April calls were still around the `40-49%` captured range
- conclusion was to keep the April sleeve on rather than harvesting early

### 2. Rolling the expiring line early was a directional choice, not a free lunch
The user's stated updated view became:
- likely more downside near term
- comfortable selling next week's overwrite early

Thread conclusion:
- early roll is fine if the goal is continuous overwrite exposure into further weakness
- it is not automatically superior if the user's preference is to sell calls into strength

## Orders Created And Placed

### 1. Proposal files written
- `orders/2026-03-12/ewy_mar13_151c_close_11x.json`
- `orders/2026-03-12/ewy_mar20_150c_roll_open_11x.json`
- `orders/2026-03-12/ewy_roll_mar13_151c_to_mar20_150c_11x.json`

### 2. The BAG roll was the final execution path used
Submitted live:
- atomic IBKR-style BAG roll
- buy back `11x Mar 13 2026 151C`
- sell `11x Mar 20 2026 150C`

Working ladder:
- `4x @ 0.35` credit
- `4x @ 0.33` credit
- `3x @ 0.30` credit

### 3. Current order state when the thread was parked
- BAG roll was placed successfully through `executor.py`
- all three tranches were still `PreSubmitted`
- no fill had printed yet
- original `-11x Mar 13 2026 151C` was still on the book
- no new `Mar 20 2026 150C` short had printed yet

Practical interpretation:
- `PreSubmitted` here looked like normal IB Adaptive holding/routing behavior, not a broken order
- the user explicitly said they were comfortable waiting

## Canonical Files From This Thread

- `analysis/2026-03-12/ewy_broad_put_hedge_universe_weekly_35_40_15_10.json`
- `analysis/2026-03-12/ewy_20260410_20260424_120p_calendar_model_audit.json`
- `analysis/2026-03-12/ewy_20260320_150c_model_audit.json`
- `orders/2026-03-12/ewy_roll_mar13_151c_to_mar20_150c_11x.json`

## Suggested Re-Entry Point If Reopened

If this topic is reopened later, check in this order:
- open EWY orders
- recent EWY fills
- whether the `Mar 13 151C` line expired or was closed by the roll
- whether the `Mar 20 150C` line printed
- whether the BAG roll needs repricing lower
