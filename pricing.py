"""
Backward-compatible pricing facade.

Prefer importing from the `option_pricing` package for new code.
"""

from option_pricing.black_scholes import (
    bs_call,
    bs_delta_call,
    bs_delta_put,
    bs_gamma,
    bs_put,
    implied_volatility_from_price,
    option_delta,
    option_price,
)
from option_pricing.limits import (
    TICK_SIZE,
    LimitPriceResult,
    build_exit_tranches,
    limit_price,
    limit_price_put,
    recommend_limit,
    tranche_ladder,
)
from option_pricing.simulation import mc_option_pnl


def price_option(
    symbol: str,
    spot: float,
    strike: float,
    dte_days: int,
    sigma: float,
    bid: float,
    ask: float,
    right: str = "C",
    action: str = "BUY",
    r: float = 0.045,
    dividend_yield: float = 0.0,
) -> None:
    time_to_expiry = dte_days / 365.0
    result = limit_price(
        S=spot,
        K=strike,
        T=time_to_expiry,
        r=r,
        sigma=sigma,
        bid=bid,
        ask=ask,
        action=action,
        right=right,
        dividend_yield=dividend_yield,
    )
    theoretical_value = option_price(
        spot=spot,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=r,
        volatility=sigma,
        right=right,
        dividend_yield=dividend_yield,
    )
    delta = option_delta(
        spot=spot,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=r,
        volatility=sigma,
        right=right,
        dividend_yield=dividend_yield,
    )
    prob_profit, exp_pnl, p05 = mc_option_pnl(
        spot,
        strike,
        time_to_expiry,
        sigma,
        result.suggested_limit,
        is_long=(action.upper() == "BUY"),
        is_call=(right.upper() == "C"),
    )

    print(f"\n{'='*55}")
    print(f"  {symbol} {strike}{right}  DTE={dte_days}  σ={sigma:.2f}  {action}")
    print(f"{'='*55}")
    print(f"  Spot:       ${spot:.2f}")
    print(f"  Theo Value: ${theoretical_value:.2f}")
    print(f"  Market:     [{bid:.2f} x {ask:.2f}]  mid=${result.mid_price:.2f}")
    print(f"  Edge:       ${result.edge_vs_mid:+.2f}  (mid - TV)")
    print(f"  Spread:     {result.spread_pct*100:.1f}%")
    print(f"  Delta:      {delta:.3f}")
    print(f"  Gamma:      {bs_gamma(spot, strike, time_to_expiry, r, sigma, dividend_yield):.4f}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Limit:      ${result.suggested_limit:.2f}")
    print(f"  Prob Profit: {prob_profit*100:.1f}%")
    print(f"  E[PnL]:     ${exp_pnl:.2f}")
    print(f"  Tail (p05): ${p05:.2f}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    print("--- AAOI LEAP Example ---")
    price_option("AAOI", 45.0, 50.0, 365, 0.55, 5.00, 7.50, "C", "BUY")

    print("--- EWY Short Call Example ---")
    price_option("EWY", 58.0, 62.0, 30, 0.25, 0.30, 0.55, "C", "SELL")
