---
name: options-execution
description: Price, probe, submit, cancel, trim, and close IBKR option orders in the ikbr_trader repo. Use when the user wants to enter or exit a spread, calendar, diagonal, or overwrite order, verify live fills and resting orders, or avoid execution mistakes such as overbuying, crossing too far, or canceling from the wrong client id.
---

# Options Execution

Use this skill for live order-entry and fill management.

## Scope

This skill owns:

- live broker-state audit before sending orders
- probe orders
- BAG combo entry and exit
- wait and recheck loops
- remainder sizing
- cancellation from the correct client

## Workflow

1. Audit live positions and live open orders.
2. Confirm the target total size and whether the trade is additive or replacement.
3. Probe small first.
4. Wait about `50s`.
5. Recheck fills and still-working orders.
6. Send only the true remainder.
7. Cancel extra resting orders once the target size is reached.

## Guardrails

- For debit trades, lower price is better.
- For credit trades, higher price is better.
- Use `BAG` orders for spreads, calendars, and diagonals.
- Use actual fills as the best liquidity signal.
- Do not leave resting orders that can overshoot the intended position.
- In this repo, executor orders normally use client `2`.

## Main Tools

- `executor.py`
- `ibkr.py`
- `stock_tooling/price_probe.py`
- `stock_tooling/price_exit.py`
- `stock_tooling/price_calendar.py`
- `stock_tooling/price_spread.py`
