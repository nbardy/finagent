# EWY 210C Bucket Strategy

**Date:** 2026-03-12  
**Scope:** What to do with the `Jan 2028 210C` bucket and why it was left untouched.

## Current Bucket

- `+110x EWY Jan 21 2028 210C`
- no short calls sold against it yet

This is the last uncovered EWY LEAP sleeve.

## What We Ruled Out

### Do not sell lower-strike shorts like `180C` against it

Reason:

- short strike below long strike is the wrong diagonal shape
- it makes the sleeve effectively bearish between the strikes
- if assigned, it can create messy short-stock handling

Conclusion:

- `180C` against `210C` is not the clean PMCC-style structure we want

## What Did Make Sense

The first acceptable sleeve was:

- `Jul 17 2026 220C`

Second choice:

- `Jul 17 2026 215C`

These are above the long strike and preserve the correct defined-risk shape.

## Why It Was Left Unsold

Earlier in the thread, short-dated and medium-dated calls up there were:

- too thin
- too wide
- too uncertain to force

Later, the better July quotes became:

- `Jul 17 215C`: around `1.45 x 2.30`
- `Jul 17 220C`: around `1.40 x 1.90`

That made the sleeve potentially worth doing, but it still was not urgent compared with:

- filling the low bucket
- finishing the `165 -> 170` sleeve

## Return Math

At `110x` size:

- `Jul 17 220C @ 1.65` is about `$18.2k` gross
- `Jul 17 215C @ 1.875` is about `$20.6k` gross

That is meaningful because the bucket is large.

Over several cycles, this sleeve can plausibly add up to tens of thousands gross. It is not trivial.

## Recommendation

If monetizing this bucket:

1. use `Jul 17 220C` first
2. probe it before selling full size
3. do not use a lower-strike short just because the premium looks bigger

## Positioning Opinion

This bucket should be treated as optional convex upside inventory.

Sell against it only when:

- the premium is truly there
- the upside cap is acceptable
- we are choosing carry over maximum convexity

Otherwise, leave it open.
