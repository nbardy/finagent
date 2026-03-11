# Execution Build Plan

## Goal

Turn the repo from:

- ad hoc pricers
- ad hoc JSON proposal files
- one-shot executor calls

into:

- pre-open fanout pricing
- stateful probing
- timed follow-through bulk orders
- reliable cancel/replace
- cover-aware allocation across all LEAP buckets

The target use case is intraday EWY options execution under time pressure.

Non-goal:

- a rigid always-on autopilot loop that hard-codes one execution pattern

The current direction should follow [TOOL_DESIGN_PHILOSOPHY.md](/Users/nicholasbardy/git/ikbr_trader/TOOL_DESIGN_PHILOSOPHY.md):

- composable primitives
- watch over blind sleep
- config-driven confidence bands
- agent-chained execution instead of hidden one-size-fits-all automation

## What Broke Today

1. Weekly execution was not automated enough.
2. We were generating probes, watching them manually, and repricing by hand.
3. We had no single stateful order manager for:
   - probe
   - wait
   - replace
   - bulk after fill
4. `portfolio.py` excludes the `2027 165C` because it only counts long calls with `dte > 365`.
5. Ghost orders from multiple IBKR client sessions were not easy to cleanly cancel.
6. We did not have a pre-open fanout planner that priced all candidate expiries/strikes in parallel.

## Current Useful Pieces

- [ibkr.py](/Users/nicholasbardy/git/ikbr_trader/ibkr.py)
- [executor.py](/Users/nicholasbardy/git/ikbr_trader/executor.py)
- [watch_orders.py](/Users/nicholasbardy/git/ikbr_trader/watch_orders.py)
- [planner_weekly.py](/Users/nicholasbardy/git/ikbr_trader/planner_weekly.py)
- [option_pricing/weekly.py](/Users/nicholasbardy/git/ikbr_trader/option_pricing/weekly.py)
- [option_pricing/probe.py](/Users/nicholasbardy/git/ikbr_trader/option_pricing/probe.py)
- [portfolio.py](/Users/nicholasbardy/git/ikbr_trader/portfolio.py)

These are enough to build the next layer instead of rewriting from scratch.

## Priority Order

1. Fix cover inventory correctness.
2. Add order-state and cancel/replace primitives.
3. Add a stateful probe manager.
4. Add pre-open fanout pricing.
5. Add staged bulk execution after first fill.
6. Add session plans and timers.

## Required Fixes

### 1. Fix LEAP inventory filtering

Problem:

- [portfolio.py](/Users/nicholasbardy/git/ikbr_trader/portfolio.py) only includes long calls with `dte > 365`.
- That drops the `165C Jan 2027` even though it is still a usable long-dated cover leg.

Change:

- Replace the hard-coded `dte > 365` check with configurable minimum long DTE.

Suggested config:

```json
{
  "strategy": {
    "min_long_dte_for_cover": 180
  }
}
```

Suggested function:

```python
def is_cover_eligible_option(contract_expiry: str, now: datetime, min_long_dte: int) -> bool:
    ...
```

### 2. Separate live shorts from pending sells

Problem:

- We need exact cover accounting:
  - live short calls
  - pending short sells
  - cover available by strike bucket

Suggested types:

```python
@dataclass(frozen=True)
class CoverBucket:
    strike: float
    expiry: str
    qty_total: int
    qty_available: int
    avg_cost: float

@dataclass(frozen=True)
class ShortExposure:
    expiry: str
    strike: float
    qty_live: int
    qty_pending: int
```

Suggested function:

```python
def compute_cover_state(
    long_calls: list[CoverBucket],
    live_shorts: list[ShortExposure],
    pending_shorts: list[ShortExposure],
) -> dict:
    ...
```

## New Core Modules

### 1. `order_state.py`

Purpose:

- one typed place for open orders, fills, replacements, and session state

Suggested types:

```python
@dataclass
class ManagedOrder:
    order_id: int | None
    symbol: str
    expiry: str
    strike: float
    right: str
    action: str
    qty: int
    limit_price: float
    tif: str
    status: str
    filled: int = 0
    remaining: int = 0
    order_ref: str = ""
    parent_plan_id: str = ""
    created_at: str = ""
    updated_at: str = ""

@dataclass
class FillRecord:
    order_id: int
    symbol: str
    expiry: str
    strike: float
    right: str
    side: str
    qty: int
    price: float
    timestamp: str

@dataclass
class ProbePlanState:
    plan_id: str
    symbol: str
    expiry: str
    strike: float
    right: str
    target_qty: int
    probe_prices: list[float]
    follow_qty: int
    follow_price: float | None
    fallback_price: float | None
    phase: str
```

Suggested file format:

- JSON in `state/orders/<plan_id>.json`

### 2. `order_manager.py`

Purpose:

- reliable IBKR actions:
  - place
  - cancel
  - replace
  - list by symbol
  - list by orderRef

Suggested functions:

```python
def place_limit_order(ib: IB, proposal: dict) -> ManagedOrder:
    ...

def cancel_order_by_id(ib: IB, order_id: int) -> None:
    ...

def cancel_orders_for_symbol(
    ib: IB,
    symbol: str,
    expiry: str | None = None,
    strike: float | None = None,
    right: str | None = None,
) -> list[int]:
    ...

def replace_limit_order(
    ib: IB,
    order_id: int,
    new_limit: float,
) -> ManagedOrder:
    ...

def list_open_orders(ib: IB, symbol: str | None = None) -> list[ManagedOrder]:
    ...
```

### 3. `probe_manager.py`

Purpose:

- run the full probe loop without manual babysitting

Behavior:

1. place initial probe ladder
2. sleep
3. check fills
4. if no fill, lower probe
5. if first fill appears, place follow-through bulk
6. optionally place delayed fallback order

Suggested config model:

```python
@dataclass(frozen=True)
class ProbeStep:
    qty: int
    price: float
    wait_seconds: int

@dataclass(frozen=True)
class FollowThroughPlan:
    trigger_fill_price: float | None
    qty: int
    price: float
    wait_seconds: int

@dataclass(frozen=True)
class ProbeExecutionPlan:
    symbol: str
    expiry: str
    strike: float
    right: str
    action: str
    steps: list[ProbeStep]
    follow_through: list[FollowThroughPlan]
    fallback_price: float | None
```

Suggested main entry point:

```python
def run_probe_plan(ib: IB, plan: ProbeExecutionPlan) -> ProbePlanState:
    ...
```

### 4. `fanout_pricer.py`

Purpose:

- price many expiries and strikes in one shot before open

Use case:

- build all candidate files for:
  - weekly
  - 2-week
  - pre-earnings
  - higher-strike diagonals on `165C`
  - higher-strike diagonals on `210C`

Suggested types:

```python
@dataclass(frozen=True)
class PricingTarget:
    symbol: str
    expiry: str
    strike_min: float
    strike_max: float
    qty_cap: int | None = None

@dataclass(frozen=True)
class CandidateSummary:
    expiry: str
    strike: float
    bid: float
    ask: float
    mid: float
    safe_qty: int
    delta: float
    prob_otm: float
    score: float
```

Suggested functions:

```python
def build_candidate_matrix(targets: list[PricingTarget]) -> list[CandidateSummary]:
    ...

def write_candidate_matrix(path: str, rows: list[CandidateSummary]) -> None:
    ...
```

## New Scripts

### Must build next

#### `cancel_symbol_orders.py`

Purpose:

- cancel all EWY option orders cleanly before placing a new session plan

CLI:

```bash
uv run python cancel_symbol_orders.py EWY --expiry 20260313
uv run python cancel_symbol_orders.py EWY --all-options
```

#### `replace_order.py`

Purpose:

- move a live limit in one command

CLI:

```bash
uv run python replace_order.py --order-id 125 --limit 4.05
```

#### `run_probe_plan.py`

Purpose:

- load a JSON plan and execute the probe loop automatically

CLI:

```bash
uv run python run_probe_plan.py --file session_probe_plan.json
```

#### `fanout_price.py`

Purpose:

- generate all candidate JSON files before the session

CLI:

```bash
uv run python fanout_price.py --symbol EWY --session-config preopen_ewy.json
```

#### `session_prepare.py`

Purpose:

- one command before market open:
  - sync portfolio
  - build cover state
  - fan out pricers
  - write ready-to-send plans

CLI:

```bash
uv run python session_prepare.py --symbol EWY
```

#### `session_execute.py`

Purpose:

- one command after first fill:
  - pick winning probe
  - send bulk
  - attach fallback repricing

CLI:

```bash
uv run python session_execute.py --plan state/orders/ewy_apr10_150.json
```

## Strategy-Specific Builders

### 1. `build_weekly_probe_plan.py`

Use for:

- `145/150` buckets
- short calls below earnings window

### 2. `build_diagonal_probe_plan.py`

Use for:

- `165C` longs with short calls in `175/180/185`
- `210C` longs with short calls in `210/215/220`

Suggested function:

```python
def build_diagonal_candidates(
    symbol: str,
    long_strike_floor: float,
    short_expiry: str,
    short_strike_min: float,
    short_strike_max: float,
) -> list[dict]:
    ...
```

## What We Should Support

### Weekly / short-dated

- fast probe ladder
- 2-5 minute wait windows
- bulk after first fill
- delayed fallback

### Pre-earnings window

- `1-3` expiries
- wider premium
- higher bulk size

### High-strike diagonal cover

- `165C` bucket:
  - short `175/180/185`
- `210C` bucket:
  - short `210/215/220/225`

These should be generated independently, not mashed into the same low-strike weekly planner.

## Concrete Next Build

### Phase 1

1. Fix [portfolio.py](/Users/nicholasbardy/git/ikbr_trader/portfolio.py)
2. Build `cancel_symbol_orders.py`
3. Build `replace_order.py`
4. Build `run_probe_plan.py`

### Phase 2

1. Build `fanout_price.py`
2. Build `session_prepare.py`
3. Build `session_execute.py`

### Phase 3

1. Build `build_diagonal_probe_plan.py`
2. Build `roller.py`
3. Build end-of-day cleanup / stale-order sweeper

## Immediate Functional Requirements

Before next session we should be able to do this:

```bash
uv run python session_prepare.py --symbol EWY
uv run python cancel_symbol_orders.py EWY --all-options
uv run python run_probe_plan.py --file state/session/ewy_apr10_150.json
```

Then after first fill:

```bash
uv run python session_execute.py --plan state/session/ewy_apr10_150.json
```

## Summary

The repo does not need another pricing model first.

It needs:

- correct cover accounting
- a stateful probe executor
- a clean cancel/replace tool
- pre-open fanout pricing
- separate builders for:
  - low-strike weekly cover
  - higher-strike diagonal cover

That is the shortest path to getting trades on faster next session.
