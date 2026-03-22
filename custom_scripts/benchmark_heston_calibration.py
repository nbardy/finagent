from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import least_squares, minimize


REPO_ROOT = Path(__file__).resolve().parents[1]

import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stratoforge.pricing.calibrate import MarketQuote
from stratoforge.pricing.heston import HestonParams, heston_price
from stratoforge.domain.contracts import ChainIndex, load_option_contracts
from stratoforge.domain.thesis import ThesisSchema
from stratoforge.scoring import build_calibration_quotes
from stratoforge.search.search_space import build_relevant_subchain, build_search_space


ANALYSIS_ROOT = REPO_ROOT / "analysis"


def _load_thesis(path: str | Path) -> ThesisSchema:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ThesisSchema.from_dict(payload)


def _default_output_base(thesis: ThesisSchema) -> Path:
    date_dir = ANALYSIS_ROOT / thesis.asof_date.isoformat()
    date_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    return date_dir / f"heston_calibration_benchmark_{thesis.symbol.lower()}_{timestamp}"


def _initial_guess(spot: float, quotes: list[MarketQuote]) -> np.ndarray:
    atm_iv = max(q.market_price for q in quotes) / spot
    guess = np.array([atm_iv**2, atm_iv**2 * 0.5, 2.0, 0.5, -0.5], dtype=float)
    lower, upper = _bounds()
    return np.clip(guess, lower, upper)


def _bounds() -> tuple[np.ndarray, np.ndarray]:
    lower = np.array([0.01, 0.01, 0.1, 0.01, -0.99], dtype=float)
    upper = np.array([10.0, 10.0, 20.0, 3.0, 0.0], dtype=float)
    return lower, upper


def _weighted_residuals(
    x: np.ndarray,
    *,
    spot: float,
    risk_free_rate: float,
    quotes: list[MarketQuote],
    dividend_yield: float,
) -> np.ndarray:
    params = HestonParams(v0=x[0], theta=x[1], kappa=x[2], xi=x[3], rho=x[4])
    residuals: list[float] = []
    for quote in quotes:
        model_price = heston_price(
            spot=spot,
            strike=quote.strike,
            T=quote.T,
            r=risk_free_rate,
            params=params,
            right=quote.right,
            dividend_yield=dividend_yield,
        )
        residuals.append((model_price - quote.market_price) * math.sqrt(quote.weight))
    return np.array(residuals, dtype=float)


def _summarize_heston_fit(
    *,
    approach: str,
    result_x: np.ndarray,
    wall_time_s: float,
    quotes: list[MarketQuote],
    spot: float,
    risk_free_rate: float,
    dividend_yield: float,
    meta: dict[str, Any],
) -> dict[str, Any]:
    params = HestonParams(
        v0=float(result_x[0]),
        theta=float(result_x[1]),
        kappa=float(result_x[2]),
        xi=float(result_x[3]),
        rho=float(result_x[4]),
    )
    per_quote_errors: list[dict[str, Any]] = []
    abs_errors: list[float] = []
    weighted_residuals = _weighted_residuals(
        result_x,
        spot=spot,
        risk_free_rate=risk_free_rate,
        quotes=quotes,
        dividend_yield=dividend_yield,
    )
    for quote in quotes:
        model_price = heston_price(
            spot=spot,
            strike=quote.strike,
            T=quote.T,
            r=risk_free_rate,
            params=params,
            right=quote.right,
            dividend_yield=dividend_yield,
        )
        error = model_price - quote.market_price
        per_quote_errors.append(
            {
                "strike": quote.strike,
                "T": round(quote.T, 6),
                "right": quote.right,
                "market_price": round(quote.market_price, 6),
                "model_price": round(model_price, 6),
                "error": round(error, 6),
                "weight": quote.weight,
            }
        )
        abs_errors.append(abs(error))

    rmse = math.sqrt(sum(error**2 for error in abs_errors) / len(abs_errors))
    weighted_sse = float(np.sum(weighted_residuals**2))
    return {
        "approach": approach,
        "wall_time_s": round(wall_time_s, 6),
        "rmse": round(rmse, 6),
        "max_error": round(max(abs_errors), 6),
        "weighted_sse": round(weighted_sse, 6),
        "params": {
            "v0": round(params.v0, 8),
            "theta": round(params.theta, 8),
            "kappa": round(params.kappa, 8),
            "xi": round(params.xi, 8),
            "rho": round(params.rho, 8),
        },
        "per_quote_errors": per_quote_errors,
        **meta,
    }


def _run_lbfgsb(
    *,
    label: str,
    spot: float,
    risk_free_rate: float,
    quotes: list[MarketQuote],
    dividend_yield: float,
    ftol: float,
    maxiter: int,
) -> dict[str, Any]:
    lower, upper = _bounds()
    x0 = _initial_guess(spot, quotes)

    def objective(x: np.ndarray) -> float:
        residuals = _weighted_residuals(
            x,
            spot=spot,
            risk_free_rate=risk_free_rate,
            quotes=quotes,
            dividend_yield=dividend_yield,
        )
        return float(np.dot(residuals, residuals))

    started = time.perf_counter()
    result = minimize(
        objective,
        x0,
        method="L-BFGS-B",
        bounds=list(zip(lower, upper, strict=True)),
        options={"maxiter": maxiter, "ftol": ftol},
    )
    wall_time_s = time.perf_counter() - started
    return _summarize_heston_fit(
        approach=label,
        result_x=result.x,
        wall_time_s=wall_time_s,
        quotes=quotes,
        spot=spot,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        meta={
            "success": bool(result.success),
            "message": str(result.message),
            "nfev": int(getattr(result, "nfev", 0)),
            "nit": int(getattr(result, "nit", 0)),
            "njev": int(getattr(result, "njev", 0)) if getattr(result, "njev", None) is not None else None,
            "ftol": ftol,
            "maxiter": maxiter,
            "solver": "minimize:L-BFGS-B",
        },
    )


def _run_least_squares_trf(
    *,
    label: str,
    spot: float,
    risk_free_rate: float,
    quotes: list[MarketQuote],
    dividend_yield: float,
    ftol: float,
    max_nfev: int,
) -> dict[str, Any]:
    lower, upper = _bounds()
    x0 = _initial_guess(spot, quotes)

    def residuals(x: np.ndarray) -> np.ndarray:
        return _weighted_residuals(
            x,
            spot=spot,
            risk_free_rate=risk_free_rate,
            quotes=quotes,
            dividend_yield=dividend_yield,
        )

    started = time.perf_counter()
    result = least_squares(
        residuals,
        x0,
        bounds=(lower, upper),
        method="trf",
        ftol=ftol,
        xtol=ftol,
        gtol=ftol,
        max_nfev=max_nfev,
    )
    wall_time_s = time.perf_counter() - started
    return _summarize_heston_fit(
        approach=label,
        result_x=result.x,
        wall_time_s=wall_time_s,
        quotes=quotes,
        spot=spot,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        meta={
            "success": bool(result.success),
            "message": str(result.message),
            "nfev": int(getattr(result, "nfev", 0)),
            "nit": None,
            "njev": int(getattr(result, "njev", 0)) if getattr(result, "njev", None) is not None else None,
            "ftol": ftol,
            "max_nfev": max_nfev,
            "solver": "least_squares:trf",
            "cost": round(float(result.cost), 6),
        },
    )


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Heston Calibration Solver Benchmark — {payload['thesis_symbol']}",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- spot: `{payload['spot']}`",
        f"- quote_count: `{payload['quote_count']}`",
        f"- risk_free_rate: `{payload['risk_free_rate']}`",
        f"- dividend_yield: `{payload['dividend_yield']}`",
        "",
        "## Approaches",
        "",
    ]
    for result in payload["results"]:
        lines.extend(
            [
                f"### {result['approach']}",
                "",
                f"- solver: `{result['solver']}`",
                f"- wall_time_s: `{result['wall_time_s']}`",
                f"- rmse: `{result['rmse']}`",
                f"- max_error: `{result['max_error']}`",
                f"- weighted_sse: `{result['weighted_sse']}`",
                f"- success: `{result['success']}`",
                f"- nfev: `{result['nfev']}`",
                f"- njev: `{result['njev']}`",
                f"- nit: `{result['nit']}`",
                f"- message: `{result['message']}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Heston calibration solver approaches on a thesis-derived quote subset.")
    parser.add_argument("--thesis", required=True, help="Path to thesis JSON.")
    parser.add_argument("--chain", required=True, help="Path to option chain JSON.")
    parser.add_argument("--output", default=None, help="Optional output base path.")
    parser.add_argument("--risk-free-rate", type=float, default=0.045)
    parser.add_argument("--dividend-yield", type=float, default=0.0)
    args = parser.parse_args()

    thesis = _load_thesis(args.thesis)
    contracts = load_option_contracts(args.chain)
    full_chain = ChainIndex(contracts)
    search_space = build_search_space(thesis, full_chain)
    relevant_chain = build_relevant_subchain(thesis, full_chain, search_space)
    quotes = build_calibration_quotes(
        relevant_chain,
        asof_date=thesis.asof_date,
        spot=thesis.spot,
    )

    results = [
        _run_lbfgsb(
            label="lbfgsb_strict",
            spot=thesis.spot,
            risk_free_rate=args.risk_free_rate,
            quotes=quotes,
            dividend_yield=args.dividend_yield,
            ftol=1e-12,
            maxiter=500,
        ),
        _run_lbfgsb(
            label="lbfgsb_relaxed",
            spot=thesis.spot,
            risk_free_rate=args.risk_free_rate,
            quotes=quotes,
            dividend_yield=args.dividend_yield,
            ftol=1e-6,
            maxiter=150,
        ),
        _run_least_squares_trf(
            label="least_squares_trf",
            spot=thesis.spot,
            risk_free_rate=args.risk_free_rate,
            quotes=quotes,
            dividend_yield=args.dividend_yield,
            ftol=1e-6,
            max_nfev=150,
        ),
    ]

    baseline_time = results[0]["wall_time_s"]
    baseline_rmse = results[0]["rmse"]
    for result in results:
        result["speedup_vs_lbfgsb_strict"] = round(baseline_time / result["wall_time_s"], 4)
        result["rmse_delta_vs_lbfgsb_strict"] = round(result["rmse"] - baseline_rmse, 6)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "as_of": thesis.asof_date.isoformat(),
        "thesis_symbol": thesis.symbol,
        "spot": thesis.spot,
        "quote_count": len(quotes),
        "risk_free_rate": args.risk_free_rate,
        "dividend_yield": args.dividend_yield,
        "results": results,
    }

    base = Path(args.output) if args.output is not None else _default_output_base(thesis)
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(f"Quote count: {len(quotes)}")
    for result in results:
        print(
            f"{result['approach']}: time={result['wall_time_s']:.4f}s "
            f"rmse={result['rmse']:.6f} "
            f"speedup={result['speedup_vs_lbfgsb_strict']:.4f}x "
            f"nfev={result['nfev']}"
        )
    print(f"JSON: {json_path}")
    print(f"Summary: {md_path}")


if __name__ == "__main__":
    main()
