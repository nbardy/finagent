# Agent 1 Dump — March 11, 2026

## Purpose

This is the working dump of what we think about the EWY book, what we staged, what went wrong intraday, what we believe now, and what to build next.

This is intentionally opinionated. It is not just a changelog.

## Current EWY Position Map

Long LEAP calls:

- `+18x EWY 145C Jan 21 2028`
- `+90x EWY 150C Jan 21 2028`
- `+40x EWY 165C Jan 15 2027`
- `+110x EWY 210C Jan 21 2028`

Short calls already on:

- `-11x EWY 151C Mar 13 2026`

Cover state from `config/portfolio_state.json` after fixing the cover filter:

- `145C`: `7` available
- `150C`: `90` available
- `165C`: `40` available
- `210C`: `110` available
- total unencumbered long calls: `247`

Important interpretation:

- The `145/150` bucket is the main covered-call inventory.
- The `165` bucket is optional diagonal inventory.
- The `210` bucket is optional upside inventory and should not be forced into bad short-call sales.

## What Is Staged For Next Open

Queued in IBKR for `2026-03-11 09:30:00 US/Eastern`:

- `SELL 7x EWY Apr 10 2026 145C @ 4.90`
- `SELL 20x EWY Apr 10 2026 150C @ 4.00`
- `SELL 20x EWY Apr 10 2026 150C @ 3.80`
- `SELL 20x EWY Apr 10 2026 150C @ 3.60`
- `SELL 10x EWY Apr 2 2026 150C @ 3.30`
- `SELL 10x EWY Apr 2 2026 150C @ 3.20`
- `SELL 10x EWY Apr 2 2026 150C @ 3.10`

This is the full low-bucket allocation:

- `67` contracts on `Apr 10`
- `30` contracts on `Apr 2`
- total `97`

Why this shape:

- `Apr 10` is the better premium / earnings-buffer balance.
- `Apr 2` is the shorter-dated supplement for faster theta and more open-gap fill odds.
- `Apr 17` was removed because it is too close to the late-April Samsung earnings window.

Canonical saved file:

- `orders/2026-03-11/ewy_next_open_call_sales.json`

## What We Believe About The Book

### 1. Short-dated weeklys were too dead

The `Mar 13` weeklys were too decayed and too wide for meaningful size.

What happened:

- we sold only `11x 151C`
- execution was poor
- the model was not the problem
- the real problem was thin liquidity plus collapsing lottery premium

Opinion:

- Stop fighting `Mar 13`.
- It is not where the edge is now.
- The better trade moved out to `Apr 2` and `Apr 10`.

### 2. The low bucket is the real income engine

The `145/150` long calls are the part of the book where short-call selling actually makes sense.

Why:

- strikes are close enough to collect real premium
- cover is clean
- assignment risk is manageable if monitored
- expiries can be chosen to stay ahead of earnings

Opinion:

- This should be the default sleeve we monetize.
- If we do nothing else, monetize this sleeve well.

### 3. The `165C` bucket is usable, but secondary

This bucket can support diagonals like `170C` or `175C` shorts.

Recent modeled examples:

- `Apr 10 170C`: around `0.35 x 3.00`, mid `1.68`
- `Apr 2 170C`: around `0.20 x 1.75`, mid `0.97`

Opinion:

- This sleeve is fine to use opportunistically.
- It is not the first thing to automate.
- It should be a second income layer after the `145/150` bucket is staged cleanly.

### 4. The `210C` bucket should mostly be left alone for now

Near-dated and medium-dated calls up there were generally too thin and too wide.

Recent modeled examples:

- `Apr 10 210C`: around `0.00 x 0.70`
- `Oct 16 210C`: around `3.80 x 6.00`
- `Oct 16 215C`: around `3.40 x 6.10`

Important opinion:

- Do not force short calls on the `210C` bucket just because the inventory exists.
- Leave these open unless the rally or IV makes higher-strike shorts actually pay.

## On Selling A 6-Month `180C`

Question asked: should we sell something like a `6 month out 180C` against the `210C` longs?

Opinion: not against the `210C` bucket.

Why:

- short strike `180` is below long strike `210`
- that is not the clean PMCC shape we want
- it introduces a bad diagonal profile between `180` and `210`
- if assigned, it creates operational mess

If we want to sell `180C`, it belongs against the `165C` bucket, not the `210C` bucket.

If we want to monetize the `210C` bucket directly, use short strikes at or above that region:

- `210C`
- `215C`
- `220C`

Even then, only do it if the premium is actually there.

## Put Spreads As Hedge Sleeve

Put spreads do mix with the short-call sales, but they should be treated as a separate hedge sleeve.

How to think about it:

- short calls = income + upside cap
- put spreads = downside protection that costs premium
- together they make the book more range-bound

Opinion:

- This mix makes sense if the goal is lower variance and crash protection.
- It does not make sense if the goal is full upside recovery.
- Put spreads should not be mechanically paired one-for-one with short calls.
- They should be sized as a portfolio hedge, not as a decorative add-on.

## What Went Wrong Intraday

We took too long to go from idea to executable orders.

Main reasons:

- the repo was not ready for same-session probe -> reprice -> bulk execution
- weekly planning was still half prototype, half manual
- order cleanup across IBKR sessions was messy
- we spent live market time building missing plumbing

Opinion:

- We did not fail because the pricing model was too weak.
- We failed because execution orchestration was too manual.
- The missing edge is automation and session prep, not variance-gamma or a fancier stochastic process.

## Model Opinions

### Black-Scholes / BSM

Still the correct default anchor here.

Use:

- spot
- IV from market
- rate
- dividend adjustment when possible

Opinion:

- For EWY short-call staging, BSM is good enough.
- The gap between fair value and real fills is mostly spread / liquidity, not model form.

### Heston / VG / Merton / Markov / etc.

Opinion:

- Not the first priority for this repo right now.
- These are lower ROI than better execution plumbing.
- Do not waste live-session time calibrating complex models when the book is illiquid and the problem is fill logic.

### Open-gap modeling

This *is* worth doing.

We should continue to scenario-price:

- weak open
- flat open
- hot open
- panic open

That helps us stage better pre-open orders.

## Tooling We Have

Useful now:

- `portfolio.py`
- `planner_weekly.py`
- `option_pricing/weekly.py`
- `option_pricing/probe.py`
- `executor.py`
- `watch_orders.py`
- `ibkr.py`

Useful outputs:

- `config/portfolio_state.json`
- `orders/{date}/...`
- `analysis/{date}/...`

## Tooling We Still Need

Highest-value missing tools:

### 1. `cancel_symbol_orders.py`

Need one command to clean all EWY option orders by:

- symbol
- expiry
- strike
- right
- orderRef prefix

### 2. `replace_order.py`

Need one safe cancel/replace path for:

- one order
- a whole ladder
- a whole symbol/expiry group

### 3. `run_probe_plan.py`

This is the biggest missing piece.

It should:

- submit a probe ladder
- sleep
- check fills
- reprice if needed
- bulk after a successful probe
- stop if the market is dead

### 4. `fanout_price.py`

Before open, price all candidates in parallel:

- `Apr 2`
- `Apr 10`
- `Apr 17`
- maybe one diagonal expiry
- low bucket, 165 bucket, 210 bucket

### 5. session planner / executor split

Need explicit pre-open workflow:

- `session_prepare.py`
- `session_execute.py`

Opinion:

- This is what would have prevented the lost session.

## What To Do Next

### Immediate

- Let the staged `Apr 2` / `Apr 10` low-bucket orders work at open.
- Do not add more complexity before we see how the open behaves.

### Soon

- Build `cancel_symbol_orders.py`
- Build `replace_order.py`
- Build `run_probe_plan.py`

### Optional next sleeve

After the low bucket is under control:

- add `165C` diagonal staging
- probably `Apr 10 170C` first

### Not now

- do not force the `210C` bucket
- do not spend time on complex model upgrades first

## Bottom-Line Opinions

1. The `145/150` bucket is where we should be selling calls.
2. `Apr 2` and `Apr 10` are the right expiries right now.
3. `Apr 17` is too close to the Samsung earnings window.
4. The `165C` bucket can support diagonals, but that is secondary.
5. The `210C` bucket should mostly be left alone until premium improves.
6. Put spreads are a good hedge sleeve, but separate from the call-income sleeve.
7. The main repo weakness is execution orchestration, not pricing theory.
8. The highest ROI build now is a stateful probe manager.
