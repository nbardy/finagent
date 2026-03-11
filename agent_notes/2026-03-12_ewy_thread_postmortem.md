# EWY Thread Postmortem
**Date:** 2026-03-12
**Scope:** What happened across the EWY hedge and call-sale thread, what changed, and what the thread-end state was intended to be.

## Final Intended State

At thread end, the intended EWY state was:

- keep the long EWY LEAP book
- keep the short-call income sleeve already sold
- remove the earlier short-dated crash hedge
- replace it with the later calendar hedge
- keep no extra resting EWY hedge orders

Thread-end EWY hedge target:

- short `Apr 10 2026 120P`
- long `Apr 24 2026 120P`
- filled size: `173x`
- average debit: about `1.4215`
- total debit: about `$24.6k`

Thread-end short-call sleeve already on:

- `-11x` `Mar 13 2026 151C`
- `-30x` `Apr 2 2026 150C`
- `-7x` `Apr 10 2026 145C`
- `-60x` `Apr 10 2026 150C`
- `-40x` `Apr 10 2026 170C`

## What Went Wrong

### 1. We initially bought the wrong shape

We entered a `Mar 20 135/121` crash hedge when the later discussion and modeling pointed more toward:

- a bottom around `Apr 2` to `Apr 10`
- then stabilization or rebound

That March spread was too short-dated and too crash-specific for the later thesis.

### 2. We layered hedges instead of replacing cleanly

The thread had a period where:

- the March crash hedge was still on
- the later April hedge was also added

That made the hedge book larger and noisier than intended.

### 3. We overshot size during live execution

The April vertical phase overshot target size because:

- partial fills were not reconciled tightly enough before remainder orders
- replacement vs additive intent was not enforced hard enough

### 4. We spent too much live time in research mode

The biggest process miss early in the thread was not model quality. It was:

- too much live-session analysis
- too much order iteration
- not enough prebuilt execution flow

## What Went Right

### 1. The low-bucket call-sale sleeve was the right move

Selling the low-bucket EWY calls against the LEAPs was one of the cleaner parts of the thread:

- it fit the book
- it funded de-risking
- it improved the chop and modest-down cases

### 2. We corrected the hedge shape

The thread moved from:

- short-dated crash spread

to:

- later-dated hedge structures
- then ultimately the `Apr 10 / Apr 24 120P` calendar

That was a better fit for the stated thesis.

### 3. We fixed major tooling gaps

The repo now has:

- stricter IBKR-first modeling paths
- cleaner `book / hedge / combined` outputs
- broader hedge-universe scans
- structure-specific pricing for calendars
- a clearer split between modeling and execution

## Main Decision Rules Learned

- Always decide whether a new hedge is additive or replacement before submitting anything.
- Always audit live positions and live open orders first.
- Never leave fill reconciliation implicit.
- Treat call-selling and downside hedging as separate sleeves.
- For this EWY book, the low bucket is the main income sleeve.
- Do not use a short-dated crash hedge for a later bottom-and-rebound thesis.

## Remaining Open Questions

- Whether the `173x` calendar should be held as-is or trimmed later is a separate portfolio-management question.
- The thread itself is functionally complete on workflow and skill organization.
