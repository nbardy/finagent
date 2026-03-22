"""
Model calibration — fit parameters to observed market option prices.

Instead of guessing params, minimize pricing error across multiple
strikes/expiries from the actual option chain. This is the ONLY way
to get model prices you can trust.

Usage:
    from option_pricing.calibrate import calibrate_heston, calibrate_vg, calibrate_mjd

    # quotes = [(strike, T, market_mid, right), ...]
    params = calibrate_heston(spot, r, quotes)
    # params is a fitted HestonParams with real values

Each calibration returns fitted params + calibration diagnostics
(RMSE, per-strike errors) so you can judge fit quality.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import math
import os
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from .black_scholes import option_price
from .heston import HestonParams, heston_price
from .merton_jump import MJDParams, mjd_price
from .variance_gamma import VGParams, vg_price


@dataclass(frozen=True)
class CalibrationResult:
    """Result of fitting model params to market quotes."""
    params: HestonParams | VGParams | MJDParams
    rmse: float
    max_error: float
    per_strike_errors: list[dict]
    n_quotes: int
    model: str

    def __str__(self) -> str:
        return (
            f"{self.model} calibration: RMSE=${self.rmse:.4f}, "
            f"MaxErr=${self.max_error:.4f}, N={self.n_quotes}\n"
            f"  Params: {self.params}"
        )


@dataclass(frozen=True)
class MarketQuote:
    """A single observed option price for calibration."""
    strike: float
    T: float
    market_price: float
    right: str = "C"
    weight: float = 1.0  # higher weight = more important to fit


def _pricing_errors(
    model_prices: list[float],
    market_prices: list[float],
    weights: list[float],
) -> float:
    """Weighted sum of squared pricing errors."""
    total = 0.0
    for mp, mkt, w in zip(model_prices, market_prices, weights):
        total += w * (mp - mkt) ** 2
    return total


def calibrate_heston(
    spot: float,
    r: float,
    quotes: list[MarketQuote],
    dividend_yield: float = 0.0,
) -> CalibrationResult:
    """
    Fit Heston params to observed option prices via L-BFGS-B.

    Optimizes: v0, theta, kappa, xi, rho
    Bounds enforce Feller condition and reasonable ranges.
    """
    market_prices = [q.market_price for q in quotes]
    weights = [q.weight for q in quotes]

    def objective(x: np.ndarray) -> float:
        v0, theta, kappa, xi, rho = x
        params = HestonParams(v0=v0, theta=theta, kappa=kappa, xi=xi, rho=rho)
        model_prices = []
        for q in quotes:
            try:
                p = heston_price(spot, q.strike, q.T, r, params, q.right, dividend_yield)
                model_prices.append(p)
            except Exception:
                return 1e10  # penalize invalid params
        return _pricing_errors(model_prices, market_prices, weights)

    # Initial guess from ATM IV
    atm_iv = max(q.market_price for q in quotes) / spot  # rough
    x0 = np.array([atm_iv**2, atm_iv**2 * 0.5, 2.0, 0.5, -0.5])

    bounds = [
        (0.01, 10.0),    # v0: variance must be positive
        (0.01, 10.0),    # theta: long-run variance
        (0.1, 20.0),     # kappa: mean reversion speed
        (0.01, 3.0),     # xi: vol of vol
        (-0.99, 0.0),    # rho: stock-vol correlation (negative for equity)
    ]

    result = minimize(objective, x0, method="L-BFGS-B", bounds=bounds,
                      options={"maxiter": 500, "ftol": 1e-12})

    fitted = HestonParams(
        v0=result.x[0], theta=result.x[1], kappa=result.x[2],
        xi=result.x[3], rho=result.x[4],
    )

    # Compute per-strike errors
    errors = []
    for q in quotes:
        mp = heston_price(spot, q.strike, q.T, r, fitted, q.right, dividend_yield)
        errors.append({
            "strike": q.strike, "T": round(q.T, 4), "right": q.right,
            "market": round(q.market_price, 4), "model": round(mp, 4),
            "error": round(mp - q.market_price, 4),
        })

    abs_errors = [abs(e["error"]) for e in errors]
    rmse = math.sqrt(sum(e**2 for e in abs_errors) / len(abs_errors))

    return CalibrationResult(
        params=fitted, rmse=round(rmse, 4),
        max_error=round(max(abs_errors), 4),
        per_strike_errors=errors, n_quotes=len(quotes), model="Heston",
    )


def calibrate_vg(
    spot: float,
    r: float,
    quotes: list[MarketQuote],
    dividend_yield: float = 0.0,
) -> CalibrationResult:
    """Fit VG params (sigma, theta, nu) to observed option prices."""
    market_prices = [q.market_price for q in quotes]
    weights = [q.weight for q in quotes]

    def objective(x: np.ndarray) -> float:
        sigma, theta, nu = x
        # Check VG validity: 1 - theta*nu - 0.5*sigma²*nu > 0
        if 1.0 - theta * nu - 0.5 * sigma**2 * nu <= 0:
            return 1e10
        params = VGParams(sigma=sigma, theta=theta, nu=nu)
        model_prices = []
        for q in quotes:
            try:
                p = vg_price(spot, q.strike, q.T, r, params, q.right, dividend_yield)
                model_prices.append(p)
            except Exception:
                return 1e10
        return _pricing_errors(model_prices, market_prices, weights)

    # Initial guess
    x0 = np.array([0.5, -0.1, 0.2])

    bounds = [
        (0.05, 5.0),     # sigma
        (-2.0, 0.0),     # theta (negative skew for equity)
        (0.01, 2.0),     # nu
    ]

    result = minimize(objective, x0, method="L-BFGS-B", bounds=bounds,
                      options={"maxiter": 500, "ftol": 1e-12})

    fitted = VGParams(sigma=result.x[0], theta=result.x[1], nu=result.x[2])

    errors = []
    for q in quotes:
        mp = vg_price(spot, q.strike, q.T, r, fitted, q.right, dividend_yield)
        errors.append({
            "strike": q.strike, "T": round(q.T, 4), "right": q.right,
            "market": round(q.market_price, 4), "model": round(mp, 4),
            "error": round(mp - q.market_price, 4),
        })

    abs_errors = [abs(e["error"]) for e in errors]
    rmse = math.sqrt(sum(e**2 for e in abs_errors) / len(abs_errors))

    return CalibrationResult(
        params=fitted, rmse=round(rmse, 4),
        max_error=round(max(abs_errors), 4),
        per_strike_errors=errors, n_quotes=len(quotes), model="VG",
    )


def calibrate_mjd(
    spot: float,
    r: float,
    quotes: list[MarketQuote],
    dividend_yield: float = 0.0,
) -> CalibrationResult:
    """Fit MJD params (sigma, lam, mu_j, sigma_j) to observed option prices."""
    market_prices = [q.market_price for q in quotes]
    weights = [q.weight for q in quotes]

    def objective(x: np.ndarray) -> float:
        sigma, lam, mu_j, sigma_j = x
        params = MJDParams(sigma=sigma, lam=lam, mu_j=mu_j, sigma_j=sigma_j)
        model_prices = []
        for q in quotes:
            try:
                p = mjd_price(spot, q.strike, q.T, r, params, q.right, dividend_yield)
                model_prices.append(p)
            except Exception:
                return 1e10
        return _pricing_errors(model_prices, market_prices, weights)

    x0 = np.array([0.5, 1.0, -0.05, 0.15])

    bounds = [
        (0.05, 5.0),     # sigma
        (0.01, 10.0),    # lam (jumps/year)
        (-0.5, 0.1),     # mu_j (mean jump, usually negative)
        (0.01, 1.0),     # sigma_j (jump vol)
    ]

    result = minimize(objective, x0, method="L-BFGS-B", bounds=bounds,
                      options={"maxiter": 500, "ftol": 1e-12})

    fitted = MJDParams(
        sigma=result.x[0], lam=result.x[1],
        mu_j=result.x[2], sigma_j=result.x[3],
    )

    errors = []
    for q in quotes:
        mp = mjd_price(spot, q.strike, q.T, r, fitted, q.right, dividend_yield)
        errors.append({
            "strike": q.strike, "T": round(q.T, 4), "right": q.right,
            "market": round(q.market_price, 4), "model": round(mp, 4),
            "error": round(mp - q.market_price, 4),
        })

    abs_errors = [abs(e["error"]) for e in errors]
    rmse = math.sqrt(sum(e**2 for e in abs_errors) / len(abs_errors))

    return CalibrationResult(
        params=fitted, rmse=round(rmse, 4),
        max_error=round(max(abs_errors), 4),
        per_strike_errors=errors, n_quotes=len(quotes), model="MJD",
    )


def calibrate_all(
    spot: float,
    r: float,
    quotes: list[MarketQuote],
    dividend_yield: float = 0.0,
) -> dict[str, CalibrationResult]:
    """Calibrate all three models and return results keyed by model name."""
    tasks = [
        ("Heston", calibrate_heston),
        ("VG", calibrate_vg),
        ("MJD", calibrate_mjd),
    ]
    if len(tasks) <= 1:
        return {
            name: calibrator(spot, r, quotes, dividend_yield)
            for name, calibrator in tasks
        }

    max_workers = min(len(tasks), os.cpu_count() or 1)
    if max_workers <= 1:
        results: dict[str, CalibrationResult] = {}
        for name, calibrator in tasks:
            try:
                results[name] = calibrator(spot, r, quotes, dividend_yield)
            except Exception as e:
                print(f"  {name} calibration failed: {e}")
        return results

    results: dict[str, CalibrationResult] = {}
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(calibrator, spot, r, quotes, dividend_yield): name
            for name, calibrator in tasks
        }
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                results[name] = future.result()
            except Exception as e:
                print(f"  {name} calibration failed: {e}")
    return results
