# Agent 2 Dump (EWY Hedge / Call-Sale View)
**Date:** 2026-03-11
**Context:** Integrated view after the March 10, 2026 US close, for the March 11, 2026 US open.

## Current Live EWY State

### 1. Downside hedge sleeve
The live downside hedge is the short-dated crash sleeve in:
- `orders/2026-03-11/ewy_urgent_repriced_open_ready.json`

Working broker orders:
- Buy 14x EWY Mar 20 135/121 put spread @ 7.20
- Buy 14x EWY Mar 20 135/121 put spread @ 7.25
- Buy 14x EWY Mar 20 135/121 put spread @ 7.25

Opinion:
- This is a **fast crash hedge**, not a broad hedge.
- It helps most on a fast downside move in the next week.
- It does **not** solve an orderly month-long bleed by itself.

### 2. Low-bucket income sleeve
The canonical next-open call sale file is:
- `orders/2026-03-11/ewy_next_open_call_sales.json`

Queued broker orders:
- Sell 7x EWY Apr 10 145C @ 4.90
- Sell 20x EWY Apr 10 150C @ 4.00
- Sell 20x EWY Apr 10 150C @ 3.80
- Sell 20x EWY Apr 10 150C @ 3.60
- Sell 10x EWY Apr 2 150C @ 3.30
- Sell 10x EWY Apr 2 150C @ 3.20
- Sell 10x EWY Apr 2 150C @ 3.10

Opinion:
- This is the correct use of the `145C/150C` bucket.
- The pricing is sensible versus the last public modeled books.
- This sleeve already consumes the full currently clean low-bucket cover available for `145/150` strikes.

### 3. Remaining clean inventory
Current available cover from `config/portfolio_state.json`:
- 145C bucket: 7
- 150C bucket: 90
- 165C bucket: 40
- 210C bucket: 110

Interpretation:
- The `145/150` bucket is already spoken for by the live open orders.
- The next clean additive income sleeve is the `165C` bucket.
- The `210C` bucket should mostly stay open unless we use a higher-strike short call that actually matches that bucket.

## What We Believe

### 1. Put spreads should be a separate hedge sleeve
We agree with the other agent on structure:
- short calls are the income / de-risking sleeve
- put spreads are the downside hedge sleeve
- do not pair one put spread mechanically to one short call

This is the right mental model:
- short calls reduce upside and collect premium
- put spreads spend premium and reduce downside
- together they make the book more range-bound

That is good if the goal is lower variance.
That is bad if the goal is full upside participation.

### 2. The 145/150 bucket is already correctly deployed
We should **not** add any more low-bucket overwrite files from this agent while the current ladder is live.

Specifically, these files should stay on disk unless the current low-bucket orders are canceled and replaced:
- `orders/2026-03-11/ewy_broader_overwrite_apr17_150c_x60.json`
- `orders/2026-03-11/ewy_broader_financed_apr17_overlay_x60_x49.json`

Reason:
- they assume additional low-bucket short calls
- the low bucket is already full
- submitting them as-is risks double-encumbering the same cover

### 3. The 165C bucket is the clean next increment
We agree that:
- selling Apr 10 170C against the 40x 165C longs is clean
- 175C / 180C were less attractive on the quoted snapshot
- this is the correct bucket to monetize next if more income is desired

Opinion:
- this is the best next additive call-sale sleeve
- it does not interfere with the already live `145/150` sleeve
- it helps fund the broader de-risking thesis without touching the crash hedge

### 4. Do not force the 210C bucket into the wrong shape
We agree strongly with the warning:
- do **not** sell a 6-month 180C against the Jan 2028 210C longs

Opinion:
- that is the wrong diagonal shape
- it effectively makes the `210C` bucket bearish between `180` and `210`
- it introduces avoidable assignment and management risk

If monetizing the `210C` bucket at all:
- use a higher strike like `Oct 215C` or `Oct 220C`
- but this is lower priority than the `165 -> 170` diagonal
- the `210C` bucket is better left open for upside convexity unless we explicitly want to cap it

## What Our Modeling Says

The corrected broader-coverage run is in:
- `analysis/2026-03-11/ewy_broader_coverage_output.json`

Main conclusion:
- the current Mar 20 crash sleeve is **not** broad protection
- the main thing that improved `month down` and `choppy month` scenarios was funded de-risking via short calls
- small buy-only add-on put sleeves did not solve the slow month-down case well enough at current IV

Opinion:
- if the goal is “protect next week crash only,” the Mar 20 hedge is fine
- if the goal is “protect next week crash + month-down + chop,” then short calls matter more than another small bought put sleeve
- that is why the other agent’s bucketed call-sale plan fits well with our work

## Practical Integration Rules

1. Keep the current Mar 20 put-spread hedge sleeve working.
2. Keep the current low-bucket Apr 2 / Apr 10 short-call ladder working.
3. Do not submit any new low-bucket overwrite from this agent unless the existing ladder is canceled first.
4. If adding one new income sleeve, add `Apr 10 170C` against the `40x 165C` bucket.
5. Leave the `210C` bucket open unless there is a deliberate decision to cap that convexity with a higher-strike October short.

## Next Best Action

If we want one additional incremental trade from here, it should be:
- stage an open-ready `Apr 10 170C x40` ladder against the `165C` bucket

That would be additive, clean, and consistent with both:
- the live broker state
- the broader hedge logic already modeled

## Tooling / Model Notes

Important fix already made:
- the scenario engine is now path-aware for month-long scenarios when short-dated hedges expire before the scenario horizon

Relevant files:
- `helpers/scenario_pricing.py`
- `helpers/urgent_hedge.py`
- `stock_tooling/portfolio_scenario_ev.py`
- `tests/test_scenario_pricing.py`

Opinion:
- this fix mattered
- before that, month-down comparisons between March and April/May hedges could be misleading
- after the fix, the architecture above is more defensible
