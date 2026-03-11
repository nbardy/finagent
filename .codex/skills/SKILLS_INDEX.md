# Skills Index

Use `.codex/skills/` as the single source of truth for repo-local skills in this repo.

## Recommended Hierarchy

### Leaf Skills

- `options-pricing`
  Price and audit single legs, verticals, and calendars with IBKR-first data and the repo's pricing models.

- `options-execution`
  Probe, fill, cancel, trim, and close option orders safely in IBKR.

- `selling-options`
  Choose overwrite and PMCC short-call strikes, bucket usage, and safe cover sizing for the live book.

### Domain Skills

- `hedge_modeling`
  Build macro scenarios, run EV, rank hedge vehicles, and choose the right structure.

- `hedge_proposal`
  Turn the chosen hedge into executable order proposals and close files.

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
- Keep live broker-state auditing in both `hedge_proposal` and `options-execution`.
