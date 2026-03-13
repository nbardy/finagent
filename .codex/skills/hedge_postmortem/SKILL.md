---
name: hedge_postmortem
description: Compare realized hedge outcomes to the intended thesis and payoff shape in this repo. Use when the user wants to understand why a hedge did or did not work, separate thesis misses from structure or execution misses, or turn a live thread into durable modeling and process rules.
---

# Hedge Postmortem

Use this skill after a hedge thread, live drawdown, or modeling miss when the main question is what happened and what should change.

Use `hedge_modeling` when the main task is still choosing or ranking forward-looking structures.

## Owns

- thesis versus realized-path comparison
- structure-miss versus process-miss analysis
- realized `book / hedge / combined` outcome review
- durable rule updates for skills, AGENTS, or scripts

## Workflow

1. Reconstruct the final intended state at the time:
   - structure
   - size
   - capital deployed
   - stated `objective`
2. Reconstruct the realized path:
   - spot move timing
   - vol or term-structure changes when relevant
   - fills, trims, replacements, and leftover orders
3. Separate the miss:
   - thesis miss
   - payoff-shape miss
   - path-model miss
   - execution or process miss
4. Compare realized `book`, `hedge`, `combined`, and `return_on_hedge_capital` to what the thread expected.
5. Write the smallest durable artifact:
   - `agent_notes/{date}_..._postmortem.md` for workflow or thread learnings
   - `analysis/{date}/...json` for supporting scenario or structure comparisons
   - AGENTS or skill patches only for rules worth keeping
6. End with concrete `keep`, `change`, and `open_questions` items.

## Required Postmortem Contract

- `final_intended_state`
- `realized_state`
- `intended_payoff_shape`
- `realized_path`
- `model_miss`
- `process_miss`
- `keep`
- `change`
- `open_questions`

## Guardrails

- use live fills, positions, and open orders when available
- do not rewrite the earlier thesis to match later price action
- keep thesis mistakes separate from execution mistakes
- if fallback market data is used, label it and keep conclusions proportional
