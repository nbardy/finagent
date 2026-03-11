# Remaining Work And Playbook

**Date:** 2026-03-12  
**Scope:** What is still unfinished from the EWY thread, and how the next execution session should run.

## What Is Done

- low-bucket EWY call sales are on
- `165 -> Apr 10 170C` diagonal sleeve is on
- tooling philosophy is now documented
- watcher/probe tooling now emits structured guidance

## What Is Still Not Done

### 1. The `210C` bucket is still uncovered

No short calls are on the `110x Jan 2028 210C` sleeve.

That is the main strategic decision still open on the call-income side.

### 2. Replace/cancel primitives are still missing

We still need:

- `replace_order.py`
- `cancel_symbol_orders.py`

These are the highest-value execution helpers still missing.

### 3. There is still no thin orchestration runner

We intentionally did **not** build a rigid automation loop.

But a light runner is still worth building if it:

- reads a plan file
- executes a probe
- calls `watch`
- reports suggested next actions

That should stay advisory and composable, not magical.

## Practical Playbook

For the next thin option line:

1. run model audit
2. generate a probe file
3. send the probe
4. run `watch_orders.py` with quote context
5. read the structured confidence output
6. bulk, reprice, or stop

This is now the intended control loop.

## Recommended Next Build Items

### Highest ROI

- `replace_order.py`
- `cancel_symbol_orders.py`

### Next after that

- a small plan interpreter on top of the existing primitives

Not a full autopilot. Just enough to reduce repetitive glue work.

## Final Read

There is not much conceptual work left in this thread.

The main open items are:

- whether to monetize the `210C` bucket now
- whether to build the replace/cancel helpers next

Everything else is mostly captured and organized.
