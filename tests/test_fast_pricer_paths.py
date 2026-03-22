from __future__ import annotations

import math
import statistics
import time
import unittest

import numpy as np
from scipy.integrate import quad

from option_pricing.heston import HestonParams, heston_call
from option_pricing.variance_gamma import VGParams, vg_call


def _heston_characteristic_function_reference(
    u: complex,
    spot: float,
    T: float,
    r: float,
    q: float,
    params: HestonParams,
) -> complex:
    v0 = params.v0
    theta = params.theta
    kappa = params.kappa
    xi = params.xi
    rho = params.rho

    d = np.sqrt((rho * xi * 1j * u - kappa) ** 2 + xi**2 * (1j * u + u**2))
    g = (kappa - rho * xi * 1j * u - d) / (kappa - rho * xi * 1j * u + d)
    exp_neg_dT = np.exp(-d * T)

    C = (r - q) * 1j * u * T + (kappa * theta / xi**2) * (
        (kappa - rho * xi * 1j * u - d) * T
        - 2.0 * np.log((1.0 - g * exp_neg_dT) / (1.0 - g))
    )
    D = ((kappa - rho * xi * 1j * u - d) / xi**2) * (
        (1.0 - exp_neg_dT) / (1.0 - g * exp_neg_dT)
    )
    return np.exp(C + D * v0 + 1j * u * np.log(spot))


def _heston_call_reference(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: HestonParams,
    dividend_yield: float = 0.0,
) -> float:
    if T <= 0:
        return max(0.0, spot - strike)

    q = dividend_yield
    log_K = math.log(strike)

    def integrand_P1(u: float) -> float:
        phi = _heston_characteristic_function_reference(u - 1j, spot, T, r, q, params)
        cf_neg_i = _heston_characteristic_function_reference(-1j, spot, T, r, q, params)
        return np.real(np.exp(-1j * u * log_K) * phi / (1j * u * cf_neg_i))

    def integrand_P2(u: float) -> float:
        phi = _heston_characteristic_function_reference(u, spot, T, r, q, params)
        return np.real(np.exp(-1j * u * log_K) * phi / (1j * u))

    P1_integral, _ = quad(integrand_P1, 1e-8, 200, limit=500)
    P2_integral, _ = quad(integrand_P2, 1e-8, 200, limit=500)

    P1 = 0.5 + P1_integral / math.pi
    P2 = 0.5 + P2_integral / math.pi
    forward = spot * math.exp((r - q) * T)
    call_price = forward * math.exp(-r * T) * P1 - strike * math.exp(-r * T) * P2
    return max(call_price, 0.0)


def _vg_characteristic_function_reference(
    u: complex,
    spot: float,
    T: float,
    r: float,
    q: float,
    params: VGParams,
) -> complex:
    sigma = params.sigma
    theta = params.theta
    nu = params.nu
    omega = params.omega

    log_fwd = np.log(spot) + (r - q + omega) * T
    inner = 1.0 - 1j * u * theta * nu + 0.5 * sigma**2 * nu * u**2
    vg_exponent = -(T / nu) * np.log(inner)
    return np.exp(1j * u * log_fwd + vg_exponent)


def _vg_call_reference(
    spot: float,
    strike: float,
    T: float,
    r: float,
    params: VGParams,
    dividend_yield: float = 0.0,
) -> float:
    if T <= 0:
        return max(0.0, spot - strike)

    q = dividend_yield
    log_K = math.log(strike)

    def integrand_P1(u: float) -> float:
        phi_u_minus_i = _vg_characteristic_function_reference(u - 1j, spot, T, r, q, params)
        phi_neg_i = _vg_characteristic_function_reference(-1j, spot, T, r, q, params)
        return np.real(np.exp(-1j * u * log_K) * phi_u_minus_i / (1j * u * phi_neg_i))

    def integrand_P2(u: float) -> float:
        phi_u = _vg_characteristic_function_reference(u, spot, T, r, q, params)
        return np.real(np.exp(-1j * u * log_K) * phi_u / (1j * u))

    P1_integral, _ = quad(integrand_P1, 1e-8, 200, limit=500)
    P2_integral, _ = quad(integrand_P2, 1e-8, 200, limit=500)

    P1 = 0.5 + P1_integral / math.pi
    P2 = 0.5 + P2_integral / math.pi
    forward = spot * math.exp((r - q) * T)
    call_price = math.exp(-r * T) * (forward * P1 - strike * P2)
    return max(call_price, 0.0)


def _benchmark_per_call(fn, cases: list[dict[str, float]], *, repeats: int = 5, loops: int = 6) -> float:
    samples: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        for _ in range(loops):
            for case in cases:
                fn(**case)
        elapsed = time.perf_counter() - start
        samples.append(elapsed / (loops * len(cases)))
    return statistics.median(samples)


class FastPricerPathTests(unittest.TestCase):
    def test_heston_fast_path_matches_reference_and_is_faster(self) -> None:
        params = HestonParams(v0=0.04, theta=0.05, kappa=3.0, xi=0.35, rho=-0.6)
        cases = [
            {
                "spot": 658.0,
                "strike": strike,
                "T": T,
                "r": 0.045,
                "params": params,
                "dividend_yield": 0.01,
            }
            for T in (7 / 365, 21 / 365, 63 / 365)
            for strike in (520.0, 600.0, 640.0)
        ]

        for case in cases:
            baseline = _heston_call_reference(**case)
            fast = heston_call(**case)
            self.assertTrue(
                math.isclose(baseline, fast, rel_tol=1e-7, abs_tol=1e-6),
                msg=f"Heston mismatch baseline={baseline:.10f} fast={fast:.10f} case={case}",
            )

        for case in cases:
            _heston_call_reference(**case)
            heston_call(**case)

        baseline_time = _benchmark_per_call(_heston_call_reference, cases)
        fast_time = _benchmark_per_call(heston_call, cases)
        self.assertLessEqual(
            fast_time,
            baseline_time * 0.90,
            msg=(
                f"Heston fast path not faster enough: baseline={baseline_time:.6f}s/call "
                f"fast={fast_time:.6f}s/call"
            ),
        )

    def test_vg_fast_path_matches_reference_and_is_faster(self) -> None:
        params = VGParams(sigma=0.25, theta=-0.12, nu=0.2)
        cases = [
            {
                "spot": 658.0,
                "strike": strike,
                "T": T,
                "r": 0.045,
                "params": params,
                "dividend_yield": 0.01,
            }
            for T in (7 / 365, 21 / 365, 63 / 365)
            for strike in (520.0, 600.0, 640.0)
        ]

        for case in cases:
            baseline = _vg_call_reference(**case)
            fast = vg_call(**case)
            self.assertTrue(
                math.isclose(baseline, fast, rel_tol=1e-7, abs_tol=1e-6),
                msg=f"VG mismatch baseline={baseline:.10f} fast={fast:.10f} case={case}",
            )

        for case in cases:
            _vg_call_reference(**case)
            vg_call(**case)

        baseline_time = _benchmark_per_call(_vg_call_reference, cases)
        fast_time = _benchmark_per_call(vg_call, cases)
        self.assertLessEqual(
            fast_time,
            baseline_time * 0.90,
            msg=(
                f"VG fast path not faster enough: baseline={baseline_time:.6f}s/call "
                f"fast={fast_time:.6f}s/call"
            ),
        )


if __name__ == "__main__":
    unittest.main()
