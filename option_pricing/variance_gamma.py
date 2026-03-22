"""
Variance Gamma (VG) option pricing model.

The VG process is a pure jump Lévy process obtained by evaluating
Brownian motion with drift at a random time given by a Gamma process.
It captures skewness (theta) and excess kurtosis (nu) that BS cannot.

Why VG for LEAPs:
  - Pure jump process: no diffusion component, all moves are jumps.
    This matches empirical return distributions better than BS.
  - Three parameters beyond r give independent control over:
      sigma - volatility of the Brownian subordinand
      theta - drift of the Brownian subordinand (skewness control;
              negative theta → left-skewed returns, matching equity markets)
      nu    - variance rate of the Gamma subordinator (kurtosis control;
              larger nu → heavier tails, more extreme moves)
  - Semi-analytical pricing via characteristic function + numerical
    integration (Gil-Pelaez inversion), same approach as Heston.

Reference: Madan, Carr, Chang (1998) "The Variance Gamma Process
and Option Pricing," European Finance Review 2, 79-105.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

from scipy.integrate import quad


@dataclass(frozen=True)
class VGParams:
    """
    Variance Gamma model parameters.

    sigma: volatility of the Brownian motion component
    theta: drift of the Brownian motion (controls skewness)
           Negative theta → negative skew (equity-like)
    nu:    variance rate of the Gamma time change (controls kurtosis)
           Larger nu → heavier tails
    """
    sigma: float
    theta: float
    nu: float

    @classmethod
    def from_market(
        cls,
        atm_vol: float,
        skew_strength: float,
        tail_weight: float,
    ) -> VGParams:
        """
        Construct from market-observable quantities.
        All parameters required — no silent defaults.

        atm_vol:        ATM implied vol (used as sigma)
        skew_strength:  theta parameter; negative for equity-like skew
        tail_weight:    nu parameter; higher = fatter tails
        """
        return cls(
            sigma=atm_vol,
            theta=skew_strength,
            nu=tail_weight,
        )

    @property
    def omega(self) -> float:
        """
        Convexity correction (martingale adjustment).

        omega = (1/nu) * ln(1 - theta*nu - 0.5*sigma²*nu)

        This ensures E[S_T] = S_0 * exp(rT) under the risk-neutral measure.
        The argument of the log must be positive for the model to be valid.
        """
        arg = 1.0 - self.theta * self.nu - 0.5 * self.sigma ** 2 * self.nu
        if arg <= 0:
            raise ValueError(
                f"VG parameters invalid: 1 - theta*nu - 0.5*sigma²*nu = {arg:.4f} <= 0. "
                f"Reduce |theta| or nu, or increase sigma."
            )
        return math.log(arg) / self.nu


def _vg_characteristic_function(
    u: complex,
    spot: float,
    T: float,
    r: float,
    q: float,
    params: VGParams,
) -> complex:
    """
    VG characteristic function φ(u) for log-spot at time T.

    φ_VG(u) = exp(i*u*(ln(S) + (r - q + omega)*T))
              * (1 - i*u*theta*nu + 0.5*sigma²*nu*u²)^(-T/nu)

    The last factor is the characteristic function of the VG increment
    raised to the power T/nu (self-decomposability of the Gamma subordinator).
    """
    return _vg_characteristic_function_fast(
        u=u,
        log_forward=math.log(spot) + (r - q + params.omega) * T,
        theta_nu=params.theta * params.nu,
        sigma2_nu=(params.sigma ** 2) * params.nu,
        time_over_nu=T / params.nu,
    )


def _vg_characteristic_function_fast(
    u: complex,
    *,
    log_forward: float,
    theta_nu: float,
    sigma2_nu: float,
    time_over_nu: float,
) -> complex:
    """
    Internal VG characteristic function with precomputed invariants.

    This is the hot path used by pricing/integration routines.
    """
    inner = 1.0 - 1j * u * theta_nu + 0.5 * sigma2_nu * u * u
    return cmath.exp(1j * u * log_forward - time_over_nu * cmath.log(inner))


def vg_call(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: VGParams,
    dividend_yield: float = 0.0,
) -> float:
    """
    VG call price via Gil-Pelaez inversion of the characteristic function.

    C = exp(-rT) * [F*P1 - K*P2]

    where P1, P2 are risk-neutral probabilities obtained by inverting
    the characteristic function (same structure as Heston).
    """
    if T <= 0:
        return max(0.0, spot - strike)

    q = dividend_yield
    log_K = math.log(strike)
    log_forward = math.log(spot) + (r - q + params.omega) * T
    theta_nu = params.theta * params.nu
    sigma2_nu = (params.sigma ** 2) * params.nu
    time_over_nu = T / params.nu
    phi_neg_i = _vg_characteristic_function_fast(
        -1j,
        log_forward=log_forward,
        theta_nu=theta_nu,
        sigma2_nu=sigma2_nu,
        time_over_nu=time_over_nu,
    )
    phi_neg_i_inv = 1.0 / phi_neg_i
    discount_factor = math.exp(-r * T)
    forward = spot * math.exp((r - q) * T)

    def integrand_P1(u: float) -> float:
        """Integrand for the delta probability P1 (share measure)."""
        # phi(u - i) / phi(-i) gives the share-measure CF
        phase = cmath.exp(-1j * u * log_K)
        phi_u_minus_i = _vg_characteristic_function_fast(
            u - 1j,
            log_forward=log_forward,
            theta_nu=theta_nu,
            sigma2_nu=sigma2_nu,
            time_over_nu=time_over_nu,
        )
        return (phase * phi_u_minus_i * phi_neg_i_inv / (1j * u)).real

    def integrand_P2(u: float) -> float:
        """Integrand for the strike probability P2 (money-market measure)."""
        phase = cmath.exp(-1j * u * log_K)
        phi_u = _vg_characteristic_function_fast(
            u,
            log_forward=log_forward,
            theta_nu=theta_nu,
            sigma2_nu=sigma2_nu,
            time_over_nu=time_over_nu,
        )
        return (phase * phi_u / (1j * u)).real

    P1_integral, _ = quad(integrand_P1, 1e-8, 200, limit=500)
    P2_integral, _ = quad(integrand_P2, 1e-8, 200, limit=500)

    P1 = 0.5 + P1_integral / math.pi
    P2 = 0.5 + P2_integral / math.pi

    call_price = discount_factor * (forward * P1 - strike * P2)

    return max(call_price, 0.0)


def vg_put(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: VGParams,
    dividend_yield: float = 0.0,
) -> float:
    """VG put price via put-call parity."""
    if T <= 0:
        return max(0.0, strike - spot)
    call = vg_call(spot, strike, T, r, params, dividend_yield)
    q = dividend_yield
    return call - spot * math.exp(-q * T) + strike * math.exp(-r * T)


def vg_price(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: VGParams,
    right: str = "C",
    dividend_yield: float = 0.0,
) -> float:
    """Dispatch to call or put."""
    if right.upper() == "C":
        return vg_call(spot, strike, T, r, params, dividend_yield)
    return vg_put(spot, strike, T, r, params, dividend_yield)
