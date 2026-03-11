---
name: options-execution
description: Price, probe, submit, cancel, trim, and close IBKR option orders in the ikbr_trader repo. Use when the user wants to enter or exit a spread, calendar, diagonal, or overwrite order, verify live fills and resting orders, or avoid execution mistakes such as overbuying, crossing too far, or canceling from the wrong client id.
---

# Options Execution

Use this skill for live order-entry and fill management.

Use this skill when the user wants to send, cancel, trim, or close live option orders.
Use `hedge_proposal` to create the files first when needed.

## Owns

- live broker-state audit
- probe and remainder logic
- BAG combo entry and exit
- cancellation and trim handling

## Guardrails

- for debit trades, lower price is better
- for credit trades, higher price is better
- use `BAG` orders for spreads, calendars, and diagonals
- use actual fills as the best liquidity signal
- do not leave resting orders that can overshoot target size
- executor orders normally use client `2`

## Main Tools

- `executor.py`
- `ibkr.py`
- `stock_tooling/price_probe.py`
- `stock_tooling/price_exit.py`
