---
name: hedge_proposal
description: Create executable hedge proposals in this repo after a hedge vehicle is chosen. Use when the user wants live pricing, probe orders, BAG combo orders, entry ladders, close files, or broker-ready JSON under orders/{YYYY-MM-DD}. This is the proposal skill, not hedge modeling.
---

# Hedge Proposal

Use this skill after the hedge structure is selected and the user wants executable orders.

Use `options-execution` when the user wants live order management after the files exist.
Read [`source_playbook.md`](../references/source_playbook.md) for source policy.

## Owns

- live repricing from IBKR
- executable entry files
- BAG combo construction for spreads, calendars, and diagonals
- close and trim files
- broker-ready JSON in `orders/{YYYY-MM-DD}/`

This skill does not choose the macro thesis. Use `hedge_modeling` first if the structure is still unsettled.

## Workflow

1. Confirm the intended hedge vehicle, size, and whether it replaces or adds to an existing hedge.
2. Pull fresh IBKR quotes.
3. Build the executable order in the repo's JSON schema.
4. For multi-leg structures, use one `BAG` order unless the user explicitly approves legging risk.
5. Emit the smallest useful set of files:
   - entry
   - probe if needed
   - close or trim if likely
6. Save all artifacts under `orders/{YYYY-MM-DD}/`.

## Main Scripts

- [`ibkr.py`](../../../ibkr.py)
- [`executor.py`](../../../executor.py)
- [`stock_tooling/price_probe.py`](../../../stock_tooling/price_probe.py)
- [`stock_tooling/price_exit.py`](../../../stock_tooling/price_exit.py)

## Required Proposal Contract

- write executable files to `orders/{YYYY-MM-DD}/`
- for spreads, calendars, and diagonals use `secType: BAG`
- state whether the file is `add`, `replace`, `trim`, or `close`
- do not double-count intended size when replacing an existing hedge

## Guardrails

- live IBKR pricing only for executable limits
- no Yahoo or disk snapshots for live orders
- no silent substitution of stale prices, guessed IV, or guessed mids
- prefer closing the same combo as a `BAG`
