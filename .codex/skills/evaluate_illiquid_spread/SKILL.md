# Evaluate Illiquid Spread

## Intent
Use this skill when asked to check the price, PNL, or exit strategy for a multi-leg option spread, especially deep, illiquid LEAPS where the bid-ask spread is extremely wide.

## Context
When market makers widen their quotes on illiquid options, the mathematical midpoint can shift dramatically without any actual trading occurring. This can cause massive phantom "losses" or "gains" in the account's Net Liquidation value.

You must not blindly trust the broker's portfolio `marketValue` or `unrealizedPNL` for these assets. You must empirically price the spread to determine its true theoretical fair value before proposing limit orders.

## Execution Steps

1.  **Fetch Live Bid/Ask:**
    - Do not rely solely on the portfolio's last marked price.
    - Write a short script using `ib.reqTickers()` to pull the current `bid`, `ask`, and `mid` for all legs of the spread.

2.  **Run Quantitative Models:**
    - Use the repo's internal pricing models (`option_pricing/calibrate.py`).
    - Pass the current option chain data into `calibrate_all()` to fit parameters for Heston, Variance Gamma, and Merton Jump Diffusion models.
    - Calculate the theoretical fair value of the specific spread using these models.

3.  **Fetch IBKR's Proprietary Model Price:**
    - Use `ib.reqTickers()` and wait for the `modelGreeks` attribute to populate.
    - Extract `modelGreeks.optPrice` for each leg to see how the broker's own internal engine values the options, ignoring the current wide quotes.

4.  **Advise on Limit Price:**
    - Compare the theoretical fair value (from step 2 & 3) against the pure bid-ask midpoint (from step 1).
    - If the midpoint is significantly higher than the fair value, explain to the user that the portfolio mark is artificially inflated.
    - Recommend a patient limit order (e.g., using the `Adaptive` algo) priced closer to the fair value, rather than blindly hitting the bid or the inflated midpoint.

## Output Structure
- State the live bid/ask spreads for the individual legs.
- Present the theoretical model prices for the overall spread.
- Explain the discrepancy (if any) between the market midpoint and the fair value.
- Propose a limit price strategy to exit the position without paying the spread penalty.