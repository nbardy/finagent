# Skill Architecture And Cleanup
**Recorded:** 2026-03-12 03:56
**Scope:** What skills were created or refined, what they cover, what still needs to be added, and what remains uncommitted.

## Current Source Of Truth

The skill layout is now unified under:

- `.codex/skills/`

The old repo-local `skills/` tree is no longer the source of truth.
It now contains only a breadcrumb index pointing back to `.codex/skills/`.

## Current Skill Set

Tracked skills under `.codex/skills/`:

- `hedge_modeling`
- `hedge_proposal`
- `ikbr-margin`
- `options-pricing`
- `options-execution`
- `selling-options`

Each of these also has `agents/openai.yaml`.

## What Was Done In This Thread

### Created / refined materially

- `ikbr-margin`
  - explains cash, buying power, available funds, excess liquidity, maintenance margin, and liquidation risk
  - includes reference material for IBKR field meanings

### Audited / reviewed structurally

- `hedge_modeling`
- `hedge_proposal`
- `options-pricing`
- `options-execution`
- `selling-options`

The split now makes sense:

- model the hedge
- turn it into a proposal
- price structures
- execute/manage fills
- handle overwrite-specific logic

## What The Skills Encode Well

- repo-specific file placement
- IBKR-first workflow
- modeling vs proposal vs execution separation
- open-order audit rules
- combo execution guardrails
- margin interpretation rules

## What Still Requires Live Broker Or Web Checks

Skills reduce repeated explanation work, but they do not remove the need for live verification.

Still requires live checks:

- current prices
- current fills and open orders
- current exchange session status
- current IBKR order-type behavior
- current ADR/depositary details if relevant
- current FX conversion

## Missing Skill

The main missing skill exposed by this thread is a stock-side accumulation / execution skill.

That missing skill would cover:

- laddered stock accumulation
- crash bids vs fill-seeking bids
- after-hours stock execution
- ADR vs ordinary-share routing
- foreign-market session quirks
- pending notional across multiple live stock orders

## Cleanup Status

Good news:

- the main skill bodies are now tracked in git
- the earlier duplicate skill-body problem appears resolved
- the current skill bodies are reasonably lean and not obviously bloated

Remaining cleanup items:

- add the missing stock accumulation skill
- optionally normalize naming style across underscore and hyphen usage
- optionally remove the `skills/` breadcrumb later if it becomes unnecessary

## Uncommitted Items

At the time of writing, the main outstanding uncommitted items were the topic notes under `agent_notes/`.

That means the skill tree itself is in better shape than the thread notes.
