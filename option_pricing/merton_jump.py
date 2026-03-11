"""
Merton Jump-Diffusion (MJD) option pricing model.

Extends Black-Scholes by overlaying a compound Poisson process of
log-normal jumps onto the usual geometric Brownian motion. This captures
sudden, discrete price moves (earnings surprises, FDA decisions, etc.)
that pure diffusion models miss entirely.

Why MJD for LEAPs:
  - Over long horizons (1-2 years), the probability of at least one
    "jump event" is substantial. MJD prices this tail risk explicitly.
  - The semi-closed form is an infinite series of BS prices, each
    weighted by the Poisson probability of k jumps occurring.
    Converges fast (typically 20-30 terms suffice).
  - Four parameters beyond r:
      sigma   - diffusion volatility (the "normal" BS vol)
      lam     - jump intensity (expected number of jumps per year)
      mu_j    - mean log-jump size (negative -> crash risk)
      sigma_j - jump size volatility (uncertainty in jump magnitude)

Reference: Merton (1976) "Option pricing when underlying stock
returns are discontinuous," Journal of Financial Economics 3, 125-144.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .black_scholes import bs_call, bs_put

if TYPE_CHECKING:
    from .heston import HestonParams
    from .variance_gamma import VGParams


@dataclass(frozen=True)
class MJDParams:
    """
    Merton Jump-Diffusion model parameters.

    sigma:   diffusion volatility (continuous component)
    lam:     jump intensity -- expected jumps per year
    mu_j:    mean of the log-normal jump size
             Negative mu_j biases jumps downward (crash risk).
    sigma_j: volatility of the log-normal jump size
    """
    sigma: float
    lam: float
    mu_j: float
    sigma_j: float

    @classmethod
    def from_market(
        cls,
        diffusion_vol: float,
        jumps_per_year: float,
        mean_jump_pct: float,
        jump_vol: float,
    ) -> MJDParams:
        """
        Construct from market-intuitive quantities.
        All parameters required — no silent defaults.

        diffusion_vol:  the "normal" vol component (BS-like)
        jumps_per_year: expected number of jump events per year
        mean_jump_pct:  mean log-jump size (e.g. -0.05 -> ~5% drop on average)
        jump_vol:       std dev of log-jump size
        """
        return cls(
            sigma=diffusion_vol,
            lam=jumps_per_year,
            mu_j=mean_jump_pct,
            sigma_j=jump_vol,
        )

    @property
    def mean_jump_compensation(self) -> float:
        """
        Compensator k = exp(mu_j + 0.5*sigma_j^2) - 1.

        The drift of the stock is adjusted by -lam*k to maintain
        the martingale property under the risk-neutral measure.
        """
        return math.exp(self.mu_j + 0.5 * self.sigma_j ** 2) - 1.0


def mjd_call(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: MJDParams,
    dividend_yield: float = 0.0,
    n_terms: int = 50,
) -> float:
    """
    Merton Jump-Diffusion call price.

    Semi-closed form: infinite series of Poisson-weighted BS call prices.
    Each term uses an adjusted risk-free rate and volatility that account
    for the expected contribution of n jumps over [0, T].

    The n-th term is:
      Term_n = P(N=n) * BS_call(spot, strike, T, r_n, sigma_n)
    where:
      P(N=n) = exp(-lam'*T) * (lam'*T)^n / n!   (Poisson weight)
      lam'   = lam * (1 + k)                      (risk-neutral intensity)
      r_n    = r - lam*k + n*(mu_j + 0.5*sigma_j^2)/T
      sigma_n = sqrt(sigma^2 + n*sigma_j^2/T)

    n_terms: number of series terms (50 is more than enough for lam <= 10).
    """
    if T <= 0:
        return max(0.0, spot - strike)

    sigma = params.sigma
    lam = params.lam
    mu_j = params.mu_j
    sigma_j = params.sigma_j
    k = params.mean_jump_compensation

    # Risk-neutral jump intensity
    lam_prime = lam * (1.0 + k)

    price = 0.0
    for n in range(n_terms):
        # Poisson weight via log to avoid overflow for large n
        log_poisson = (
            -lam_prime * T
            + n * math.log(max(lam_prime * T, 1e-300))
            - math.lgamma(n + 1)
        )
        poisson_weight = math.exp(log_poisson)

        if poisson_weight < 1e-20:
            continue

        # Adjusted volatility: sqrt(sigma^2 + n*sigma_j^2/T)
        sigma_n = math.sqrt(sigma ** 2 + n * sigma_j ** 2 / T)

        # Adjusted risk-free rate
        r_n = r - lam * k + n * (mu_j + 0.5 * sigma_j ** 2) / T

        price += poisson_weight * bs_call(spot, strike, T, r_n, sigma_n, dividend_yield)

    return max(price, 0.0)


def mjd_put(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: MJDParams,
    dividend_yield: float = 0.0,
    n_terms: int = 50,
) -> float:
    """MJD put price via put-call parity."""
    if T <= 0:
        return max(0.0, strike - spot)
    call = mjd_call(spot, strike, T, r, params, dividend_yield, n_terms)
    q = dividend_yield
    return call - spot * math.exp(-q * T) + strike * math.exp(-r * T)


def mjd_price(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: MJDParams,
    right: str = "C",
    dividend_yield: float = 0.0,
    n_terms: int = 50,
) -> float:
    """Dispatch to call or put."""
    if right.upper() == "C":
        return mjd_call(spot, strike, T, r, params, dividend_yield, n_terms)
    return mjd_put(spot, strike, T, r, params, dividend_yield, n_terms)


def compare_all_models(
    spot: float,
    strike: float,
    T: float,
    r: float,
    bs_vol: float,
    heston_params: HestonParams | None = None,
    vg_params: VGParams | None = None,
    mjd_params: MJDParams | None = None,
    right: str = "C",
    dividend_yield: float = 0.0,
    bid: float = 0.0,
    ask: float = 0.0,
) -> dict:
    """
    Compare BS, Heston, Variance Gamma, and Merton Jump-Diffusion
    pricing for a single option. Returns a dict with all model prices
    and their differences from BS.

    Any model with None params is skipped.
    """
    # Deferred imports to avoid circular dependencies at module load time
    from .black_scholes import option_price as bs_option_price
    from .heston import heston_price
    from .variance_gamma import vg_price

    bs = bs_option_price(spot, strike, T, r, bs_vol, right, dividend_yield)
    mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0

    result = {
        "strike": strike,
        "right": right,
        "dte": int(T * 365),
        "bs_price": round(bs, 4),
        "market_mid": round(mid, 4) if mid > 0 else None,
    }

    if heston_params is not None:
        h = heston_price(spot, strike, T, r, heston_params, right, dividend_yield)
        result["heston_price"] = round(h, 4)
        result["heston_vs_bs"] = round(h - bs, 4)

    if vg_params is not None:
        v = vg_price(spot, strike, T, r, vg_params, right, dividend_yield)
        result["vg_price"] = round(v, 4)
        result["vg_vs_bs"] = round(v - bs, 4)

    if mjd_params is not None:
        m = mjd_price(spot, strike, T, r, mjd_params, right, dividend_yield)
        result["mjd_price"] = round(m, 4)
        result["mjd_vs_bs"] = round(m - bs, 4)

    return result
