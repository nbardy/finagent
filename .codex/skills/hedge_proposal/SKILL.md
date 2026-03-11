---
name: hedge_proposal
description: Create executable hedge proposals in this repo after a hedge vehicle is chosen. Use when the user wants live pricing, probe orders, BAG combo orders, entry ladders, close files, or broker-ready JSON under orders/{YYYY-MM-DD}. This is the proposal skill, not hedge modeling.
---

# Hedge Proposal

Use this skill after the hedge structure is selected and the user wants executable orders.

## Scope

This skill owns:

- live repricing from IBKR
- probe files
- full entry ladders
- BAG combo construction for spreads, calendars, and diagonals
- close and trim files
- broker-ready JSON in `orders/{YYYY-MM-DD}/`

This skill does not decide the macro thesis or rank the structure universe. If the user is still choosing vehicles, use `hedge_modeling`.
Use `options-execution` when the user wants to actually send, cancel, or rework orders live.

## Default Workflow

1. Confirm the intended hedge vehicle, size, and whether it replaces or adds to an existing hedge.
2. Pull fresh IBKR quotes.
3. Build the executable order in the repo's JSON schema.
4. For multi-leg structures, use a single `BAG` order unless the user explicitly wants legging risk.
5. If execution quality matters, write:
   - a probe file
   - a full file
   - optionally a close file
6. Save all artifacts under `orders/{YYYY-MM-DD}/`.

## Strict Execution Rules

- Use live IBKR pricing.
- Do not use Yahoo or disk snapshots to set executable limits.
- Do not silently substitute stale prices, guessed IV, or guessed mids.
- Do not split a spread, calendar, or diagonal into naked legs unless the user explicitly approves legging risk.
- For exits, prefer closing the same combo as a `BAG`.

## Main Tools

- [`ibkr.py`](../../../ibkr.py)
  Use for live quote and contract work.
- [`executor.py`](../../../executor.py)
  This is the target JSON schema and the submission path.
- [`stock_tooling/price_probe.py`](../../../stock_tooling/price_probe.py)
  Use for single-instrument or simple quote-probe generation.
- [`stock_tooling/price_exit.py`](../../../stock_tooling/price_exit.py)
  Use for close pricing when applicable.

## Order Construction Rules

- Write manual proposals to `orders/{YYYY-MM-DD}/descriptive_name.json`.
- For spreads, calendars, and diagonals:
  - `contract.secType` should be `BAG`
  - include both legs in one contract
  - use one overall `BUY` or `SELL` action on the combo
- Use tranche ladders when the user wants staged execution.
- If the user wants scratch exits, write separate close files at or above entry.

## Minimum Proposal Set

For any hedge the user is likely to work actively, prefer to generate:

- `*_probe.json`
- `*_live.json` or `*_open_ready.json`
- `*_close.json`

If the hedge replaces an existing one, say that clearly in the description and do not double-count the intended size.

## File Placement

- executable orders: `orders/{YYYY-MM-DD}/descriptive_name.json`
- if needed, supporting pricing notes belong in `analysis/{YYYY-MM-DD}/`, not mixed into the order file

## Response Style

- State the exact structure, size, and dates.
- State whether the file is probe, full entry, trim, or close.
- State whether the order is paired as a combo.
- If pricing is stale or incomplete, stop and say so instead of emitting a fake executable limit.
