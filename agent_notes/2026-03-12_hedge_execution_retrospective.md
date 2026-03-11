# Hedge Execution Retrospective
**Date:** 2026-03-12
**Scope:** What happened operationally, what went wrong, and what the repo now assumes.

## Main Execution Mistakes

### 1. We stayed in research mode too long
- too much time spent modeling live
- not enough time spent freezing one structure and sending it
- this caused the first EWY hedge window to be missed into the close

### 2. We layered hedges instead of replacing cleanly
- the Mar 20 crash hedge was approved and sent
- later the Apr 10 hedge was added on top
- this created more put-hedge size than originally intended

### 3. We overshot one hedge target
- the Apr 10 hedge size exceeded the original target
- this came from remainder logic and live-position reconciliation not being explicit enough

### 4. We needed clearer `add vs replace` intent
This is now treated as a required repo convention:
- `add`
- `replace`
- `trim`
- `close`

## What Was Correct

- multi-leg hedge entries were sent as `BAG` combo orders
- this prevented accidental naked half-leg entries
- the same rule applies for closes and trims

## Operational Lessons

### 1. Hedge modeling and hedge proposal are different steps
- model first
- choose structure and target size
- only then generate executable files

### 2. Probes should be used only when time allows
- a probe is for execution quality discovery
- not for rediscovering the whole thesis
- when the session is nearly closed, paying up earlier can be better than over-probing

### 3. Broad hedges and crash hedges should not be mixed casually
- the Mar 20 sleeve was a crash hedge
- the Apr 10 sleeve was a broader early-April hedge
- these should have been treated as alternatives, not automatic layers

## Files Relevant To Execution

Examples from this thread:
- `orders/2026-03-11/ewy_urgent_big_crash_hedge*.json`
- `orders/2026-03-11/ewy_urgent_repriced_open_ready.json`
- `orders/2026-03-11/ewy_best_overlay_apr10_135_120_live.json`
- `orders/2026-03-11/ewy_close_mar20_crash_hedge.json`
- `orders/2026-03-12/ewy_close_apr10_135_120_at_entry.json`

## Current Repo-Level Rules We Want To Preserve

- multi-leg structures should be filed as `BAG`
- executable pricing should come from IBKR, not Yahoo or disk snapshots
- proposal generation should reconcile against live positions before sizing
- execution logic should avoid leaving resting orders that can overshoot target size

## Remaining Optional Improvement

The main remaining operational improvement is code, not prompt wording:
- make `intent=add|replace|trim|close` required in the proposal path
- make live-position reconciliation mandatory before writing executable orders
