---
name: ikbr-margin
description: Explain IBKR margin, cash, buying power, available funds, excess liquidity, maintenance margin, and liquidation risk in the ikbr_trader repo. Use when a user asks how much stock they can buy, whether they are using margin, how open orders affect capacity, or how a crash would impact liquidation risk.
---

# IBKR Margin

## Overview

Use live IBKR account data from this repo to explain stock-buying capacity and liquidation risk in plain language. Prefer account summary tags and live open orders over stale JSON snapshots.

## Workflow

1. Pull live account summary with [`ibkr.py`](../../../ibkr.py) helpers.
2. Pull live open orders with `reqAllOpenOrders()` semantics so client-ID isolation does not hide working orders.
3. Separate actual cash from margin-opening room and from liquidation cushion.
4. Convert working buy orders into real notional by contract type and currency units.
5. Explain the result using IBKR's own definitions before giving portfolio-specific judgment.

## Pull Live Data

Use [`ibkr.py`](../../../ibkr.py) and prefer tags:

- `TotalCashValue`
- `NetLiquidation`
- `EquityWithLoanValue`
- `AvailableFunds`
- `BuyingPower`
- `InitMarginReq`
- `MaintMarginReq`
- `ExcessLiquidity`
- `SMA`
- `Cushion`
- `GrossPositionValue`
- `LookAheadAvailableFunds`
- `LookAheadExcessLiquidity`
- `LookAheadMaintMarginReq`
- `FullInitMarginReq`
- `FullMaintMarginReq`

Read [`references/ibkr-margin-metrics.md`](./references/ibkr-margin-metrics.md) for the meaning of each field and the repo-specific interpretation rules.

## Interpret The Numbers

- Treat `TotalCashValue` as actual cash.
- Treat `AvailableFunds` as opening room for new positions, not cash.
- Treat `BuyingPower` as leverage capacity derived from margin rules, not a separate asset pool.
- Treat `ExcessLiquidity` as the real liquidation buffer. If it goes negative, liquidation risk is immediate.
- Treat `EquityWithLoanValue` as the borrowing base. If it is far below `NetLiquidation`, the account likely has positions that help net equity but do not help borrowing capacity much.

## Handle Open Orders Correctly

- Include current working buy orders before answering "how much more can we buy."
- For stock limit orders, approximate pending notional as `remaining * limit_price`.
- For listed option orders and option combos, usually multiply by the contract multiplier, typically `100`.
- For sell orders, separate credit-generating orders from buy orders; do not net them casually unless the user explicitly wants a net cash-flow view.
- Use account-wide reads because different IBKR client IDs cannot always see each other's working orders without `reqAllOpenOrders()`.

## Respect Currency Units

- GBP stocks may be quoted in pence even when the contract currency is `GBP`.
- JPY stocks are quoted in yen.
- This repo already encodes those guardrails in [`executor.py`](../../../executor.py); do not restate pending order exposure in the wrong unit.

## Explain Liquidation Risk

- Start from `ExcessLiquidity`, not `BuyingPower`.
- A new stock purchase reduces future cushion by its maintenance requirement, which may be much higher than textbook `25%` for volatile, foreign, concentrated, or non-marginable names.
- Losses then reduce cushion roughly dollar-for-dollar.
- IBKR can liquidate in real time when maintenance is breached; do not describe this as a normal grace-period margin call.
- Give a range analysis for new buys: normal marginable stock, elevated house margin, and worst-case non-marginable treatment.

## Avoid Common Misreads

- Do not answer a cash question with `BuyingPower`.
- Do not ignore live working buy orders when estimating new capacity.
- Do not assume long option market value supports stock borrowing the same way cash or marginable stock does.
- Do not assume `25%` maintenance for volatile, foreign, concentrated, or OTC names.
- Do not treat option combo limit price as exact future margin impact; use it only as a rough pending-notional proxy.

## Response Style

- Use the live numbers first.
- State clearly whether the user is asking about cash, opening room, or liquidation room.
- If the account is option-heavy, call out that `NetLiquidation` can look large while borrowing capacity stays much smaller.
- If the user asks "how much margin can I use comfortably," answer with conservative, reasonable, and aggressive ranges tied to current `ExcessLiquidity`.
- Keep recommendations practical: conservative, reasonable, aggressive.
