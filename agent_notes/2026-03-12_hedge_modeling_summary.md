# Hedge Modeling Summary
**Date:** 2026-03-12
**Scope:** EWY hedge modeling work completed across this thread.

## Main Thesis Windows Modeled

### 1. Early-April bottom window
Used repeatedly for EWY:
- `35%` bottom by Apr 2, then rebound
- `40%` bottom by Apr 10, then rebound
- `15%` choppy hold into earnings window
- `10%` early squeeze higher

This was the main thesis used for:
- spot-grid stress tables
- vertical/calendar/diagonal ranking
- broad hedge-universe scans

### 2. Monthly macro regime
Used for broader sanity checks:
- `50%` choppy flat month
- `40%` down `8%` over month
- `10%` up `8%` over month

## Main Modeling Conclusions

### 1. The short-dated Mar 20 crash hedge was the wrong shape
- Good for an immediate crash
- Bad for an orderly bleed or a bottom closer to Apr 2 to Apr 10
- This was the key mismatch we corrected

### 2. The best simple verticals were later April structures
Important candidates we evaluated:
- `Apr 10 135/125`
- `Apr 10 135/120`
- `Apr 17 140/125`

Best simple practical read for the bottom-window thesis:
- `Apr 10 135/120`

### 3. Broad scans favored calendars
From the later full-universe scans:
- `Apr 10 / Apr 24 120P` calendar ranked best in both weekly and monthly runs
- `Apr 10 / Apr 24 125P` calendar also ranked near the top
- diagonals were valid but weaker than the best calendars
- outright long puts ranked poorly

### 4. No pure paid hedge gives every path for free
There is no simple bought-put structure that:
- makes money on `+8%`
- makes money on `-8%`
- and also makes money on flat/chop

The smoother profile came from:
- the long EWY book
- the short-call sleeve
- plus a later-dated downside sleeve

## Files Produced

Key modeling outputs:
- `analysis/2026-03-11/ewy_vehicle_rankings_50_40_10_typed.json`
- `analysis/2026-03-11/ewy_bottom_apr2_apr10_timing_output.json`
- `analysis/2026-03-11/ewy_put_overlay_batch_scan_apr02_apr10.json`
- `analysis/2026-03-11/ewy_current_live_overlay_ev.json`
- `analysis/2026-03-11/ewy_current_live_split_table.json`
- `analysis/2026-03-11/ewy_current_live_split_table_week_down_extension.json`
- `analysis/2026-03-12/ewy_broad_put_hedge_universe_weekly_35_40_15_10.json`
- `analysis/2026-03-12/ewy_broad_put_hedge_universe_monthly_50_40_10.json`
- `analysis/2026-03-12/ewy_top3_spot_grid.json`

## Important Corrections Made

- modeling now separates `book`, `hedge`, and `combined`
- month-long scenarios are path-aware when short-dated hedges expire before the end horizon
- strict-refresh behavior was pushed into the main EV tooling
- silent pricing fallbacks were removed from the main hedge-modeling path

## Current Best Interpretive Read

If choosing fresh from scratch under the early-April bottom thesis:
- best broad model winner: April calendars
- best simple fallback: `Apr 10 135/120`
- worst mismatch: short-dated pure crash hedges like the original Mar 20 sleeve
