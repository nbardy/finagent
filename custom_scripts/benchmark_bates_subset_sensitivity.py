from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_scripts.benchmark_heston_subset_sensitivity import _select_quote_subset  # noqa: E402
from custom_scripts.benchmark_heston_calibration import _load_thesis  # noqa: E402
from stratoforge.domain.contracts import ChainIndex, load_option_contracts  # noqa: E402
from stratoforge.domain.thesis import ThesisSchema  # noqa: E402
from stratoforge.pricing.bates import BatesParams, bates_price  # noqa: E402
from stratoforge.pricing.calibrate import MarketQuote, calibrate_bates  # noqa: E402
from stratoforge.scoring import build_calibration_quotes  # noqa: E402
from stratoforge.search.search_space import build_relevant_subchain, build_search_space  # noqa: E402


ANALYSIS_ROOT = REPO_ROOT / "analysis"


def _default_output_base(thesis: ThesisSchema) -> Path:
    date_dir = ANALYSIS_ROOT / thesis.asof_date.isoformat()
    date_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    return date_dir / f"bates_subset_sensitivity_{thesis.symbol.lower()}_{timestamp}"


def _fit_metrics(
    params: BatesParams,
    *,
    spot: float,
    risk_free_rate: float,
    quotes: list[MarketQuote],
    dividend_yield: float,
) -> dict[str, Any]:
    errors: list[float] = []
    abs_errors: list[float] = []
    for quote in quotes:
        model_price = bates_price(
            spot=spot,
            strike=quote.strike,
            T=quote.T,
            r=risk_free_rate,
            params=params,
            right=quote.right,
            dividend_yield=dividend_yield,
        )
        error = model_price - quote.market_price
        errors.append(math.sqrt(quote.weight) * error)
        abs_errors.append(abs(error))

    weighted_sse = float(np.dot(errors, errors))
    rmse = math.sqrt(sum(error * error for error in abs_errors) / len(abs_errors))
    return {
        "quote_count": len(quotes),
        "rmse": round(rmse, 6),
        "max_error": round(max(abs_errors), 6),
        "weighted_sse": round(weighted_sse, 6),
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Bates Calibration Subset Sensitivity Benchmark — {payload['thesis_symbol']}",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- spot: `{payload['spot']}`",
        f"- quote_count: `{payload['quote_count']}`",
        f"- subset_sizes: `{payload['subset_sizes']}`",
        f"- risk_free_rate: `{payload['risk_free_rate']}`",
        f"- dividend_yield: `{payload['dividend_yield']}`",
        "",
        "## Results",
        "",
    ]
    for block in payload["results"]:
        lines.extend(
            [
                f"### subset_size={block['subset_size']}",
                "",
                f"- selected_quotes: `{block['train_quote_count']}`",
                f"- validation_quotes: `{block['validation_quote_count']}`",
                f"- wall_time_s: `{block['wall_time_s']}`",
                f"- train_rmse: `{block['train_rmse']}`",
                f"- validation_rmse: `{block['validation_rmse']}`",
                f"- train_max_error: `{block['train_max_error']}`",
                f"- validation_max_error: `{block['validation_max_error']}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark Bates calibration fit/runtime across different quote subset sizes.",
    )
    parser.add_argument("--thesis", required=True, help="Path to thesis JSON.")
    parser.add_argument("--chain", required=True, help="Path to option chain JSON.")
    parser.add_argument("--output", default=None, help="Optional output base path.")
    parser.add_argument(
        "--subset-sizes",
        nargs="+",
        type=int,
        default=None,
        help="Subset sizes to benchmark. Defaults to a compact sweep based on the quote count.",
    )
    parser.add_argument("--risk-free-rate", type=float, default=0.045)
    parser.add_argument("--dividend-yield", type=float, default=0.0)
    args = parser.parse_args()

    thesis = _load_thesis(args.thesis)
    contracts = load_option_contracts(args.chain)
    full_chain = ChainIndex(contracts)
    search_space = build_search_space(thesis, full_chain)
    relevant_chain = build_relevant_subchain(thesis, full_chain, search_space)
    full_quotes = build_calibration_quotes(
        relevant_chain,
        asof_date=thesis.asof_date,
        spot=thesis.spot,
    )

    subset_sizes = args.subset_sizes or sorted(
        {
            max(3, min(5, len(full_quotes))),
            max(3, min(10, len(full_quotes))),
            max(3, min(15, len(full_quotes))),
            len(full_quotes),
        }
    )

    results: list[dict[str, Any]] = []
    for subset_size in subset_sizes:
        subset_quotes = _select_quote_subset(full_quotes, subset_size)
        started = time.perf_counter()
        fitted = calibrate_bates(
            thesis.spot,
            args.risk_free_rate,
            subset_quotes,
            args.dividend_yield,
        )
        wall_time_s = time.perf_counter() - started
        validation_metrics = _fit_metrics(
            fitted.params,
            spot=thesis.spot,
            risk_free_rate=args.risk_free_rate,
            quotes=full_quotes,
            dividend_yield=args.dividend_yield,
        )
        results.append(
            {
                "subset_size": len(subset_quotes),
                "train_quote_count": len(subset_quotes),
                "validation_quote_count": len(full_quotes),
                "wall_time_s": round(wall_time_s, 6),
                "train_rmse": fitted.rmse,
                "train_max_error": fitted.max_error,
                "validation_rmse": validation_metrics["rmse"],
                "validation_max_error": validation_metrics["max_error"],
                "validation_weighted_sse": validation_metrics["weighted_sse"],
                "params": {
                    "v0": fitted.params.v0,
                    "theta": fitted.params.theta,
                    "kappa": fitted.params.kappa,
                    "xi": fitted.params.xi,
                    "rho": fitted.params.rho,
                    "lam": fitted.params.lam,
                    "mu_j": fitted.params.mu_j,
                    "sigma_j": fitted.params.sigma_j,
                },
            }
        )

    payload = {
        "generated_at": datetime.now().isoformat(),
        "as_of": thesis.asof_date.isoformat(),
        "thesis_symbol": thesis.symbol,
        "spot": thesis.spot,
        "quote_count": len(full_quotes),
        "subset_sizes": [block["subset_size"] for block in results],
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

    print(f"Quote count: {len(full_quotes)}")
    for result in results:
        print(
            f"subset={result['subset_size']}: "
            f"time={result['wall_time_s']:.4f}s "
            f"train_rmse={result['train_rmse']:.6f} "
            f"validation_rmse={result['validation_rmse']:.6f}"
        )
    print(f"JSON: {json_path}")
    print(f"Summary: {md_path}")


if __name__ == "__main__":
    main()
