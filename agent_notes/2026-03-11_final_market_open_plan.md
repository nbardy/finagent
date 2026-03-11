# Final Market Open Plan
**Date:** 2026-03-11
**Scope:** EWY book, using the reconciled views from `agent_1_mar_11th_dump.md` and `agent_2_mar_11th_dump.md`, plus the actual live IBKR open-order state.

## Final Decision

For the Wednesday, March 11, 2026 US market open:

1. Let the existing EWY low-bucket call-sale ladder work.
2. Let the existing EWY Mar 20 crash hedge work.
3. Do not add any new low-bucket overwrite before the open.
4. Do not touch the `210C` bucket before the open.
5. Only consider a new `165 -> Apr 10 170C` diagonal sleeve after we see how the open behaves and after confirming fills on the existing orders.

This is the final open stance.

## Live EWY Orders To Leave Working

### Downside hedge sleeve
Canonical file:
- `orders/2026-03-11/ewy_urgent_repriced_open_ready.json`

Live broker orders:
- Buy `14x` EWY Mar 20 2026 `135/121` put spread @ `7.20`
- Buy `14x` EWY Mar 20 2026 `135/121` put spread @ `7.25`
- Buy `14x` EWY Mar 20 2026 `135/121` put spread @ `7.25`

Interpretation:
- This is the fast crash sleeve.
- It is already aggressive enough for the open.
- Do not replace it pre-open.

### Low-bucket call-sale sleeve
Canonical file:
- `orders/2026-03-11/ewy_next_open_call_sales.json`

Live broker orders:
- Sell `7x` EWY Apr 10 2026 `145C` @ `4.90`
- Sell `20x` EWY Apr 10 2026 `150C` @ `4.00`
- Sell `20x` EWY Apr 10 2026 `150C` @ `3.80`
- Sell `20x` EWY Apr 10 2026 `150C` @ `3.60`
- Sell `10x` EWY Apr 2 2026 `150C` @ `3.30`
- Sell `10x` EWY Apr 2 2026 `150C` @ `3.20`
- Sell `10x` EWY Apr 2 2026 `150C` @ `3.10`

Interpretation:
- This is the full clean `145/150` bucket allocation.
- It should be treated as the canonical low-bucket income sleeve.
- Do not double-file any more `145/150` short calls.

## Inventory Rules

From `config/portfolio_state.json`:
- `145C` available: `7`
- `150C` available: `90`
- `165C` available: `40`
- `210C` available: `110`

Practical meaning:
- `145/150` bucket is already fully committed by the live open orders.
- `165C` bucket remains the clean additive diagonal sleeve.
- `210C` bucket remains optional convex upside inventory and should not be forced into a bad overwrite.

## What We Are Explicitly Not Doing

### 1. No new low-bucket overwrite
Do not submit:
- `orders/2026-03-11/ewy_broader_overwrite_apr17_150c_x60.json`
- `orders/2026-03-11/ewy_broader_financed_apr17_overlay_x60_x49.json`

Reason:
- both rely on additional low-bucket short calls
- the low bucket is already full
- they would conflict with the staged open ladder

### 2. No forced trade on the `210C` bucket
Do not sell a lower-strike medium-dated short call like a `180C` against the `210C` longs.

Reason:
- wrong diagonal shape
- effectively bearish between the short and long strikes
- avoidable assignment and management risk

### 3. No extra complexity before seeing the open
Do not add another new hedge structure before the first wave of fills and tape behavior are visible.

Reason:
- both note sets agree the biggest failure was execution sprawl
- the correct response is fewer pre-open moving parts, not more

## Open Sequence

### Before 9:30 AM US/Eastern
- Do not modify the live EWY orders unless there is a clear broker mismatch.
- Treat the two canonical files above as the only valid EWY open files.

### First 5 minutes after the open
- Check which of the put-spread tranches fill.
- Check which of the low-bucket call-sale tranches fill.
- Do not add a second low-bucket ladder.

### After initial fills
If the low-bucket ladder is partially or substantially filled and the market is still unstable:
- keep the Mar 20 crash sleeve on
- consider whether the broader protection need is already sufficiently funded by the short-call credits

If the low-bucket ladder is filling cleanly and more income is still desired:
- the only clean next sleeve is `Apr 10 170C` against the `40x 165C` bucket

## Broader Hedge Conclusion

The corrected broader-coverage modeling says:
- the current Mar 20 `135/121` hedge is good for a fast next-week downside move
- it is not a broad 1-month hedge
- funded de-risking through short calls improved the month-down and choppy-month cases more than another small bought-put sleeve

That means the open plan should be:
- keep the crash sleeve
- keep the low-bucket call-sales
- only add the `165 -> 170` diagonal later if needed

## If We Need One More Trade After The Open

The preferred next additive trade is:
- stage `Apr 10 2026 170C x40` against the `165C` bucket

This is preferred over:
- touching the `210C` bucket
- adding another low-bucket overwrite
- adding another buy-only small put sleeve immediately

## Final Operational Rule

At the open, optimize for:
- fill verification
- avoiding duplicate cover use
- not introducing a new conflicting sleeve before the current one is confirmed

The correct default is to **let the current EWY open plan work first**.
