# IBKR Margin Metrics

## Core Definitions

Use these terms exactly:

- `TotalCashValue`: actual cash.
- `NetLiquidation`: account equity if positions were marked and liquidated at current value.
- `EquityWithLoanValue`: the borrowing base used for margin calculations.
- `AvailableFunds`: opening margin room. IBKR defines it as `Equity With Loan Value - Initial Margin`.
- `ExcessLiquidity`: liquidation buffer. IBKR defines it as `Equity With Loan Value - Maintenance Margin`.
- `BuyingPower`: leverage capacity, not cash. In a standard Reg T margin account it is commonly about `AvailableFunds * 4`.
- `InitMarginReq`: margin needed to open/hold positions under initial-margin rules.
- `MaintMarginReq`: margin needed to avoid liquidation under maintenance rules.
- `LookAheadAvailableFunds`: projected opening room after IBKR's next look-ahead margin run.
- `LookAheadExcessLiquidity`: projected liquidation buffer after the look-ahead run.
- `LookAheadMaintMarginReq`: projected maintenance requirement after the look-ahead run.
- `FullInitMarginReq` and `FullMaintMarginReq`: broader margin requirement figures that can be useful for cross-checking current values.
- `SMA`: Reg T memo balance; useful context, but not the main liquidation metric.
- `Cushion`: percent buffer before maintenance breach.

## Practical Interpretation

Translate account questions this way:

- "How much cash do I have?" -> `TotalCashValue`
- "How much can I buy without borrowing?" -> roughly `TotalCashValue`, minus whatever cash the user wants to preserve
- "How much can I open on margin?" -> `AvailableFunds` and `BuyingPower`, with house-margin caveats
- "How close am I to liquidation?" -> `ExcessLiquidity`, `MaintMarginReq`, and `Cushion`

Do not answer a cash question with `BuyingPower`.

If current and look-ahead values differ materially, mention both. That is often the cleanest warning that overnight or next-session margin treatment is tighter than the current snapshot suggests.

## Option-Heavy Account Warning

If `NetLiquidation` is much larger than `EquityWithLoanValue`, the account likely contains positions that help total equity but do not support borrowing nearly as much. Long option value is especially poor collateral for stock buying. Use that gap to explain why `BuyingPower` can feel small relative to headline net worth.

## Open-Order Exposure

When answering "how much more can we buy," include working orders:

- Stock: `remaining * limit_price`
- U.S. listed options: `remaining * limit_price * 100`
- Option combos (`BAG`): usually treat quoted combo price as per-spread and multiply by `100`

Keep buy exposure and sell-credit orders separate unless the user explicitly wants a netted estimate.
Do not present combo limit notional as if it were the true margin requirement; it is only a rough exposure proxy.

## Repo-Specific Unit Gotchas

This repo trades non-USD names and already documents critical unit rules in [`AGENTS.md`](../../../../AGENTS.md) and [`executor.py`](../../../../executor.py):

- GBP stocks on LSE/AIM are quoted in pence even though the currency field is `GBP`.
- JPY stocks on TSE are quoted in yen.
- `assert_price_units()` protects against obvious unit mistakes at execution time.

When describing pending order exposure, report the local-currency notional first if the order is quoted in subunits, then convert approximately to USD only if useful.

## Liquidation Risk Heuristic

For a hypothetical new stock buy of notional `N`:

1. Estimate immediate maintenance impact.
2. Subtract that from current `ExcessLiquidity`.
3. Stress the position with a drawdown.
4. Subtract the drawdown loss from remaining cushion.

Use a range, not a single number:

- Normal marginable stock: start with `25%` maintenance as a rough baseline.
- Higher-risk small-cap / foreign / concentrated stock: test `50%`.
- Non-marginable or house-restricted stock: test `100%`.

Example:

- Current `ExcessLiquidity = 140k`
- New stock buy `= 100k`
- If maintenance is `25%`, immediate cushion drop is `25k`
- If the basket then falls `30%`, another `30k` of cushion is gone
- Remaining cushion is about `85k`

At `50%` maintenance, the same path leaves about `60k`.
At `100%` maintenance, the same path leaves only about `10k`.

This is why `BuyingPower` is not the safe number to use for risk decisions.

## Live Pull Pattern

Use a short live query from the repo root:

```bash
uv run python - <<'PY'
from ibkr import connect, get_account_summary, get_open_orders

tags = {
    'TotalCashValue', 'NetLiquidation', 'EquityWithLoanValue',
    'AvailableFunds', 'BuyingPower', 'InitMarginReq',
    'MaintMarginReq', 'ExcessLiquidity', 'SMA', 'Cushion'
}

with connect(client_id=99, market_data_type=3, readonly=True) as ib:
    metrics = get_account_summary(ib, tags=tags)
    orders = get_open_orders(ib)
    for row in metrics:
        print(vars(row))
    for order in orders:
        print(vars(order))
PY
```

Adjust `client_id` as needed.

## Official IBKR References

Use official sources for definitions:

- Current Available Funds: <https://www.interactivebrokers.com/campus/glossary-terms/current-available-funds/>
- Buying Power: <https://www.interactivebrokers.com/campus/glossary-terms/buying-power/>
- Current Excess Liquidity: <https://www.interactivebrokers.com/campus/glossary-terms/current-excess-liquidity/>
- Equity with Loan Value: <https://www.interactivebrokers.com/campus/glossary-terms/equity-with-loan-value/>
- Current Maintenance Margin: <https://www.interactivebrokers.com/campus/glossary-terms/current-maintenance-margin/>
- Reg T Margin: <https://www.interactivebrokers.com/campus/glossary-terms/reg-t-margin/>
- IBKR account margin notes: <https://www.interactivebrokers.com/en/accounts/configuring-your-account.php>
