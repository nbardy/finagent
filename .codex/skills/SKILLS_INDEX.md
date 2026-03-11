# Skills Index

Use `.codex/skills/` as the single source of truth for repo-local skills in this repo.
Read [`references/source_playbook.md`](./references/source_playbook.md) for shared internet/source policy.

## Recommended Hierarchy

### Leaf Skills

- `options-pricing`
  Fair-value audit for one chosen structure.

- `options-execution`
  Live order-entry and fill management.

- `selling-options`
  Covered-call and PMCC overwrite selection.

### Domain Skills

- `hedge_modeling`
  Macro scenarios, EV, stress tests, and hedge ranking.

- `hedge_proposal`
  Turn the chosen hedge into executable entry, trim, and close files.

- `ikbr-margin`
  Explain account capacity, excess liquidity, and liquidation risk using live IBKR account data.

## Trigger Guidance

- If the user asks which hedge makes sense: start with `hedge_modeling`.
- If the user asks for executable hedge files: use `hedge_proposal`.
- If the user asks how to price a leg, spread, or calendar: use `options-pricing`.
- If the user asks to probe, cancel, or manage fills: use `options-execution`.
- If the user asks what calls to sell or how much overwrite is safe: use `selling-options`.
- If the user asks about cash, buying power, or liquidation risk: use `ikbr-margin`.

## Design Rules

- Higher-layer skills may reference lower-layer skills.
- Lower-layer skills should not reference higher-layer skills.
- Do not combine modeling and execution unless the user wants both in the same turn.
- Keep repo conventions in code and AGENTS, not duplicated in every skill.
