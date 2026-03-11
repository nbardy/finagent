# Margin And Account Capacity
**Recorded:** 2026-03-12 03:56
**Scope:** IBKR account interpretation, cash vs buying power, liquidation risk, and how photonics orders fit inside current account capacity.

## Main Interpretation

The core confusion resolved in this thread was:

- `cash` is not the same thing as `available funds`
- `buying power` is not another cash bucket
- `excess liquidity` is the actual liquidation buffer
- `gross position value` is heavily distorted upward by the options book

The user's preferred leverage lens was:

- `max(0, -TotalCashValue) / StockMarketValue`

That is not IBKR's liquidation lens, but it is a useful intuitive debt-to-stocks lens.

## Key Account Concepts Used

- `TotalCashValue`: actual cash
- `AvailableFunds`: opening room for new positions under initial margin
- `BuyingPower`: margin-derived capacity number
- `ExcessLiquidity`: liquidation cushion
- `NetLiquidation`: total net marked account value
- `StockMarketValue`: marked value of stocks only

## Account Read At End Of Thread

After the final after-hours `AXTI` buy, live IBKR showed:

- `TotalCashValue`: `58,772.73 USD`
- `AvailableFunds`: `157,079.53 USD`
- `ExcessLiquidity`: `159,541.82 USD`
- `BuyingPower`: `628,318.13 USD`
- `NetLiquidation`: `846,504.80 USD`

Interpretation:

- The account still has positive cash.
- There is no negative-cash stock margin loan yet.
- The account remains comfortable from a cushion standpoint, but the live photonics order stack is already meaningful.

## Important Conclusions Reached

- The account did still have cash; the earlier larger cash number partly reflected option-spread credits.
- The user was not currently on negative-cash margin.
- A large portion of account size metrics reflects the options book rather than stock deployed capital.
- Any answer about "how much more can we buy" has to include the live resting photonics orders.

## Liquidation Framing

The right risk metric for a new stock sleeve is not `BuyingPower`.
It is:

- current `ExcessLiquidity`
- minus maintenance requirement on the new stock
- minus mark-to-market loss if the sleeve falls

Key practical point:

- IBKR can liquidate in real time if maintenance is breached
- there is no reliable grace-period margin-call assumption

## Resting Order Effect

By the end of the thread, live resting photonics orders were roughly:

- `USD 79k` equivalent

That means future stock deployment should not be discussed as if no staged demand already exists.

## Outcome

The account still had cash after the live `TSEM` and `AXTI` after-hours buys.
The photonics build remained feasible, but the active order stack already represented a substantial staged deployment plan rather than an empty slate.
