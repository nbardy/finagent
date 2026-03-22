"""
Heston stochastic volatility model for option pricing.

Why Heston over BS for LEAPs:
  BS assumes constant vol. On a 681-DTE option, vol will mean-revert
  toward its long-run level. Heston captures this with 5 parameters:

    v0    - current instantaneous variance (IV² from market)
    theta - long-run variance (vol² the market reverts to)
    kappa - mean reversion speed (how fast vol returns to theta)
    xi    - vol of vol (how much variance itself fluctuates)
    rho   - correlation between stock and vol (usually negative:
            stocks drop → vol spikes, the "leverage effect")

  For selling LEAPs, Heston typically gives HIGHER prices than BS
  because it accounts for the vol smile and fat tails. This means
  your BS-based limits might be leaving money on the table.

Implementation: semi-closed form via characteristic function and
numerical integration (Carr-Madan / Lewis approach).
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

from scipy.integrate import quad


@dataclass(frozen=True)
class HestonParams:
    """
    Heston model parameters — ALL required, no silent defaults.

    v0    - current instantaneous variance (IV² from market)
    theta - long-run variance (vol² the market reverts to)
    kappa - mean reversion speed (how fast vol returns to theta)
    xi    - vol of vol (how much variance itself fluctuates)
    rho   - correlation between stock and vol (usually negative)
    """
    v0: float
    theta: float
    kappa: float
    xi: float
    rho: float

    @classmethod
    def from_ivs(
        cls,
        current_iv: float,
        long_run_vol: float,
        kappa: float,
        xi: float,
        rho: float,
    ) -> HestonParams:
        """
        Construct from observable implied volatilities.
        All parameters required — no silent defaults.
        """
        return cls(
            v0=current_iv ** 2,
            theta=long_run_vol ** 2,
            kappa=kappa,
            xi=xi,
            rho=rho,
        )

    @property
    def feller_satisfied(self) -> bool:
        """Feller condition: 2*kappa*theta > xi². Ensures vol stays positive."""
        return 2.0 * self.kappa * self.theta > self.xi ** 2


def _heston_characteristic_function_cached(
    u: complex,
    log_spot: float,
    T: float,
    r: float,
    q: float,
    params: HestonParams,
) -> complex:
    """
    Heston characteristic function φ(u) for log-spot.

    Uses the "good" formulation (Albrecher et al.) that avoids
    branch-cut discontinuities in the complex logarithm.
    """
    v0 = params.v0
    theta = params.theta
    kappa = params.kappa
    xi = params.xi
    rho = params.rho

    # Precompute the scalar pieces that are reused by both integrands.
    u_i = 1j * u
    rho_xi = rho * xi
    xi_sq = xi * xi
    common = kappa - rho_xi * u_i
    d = cmath.sqrt(common * common + xi_sq * (u_i + u * u))

    g = (common - d) / (common + d)

    # C and D functions
    exp_neg_dT = cmath.exp(-d * T)
    common_minus_d = common - d
    one_minus_g = 1.0 - g
    one_minus_g_exp_neg_dT = 1.0 - g * exp_neg_dT

    C = (r - q) * u_i * T + (kappa * theta / xi_sq) * (
        common_minus_d * T
        - 2.0 * cmath.log(one_minus_g_exp_neg_dT / one_minus_g)
    )

    D = (common_minus_d / xi_sq) * (
        (1.0 - exp_neg_dT) / one_minus_g_exp_neg_dT
    )

    return cmath.exp(C + D * v0 + u_i * log_spot)


def _heston_characteristic_function(
    u: complex,
    spot: float,
    strike: float,
    T: float,
    r: float,
    q: float,
    params: HestonParams,
) -> complex:
    """Backward-compatible wrapper used by existing callers inside this module."""
    return _heston_characteristic_function_cached(u, math.log(spot), T, r, q, params)


def heston_call(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: HestonParams,
    dividend_yield: float = 0.0,
) -> float:
    """
    Heston model call price via numerical integration.

    Uses the Carr-Madan formulation with Gauss-Kronrod quadrature.
    """
    if T <= 0:
        return max(0.0, spot - strike)

    q = dividend_yield
    log_spot = math.log(spot)
    log_K = math.log(strike)
    discount = math.exp(-r * T)
    cf_neg_i = _heston_characteristic_function_cached(-1j, log_spot, T, r, q, params)

    # Numerical integration
    # Split into two probability integrals for better numerics
    def integrand_P1(u: float) -> float:
        phi = _heston_characteristic_function_cached(u - 1j, log_spot, T, r, q, params)
        return (
            cmath.exp(-1j * u * log_K) * phi / (1j * u * cf_neg_i)
        ).real

    def integrand_P2(u: float) -> float:
        phi = _heston_characteristic_function_cached(u, log_spot, T, r, q, params)
        return (cmath.exp(-1j * u * log_K) * phi / (1j * u)).real

    P1_integral, _ = quad(integrand_P1, 1e-8, 200, limit=500)
    P2_integral, _ = quad(integrand_P2, 1e-8, 200, limit=500)

    P1 = 0.5 + P1_integral / math.pi
    P2 = 0.5 + P2_integral / math.pi

    call_price = spot * math.exp(-q * T) * P1 - strike * discount * P2

    return max(call_price, 0.0)


def heston_put(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: HestonParams,
    dividend_yield: float = 0.0,
) -> float:
    """Heston put price via put-call parity."""
    if T <= 0:
        return max(0.0, strike - spot)
    call = heston_call(spot, strike, T, r, params, dividend_yield)
    q = dividend_yield
    return call - spot * math.exp(-q * T) + strike * math.exp(-r * T)


def heston_price(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: HestonParams,
    right: str = "C",
    dividend_yield: float = 0.0,
) -> float:
    """Dispatch to call or put."""
    if right.upper() == "C":
        return heston_call(spot, strike, T, r, params, dividend_yield)
    return heston_put(spot, strike, T, r, params, dividend_yield)


def compare_models(
    spot: float,
    strike: float,
    T: float,
    r: float,
    bs_vol: float,
    heston_params: HestonParams,
    right: str = "C",
    dividend_yield: float = 0.0,
    bid: float = 0.0,
    ask: float = 0.0,
) -> dict:
    """
    Compare BS vs Heston pricing for a single option.
    Returns a dict with both model prices and the difference.
    """
    from .black_scholes import option_price as bs_price

    bs = bs_price(spot, strike, T, r, bs_vol, right, dividend_yield)
    heston = heston_price(spot, strike, T, r, heston_params, right, dividend_yield)
    mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0

    return {
        "strike": strike,
        "right": right,
        "dte": int(T * 365),
        "bs_price": round(bs, 4),
        "heston_price": round(heston, 4),
        "difference": round(heston - bs, 4),
        "pct_difference": round((heston - bs) / bs * 100, 2) if bs > 0 else 0.0,
        "market_mid": round(mid, 4),
        "bs_vs_mid": round(mid - bs, 4) if mid > 0 else None,
        "heston_vs_mid": round(mid - heston, 4) if mid > 0 else None,
    }
