---
name: ikbr-margin
description: Explain IBKR margin, cash, buying power, available funds, excess liquidity, maintenance margin, and liquidation risk in the ikbr_trader repo. Use when a user asks how much stock they can buy, whether they are using margin, how open orders affect capacity, or how a crash would impact liquidation risk.
---

# IBKR Margin

Use this skill to interpret cash, margin room, and liquidation risk from live IBKR account data.

## Workflow

1. Pull live account summary from [`ibkr.py`](../../../ibkr.py).
2. Pull live open orders with account-wide visibility.
3. Separate cash, opening room, and liquidation cushion.
4. Include working orders in exposure.
5. Explain the result in plain language.

Read [`ibkr-margin-metrics.md`](./references/ibkr-margin-metrics.md) for the field definitions and repo-specific interpretation rules.
