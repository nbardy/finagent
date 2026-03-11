from __future__ import annotations

import math

from scipy.optimize import brentq


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _sanitize_volatility(volatility: float) -> float:
    return max(float(volatility), 1e-6)


def _d1(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    sigma = _sanitize_volatility(volatility)
    return (
        math.log(spot / strike)
        + (risk_free_rate - dividend_yield + 0.5 * sigma**2) * time_to_expiry
    ) / (sigma * math.sqrt(time_to_expiry))


def _d2(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    sigma = _sanitize_volatility(volatility)
    return _d1(spot, strike, time_to_expiry, risk_free_rate, sigma, dividend_yield) - sigma * math.sqrt(
        time_to_expiry
    )


def bs_call(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    if time_to_expiry <= 0:
        return max(0.0, spot - strike)
    d1 = _d1(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)
    d2 = _d2(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)
    return spot * math.exp(-dividend_yield * time_to_expiry) * norm_cdf(d1) - strike * math.exp(
        -risk_free_rate * time_to_expiry
    ) * norm_cdf(d2)


def bs_put(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    if time_to_expiry <= 0:
        return max(0.0, strike - spot)
    d1 = _d1(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)
    d2 = _d2(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)
    return strike * math.exp(-risk_free_rate * time_to_expiry) * norm_cdf(-d2) - spot * math.exp(
        -dividend_yield * time_to_expiry
    ) * norm_cdf(-d1)


def option_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    right: str = "C",
    dividend_yield: float = 0.0,
) -> float:
    if right.upper() == "C":
        return bs_call(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)
    return bs_put(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)


def bs_delta_call(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    if time_to_expiry <= 0:
        return 1.0 if spot > strike else 0.0
    d1 = _d1(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)
    return math.exp(-dividend_yield * time_to_expiry) * norm_cdf(d1)


def bs_delta_put(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    if time_to_expiry <= 0:
        return -1.0 if spot < strike else 0.0
    d1 = _d1(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)
    return math.exp(-dividend_yield * time_to_expiry) * (norm_cdf(d1) - 1.0)


def option_delta(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    right: str = "C",
    dividend_yield: float = 0.0,
) -> float:
    if right.upper() == "C":
        return bs_delta_call(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)
    return bs_delta_put(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)


def bs_gamma(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    if time_to_expiry <= 0 or spot <= 0:
        return 0.0
    sigma = _sanitize_volatility(volatility)
    d1 = _d1(spot, strike, time_to_expiry, risk_free_rate, sigma, dividend_yield)
    return (
        math.exp(-dividend_yield * time_to_expiry)
        * norm_pdf(d1)
        / (spot * sigma * math.sqrt(time_to_expiry))
    )


def implied_volatility_from_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    market_price: float,
    right: str = "C",
    dividend_yield: float = 0.0,
    lower: float = 0.01,
    upper: float = 3.0,
) -> float | None:
    if market_price <= 0 or time_to_expiry <= 0:
        return None

    def objective(volatility: float) -> float:
        return option_price(
            spot=spot,
            strike=strike,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=volatility,
            right=right,
            dividend_yield=dividend_yield,
        ) - market_price

    try:
        return brentq(objective, lower, upper)
    except ValueError:
        return None
