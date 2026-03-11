---
name: selling-options
description: Select and size short-call overwrite trades in the ikbr_trader repo. Use when the user wants to sell calls against LEAPs or stock, choose strikes and expiries, respect covered buckets, compare income sleeves, or avoid over-encumbering the same long calls.
---

# Selling Options

Use this skill for covered-call and PMCC-style overwrite decisions.

## Scope

This skill owns:

- strike and expiry selection for short calls
- bucket logic for which long calls can cover which short calls
- safe cover sizing
- separating income sleeves from hedge sleeves
- deciding whether a short-call sleeve is already full

## Workflow

1. Audit the live long-call and short-call book.
2. Group the book into cover buckets.
3. Confirm how much clean cover remains.
4. Rank candidate short calls by premium, distance, and practical assignment risk.
5. If the user wants to file the order, hand off to `options-execution`.

## Guardrails

- Do not double-encumber the same cover bucket.
- Distinguish low-bucket overwrites from higher-strike diagonals.
- Separate income logic from downside hedge logic.
- If another agent already sold the sleeve, say the bucket is full instead of proposing more size.

## Main Tools

- `stock_tooling/planner_weekly.py`
- `ibkr.py`
- `stock_tooling/audit_option_models.py`
