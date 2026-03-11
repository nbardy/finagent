# EWY Call Overwrite State

**Date:** 2026-03-12  
**Scope:** Final practical state of the EWY call-overwrite book after the full thread.

## Long EWY LEAP Inventory

- `+18x EWY 145C Jan 21 2028`
- `+90x EWY 150C Jan 21 2028`
- `+40x EWY 165C Jan 15 2027`
- `+110x EWY 210C Jan 21 2028`

Total long EWY LEAP calls: `258`

## Short Calls Sold On Top

- `-11x EWY Mar 13 2026 151C`
- `-30x EWY Apr 2 2026 150C`
- `-7x EWY Apr 10 2026 145C`
- `-60x EWY Apr 10 2026 150C`
- `-40x EWY Apr 10 2026 170C`

Total short calls on the book: `148`

## Coverage By Bucket

### Low bucket: `145C / 150C`

This bucket is fully spoken for.

- `145C` bucket covered
- `150C` bucket covered

This is the main income sleeve and it is already loaded.

### Mid bucket: `165C`

This bucket is also now fully covered.

Final structure:

- long `40x Jan 15 2027 165C`
- short `40x Apr 10 2026 170C`

This sleeve was discovered by live probing, not by trusting the displayed ask.

Observed execution:

- early probe fills around `0.91-0.92`
- later bulk fills at `0.95`, `0.90`, `0.85`, and one final better-than-limit fill
- full-sleeve average around `0.917`

Gross sleeve credit:

- about `$3.67k`

### High bucket: `210C`

This bucket is still untouched.

- `110x Jan 21 2028 210C`
- no short calls sold against it yet

## Main Lessons

### 1. The low bucket is the real overwrite engine

The `145/150` longs are where repeated short-call selling actually pays.

### 2. The `165C` sleeve is worthwhile but modest

It makes sense, but it is supplemental carry, not the core engine.

### 3. The `210C` sleeve is optional convex inventory

Do not force a bad overwrite just to say everything is covered.

## Canonical Related Notes

- [agent_1_mar_11th_dump.md](/Users/nicholasbardy/git/ikbr_trader/agent_notes/agent_1_mar_11th_dump.md)
- [2026-03-11_final_market_open_plan.md](/Users/nicholasbardy/git/ikbr_trader/agent_notes/2026-03-11_final_market_open_plan.md)
- [2026-03-12_ewy_thread_postmortem.md](/Users/nicholasbardy/git/ikbr_trader/agent_notes/2026-03-12_ewy_thread_postmortem.md)
