---
name: selling-options
description: Select and size short-call overwrite trades in the ikbr_trader repo. Use when the user wants to sell calls against LEAPs or stock, choose strikes and expiries, respect covered buckets, compare income sleeves, or avoid over-encumbering the same long calls.
---

# Selling Options

Use this skill for covered-call and PMCC-style overwrite decisions.

Use this skill for covered-call and PMCC overwrite selection, not downside hedge ranking.

## Owns

- short-call strike and expiry selection
- cover-bucket logic
- safe cover sizing
- income-sleeve vs hedge-sleeve separation

## Guardrails

- Do not double-encumber the same cover bucket.
- Distinguish low-bucket overwrites from higher-strike diagonals.
- Separate income logic from downside hedge logic.
- If another agent already sold the sleeve, say the bucket is full instead of proposing more size.

## Main Scripts

- `stock_tooling/planner_weekly.py`
- `ibkr.py`
- `stock_tooling/audit_option_models.py`
