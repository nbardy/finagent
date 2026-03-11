# Tooling Design And Watch Primitives

**Date:** 2026-03-12  
**Scope:** What changed in the execution-tooling layer and what philosophy now governs it.

## Summary

The repo now has an explicit design philosophy:

- tools should be composable primitives
- `watch` is a first-class concept
- agents should chain primitives based on context
- the repo should not hard-code one universal execution loop

Canonical design doc:

- [TOOL_DESIGN_PHILOSOPHY.md](/Users/nicholasbardy/git/ikbr_trader/TOOL_DESIGN_PHILOSOPHY.md)

## What Was Added

### 1. Config-driven watch rules

New file:

- [config/watch_rules.json](/Users/nicholasbardy/git/ikbr_trader/config/watch_rules.json)

Purpose:

- define liquidity bands
- recommend poll windows
- define observation windows
- attach confidence scores and next-action thresholds

These are heuristics, not hard law.

### 2. Reusable watch-assessment module

New file:

- [stock_tooling/watch_rules.py](/Users/nicholasbardy/git/ikbr_trader/stock_tooling/watch_rules.py)

Purpose:

- classify a market as `tight`, `tradable`, `wide`, or `very_wide`
- compute confidence from quote quality and fills
- emit a suggested action:
  - `keep_watching`
  - `bulk_ready`
  - `reprice_candidate`
  - `do_not_force`

### 3. Structured watcher

Updated file:

- [stock_tooling/watch_orders.py](/Users/nicholasbardy/git/ikbr_trader/stock_tooling/watch_orders.py)

New behavior:

- optional quote pull while watching
- machine-readable JSON snapshots
- optional full history output to `analysis/{date}/...`
- structured watch assessment on each poll

This is now the correct primitive for:

- poll
- observe
- assess

It is not an execution bot.

### 4. Probe files now carry watch guidance

Updated file:

- [stock_tooling/price_probe.py](/Users/nicholasbardy/git/ikbr_trader/stock_tooling/price_probe.py)

New behavior:

- proposal JSON now includes `watch_guidance`
- initial poll window and confidence are attached to the probe itself

## What This Means Operationally

The intended chain is now:

1. model or audit
2. generate a probe proposal
3. execute the probe
4. watch with structured output
5. decide whether to bulk, reprice, or stop

The repo is closer to “agent-usable control surface” and farther from “manual snippets plus guesswork.”

## What Is Still Missing

Still not built:

- `replace_order.py`
- `cancel_symbol_orders.py`
- a plan interpreter like `run_probe_plan.py`

Those should remain thin orchestration tools built on top of:

- `price_probe.py`
- `watch_orders.py`
- `executor.py`
- `ibkr.py`

## Opinion

This is the right direction.

The problem in the EWY thread was not mainly model sophistication. It was:

- too much live-session improvisation
- too little reusable execution plumbing

This tooling update addresses that directly.
