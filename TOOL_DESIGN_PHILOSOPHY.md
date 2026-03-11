# Tool Design Philosophy

## Goal

Build **flexible trading primitives** that an agent can chain, not a rigid "autopilot bot" that pretends one loop works for every option book.

The target workflow is:

- model
- generate proposal
- execute small size
- watch
- reassess
- reprice or scale

The agent harness should decide how to compose those steps based on context. The repo should provide the pieces.

## Non-Goals

- No hidden "sleep and retry forever" runner.
- No single hard-coded execution loop for all symbols, expiries, or liquidity regimes.
- No opaque price-selection logic that silently chooses a number without showing the quote quality and model context.
- No silent fallback from live broker data to stale public data for execution decisions.

## Core Principles

### 1. Primitives Over Monoliths

Prefer small tools with clear boundaries:

- `model` or `audit`
- `proposal`
- `execute`
- `watch`
- `cancel`
- `replace`
- `summarize`

The agent can chain them into a playbook. The tool itself should not assume the whole playbook.

### 2. Watch Over Sleep

`sleep` is only an implementation detail. The user-facing concept is `watch`.

`watch` means:

- poll broker state for a bounded window
- capture fills, open orders, positions, and live quote context
- return a structured assessment

The output should answer:

- did anything fill?
- how wide is the market?
- how confident are we in the current executable zone?
- should we keep watching, bulk, reprice, or stop forcing it?

### 3. Configurable Heuristics, Not Frozen Math

Low-liquidity names and wide spreads require longer watch windows and lower confidence. Tight liquid markets justify faster follow-through.

That logic should live in config-driven rule bands, not scattered hard-coded `if spread > X` branches across scripts.

Rules are advisory, not sovereign. The agent may override them.

### 4. Agent-Chained, Human-Auditable

The right control surface is:

- tool outputs structured artifacts
- agent reads them
- agent decides next step

That keeps the loop fast without burying all judgment inside a single automation script.

### 5. File-Mediated State

All important outputs should be saved:

- proposals -> `orders/{YYYY-MM-DD}/`
- watch snapshots / assessments -> `analysis/{YYYY-MM-DD}/`
- persistent config -> `config/`

If the agent or broker session dies, the reasoning and proposed next action should still exist on disk.

### 6. Separate Observation From Action

Watching should not place orders.

Proposal generation should not transmit orders.

Execution should not decide pricing policy.

This separation makes the system composable and safer under time pressure.

### 7. Model Bands, Not Model Worship

For pricing and audit we want:

- `BSM`
- `Heston`
- `VG`
- `MJD`

But execution should still anchor to:

- actual quote quality
- observed probe fills
- live broker state

Rich models help define a band. They do not override the reality of a thin book.

### 8. Prefer IBKR For Execution Context

IBKR is the source of truth for:

- positions
- open orders
- fills
- executable quotes

Bulk public-chain data can still be useful for ranking or scenario scans, but execution tooling should fail loud when broker-side market data is not usable.

## Desired Tooling Surface

### Modeling

- `audit_option_models.py`
- `price_spread.py`
- `planner_weekly.py`

### Proposal Generation

- `price_probe.py`
- future `replace_order.py` / `cancel_symbol_orders.py`

### Observation

- `watch_orders.py`

Observation tools should return structured guidance, not only terminal text.

### Execution

- `executor.py`

Execution should stay dumb:

- read file
- submit orders
- report status

## What "Good" Looks Like

For a thin option line, the agent should be able to do:

1. run model audit
2. build a small probe ladder
3. execute the probe
4. run `watch` for a configured window
5. inspect structured confidence / liquidity output
6. decide whether to bulk, reprice, or stop

The repo should make that fast. It should not force a single universal strategy.

## Immediate Design Consequences

- `watch_orders.py` should emit machine-readable snapshots and recommendations.
- Probe tools should emit initial watch guidance, not just prices.
- Watch timing should come from configurable rule bands tied to spread/liquidity quality.
- Future "playbook" runners should compose primitives and configs, not encode one magic execution loop.
