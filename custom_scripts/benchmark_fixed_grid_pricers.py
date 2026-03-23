from __future__ import annotations

import json
import statistics
import time
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stratoforge.pricing.bates import BatesParams, bates_price, bates_price_fixed_grid  # noqa: E402
from stratoforge.pricing.heston import HestonParams, heston_price, heston_price_fixed_grid  # noqa: E402


ANALYSIS_ROOT = REPO_ROOT / "analysis" / datetime.now().strftime("%Y-%m-%d")
ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)


def _bench(fn, cases: list[tuple], repeats: int = 3) -> float:
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        for case in cases:
            fn(*case)
        samples.append((time.perf_counter() - started) / len(cases))
    return statistics.median(samples)


def main() -> None:
    heston_params = HestonParams(v0=0.04, theta=0.05, kappa=3.0, xi=0.35, rho=-0.6)
    bates_params = BatesParams(
        v0=0.04,
        theta=0.05,
        kappa=3.0,
        xi=0.35,
        rho=-0.6,
        lam=1.0,
        mu_j=-0.05,
        sigma_j=0.12,
    )
    cases = [
        (658.0, strike, T, 0.045, "P", 0.01)
        for T in (7 / 365, 21 / 365, 63 / 365, 126 / 365)
        for strike in (520.0, 560.0, 600.0, 640.0, 680.0)
    ]

    heston_errors = []
    bates_errors = []
    for spot, strike, time_to_expiry, rate, right, dividend_yield in cases:
        heston_ref = heston_price(spot, strike, time_to_expiry, rate, heston_params, right, dividend_yield)
        heston_fast = heston_price_fixed_grid(
            spot,
            strike,
            time_to_expiry,
            rate,
            heston_params,
            right,
            dividend_yield,
        )
        heston_errors.append(abs(heston_ref - heston_fast))

        bates_ref = bates_price(spot, strike, time_to_expiry, rate, bates_params, right, dividend_yield)
        bates_fast = bates_price_fixed_grid(
            spot,
            strike,
            time_to_expiry,
            rate,
            bates_params,
            right,
            dividend_yield,
        )
        bates_errors.append(abs(bates_ref - bates_fast))

    heston_ref_time = _bench(lambda *args: heston_price(args[0], args[1], args[2], args[3], heston_params, args[4], args[5]), cases)
    heston_fast_time = _bench(lambda *args: heston_price_fixed_grid(args[0], args[1], args[2], args[3], heston_params, args[4], args[5]), cases)
    bates_ref_time = _bench(lambda *args: bates_price(args[0], args[1], args[2], args[3], bates_params, args[4], args[5]), cases)
    bates_fast_time = _bench(lambda *args: bates_price_fixed_grid(args[0], args[1], args[2], args[3], bates_params, args[4], args[5]), cases)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "case_count": len(cases),
        "heston": {
            "reference_time_per_call_s": round(heston_ref_time, 6),
            "fixed_grid_time_per_call_s": round(heston_fast_time, 6),
            "speedup": round(heston_ref_time / heston_fast_time, 4),
            "median_abs_error": round(statistics.median(heston_errors), 6),
            "p95_abs_error": round(sorted(heston_errors)[int(0.95 * (len(heston_errors) - 1))], 6),
            "max_abs_error": round(max(heston_errors), 6),
        },
        "bates": {
            "reference_time_per_call_s": round(bates_ref_time, 6),
            "fixed_grid_time_per_call_s": round(bates_fast_time, 6),
            "speedup": round(bates_ref_time / bates_fast_time, 4),
            "median_abs_error": round(statistics.median(bates_errors), 6),
            "p95_abs_error": round(sorted(bates_errors)[int(0.95 * (len(bates_errors) - 1))], 6),
            "max_abs_error": round(max(bates_errors), 6),
        },
    }

    output_path = ANALYSIS_ROOT / "fixed_grid_pricer_benchmark.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"JSON: {output_path}")


if __name__ == "__main__":
    main()
