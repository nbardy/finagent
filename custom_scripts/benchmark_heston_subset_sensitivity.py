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

from custom_scripts.benchmark_heston_calibration import (  # noqa: E402
    _load_thesis,
    _run_lbfgsb,
    _run_least_squares_trf,
)
from stratoforge.domain.contracts import ChainIndex, load_option_contracts  # noqa: E402
from stratoforge.domain.thesis import ThesisSchema  # noqa: E402
from stratoforge.pricing.calibrate import MarketQuote  # noqa: E402
from stratoforge.pricing.heston import HestonParams, heston_price  # noqa: E402
from stratoforge.scoring import build_calibration_quotes  # noqa: E402
from stratoforge.search.search_space import build_relevant_subchain, build_search_space  # noqa: E402


ANALYSIS_ROOT = REPO_ROOT / "analysis"


def _default_output_base(thesis: ThesisSchema) -> Path:
    date_dir = ANALYSIS_ROOT / thesis.asof_date.isoformat()
    date_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    return date_dir / f"heston_subset_sensitivity_{thesis.symbol.lower()}_{timestamp}"


def _ordered_quotes(quotes: list[MarketQuote]) -> list[MarketQuote]:
    return sorted(quotes, key=lambda quote: (quote.T, quote.right, quote.strike, quote.market_price))


def _select_quote_subset(quotes: list[MarketQuote], subset_size: int) -> list[MarketQuote]:
    ordered = _ordered_quotes(quotes)
    if subset_size <= 0:
        raise ValueError("subset_size must be positive")
    if subset_size >= len(ordered):
        return ordered

    raw_indices = np.linspace(0, len(ordered) - 1, num=subset_size)
    chosen: list[int] = []
    seen: set[int] = set()
    for raw_index in raw_indices:
        index = int(round(float(raw_index)))
        while index in seen and index + 1 < len(ordered):
            index += 1
        while index in seen and index - 1 >= 0:
            index -= 1
        if index not in seen:
            seen.add(index)
            chosen.append(index)

    if len(chosen) < subset_size:
        for index in range(len(ordered)):
            if index not in seen:
                seen.add(index)
                chosen.append(index)
                if len(chosen) == subset_size:
                    break

    return [ordered[index] for index in sorted(chosen)]


def _fit_metrics(
    params: HestonParams,
    *,
    spot: float,
    risk_free_rate: float,
    quotes: list[MarketQuote],
    dividend_yield: float,
) -> dict[str, Any]:
    errors: list[float] = []
    abs_errors: list[float] = []
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
        weight = math.sqrt(quote.weight)
        errors.append(weight * error)
        abs_errors.append(abs(error))

    weighted_sse = float(np.dot(errors, errors))
    rmse = math.sqrt(sum(error * error for error in abs_errors) / len(abs_errors))
    return {
        "quote_count": len(quotes),
        "rmse": round(rmse, 6),
        "max_error": round(max(abs_errors), 6),
        "weighted_sse": round(weighted_sse, 6),
    }


def _compact_result(
    *,
    subset_size: int,
    approach_result: dict[str, Any],
    validation_metrics: dict[str, Any],
    full_quote_count: int,
) -> dict[str, Any]:
    return {
        "subset_size": subset_size,
        "train_quote_count": subset_size,
        "validation_quote_count": full_quote_count,
        "approach": approach_result["approach"],
        "solver": approach_result["solver"],
        "wall_time_s": approach_result["wall_time_s"],
        "train_rmse": approach_result["rmse"],
        "train_max_error": approach_result["max_error"],
        "train_weighted_sse": approach_result["weighted_sse"],
        "validation_rmse": validation_metrics["rmse"],
        "validation_max_error": validation_metrics["max_error"],
        "validation_weighted_sse": validation_metrics["weighted_sse"],
        "success": approach_result["success"],
        "message": approach_result["message"],
        "nfev": approach_result["nfev"],
        "njev": approach_result["njev"],
        "nit": approach_result["nit"],
        "speedup_vs_lbfgsb_strict": None,
        "params": approach_result["params"],
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Heston Calibration Subset Sensitivity Benchmark — {payload['thesis_symbol']}",
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
                f"- selected_quotes: `{len(block['selected_quotes'])}`",
                f"- validation_quotes: `{payload['quote_count']}`",
                "",
            ]
        )
        for result in block["approaches"]:
            lines.extend(
                [
                    f"- `{result['approach']}`",
                    f"  - solver: `{result['solver']}`",
                    f"  - wall_time_s: `{result['wall_time_s']}`",
                    f"  - train_rmse: `{result['train_rmse']}`",
                    f"  - validation_rmse: `{result['validation_rmse']}`",
                    f"  - train_max_error: `{result['train_max_error']}`",
                    f"  - validation_max_error: `{result['validation_max_error']}`",
                ]
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark Heston calibration fit/runtime across different quote subset sizes.",
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
        train_results = [
            _run_lbfgsb(
                label="lbfgsb_strict",
                spot=thesis.spot,
                risk_free_rate=args.risk_free_rate,
                quotes=subset_quotes,
                dividend_yield=args.dividend_yield,
                ftol=1e-12,
                maxiter=500,
            ),
            _run_lbfgsb(
                label="lbfgsb_relaxed",
                spot=thesis.spot,
                risk_free_rate=args.risk_free_rate,
                quotes=subset_quotes,
                dividend_yield=args.dividend_yield,
                ftol=1e-6,
                maxiter=150,
            ),
            _run_least_squares_trf(
                label="least_squares_trf",
                spot=thesis.spot,
                risk_free_rate=args.risk_free_rate,
                quotes=subset_quotes,
                dividend_yield=args.dividend_yield,
                ftol=1e-6,
                max_nfev=150,
            ),
        ]

        baseline_time = train_results[0]["wall_time_s"]
        validation_blocks: list[dict[str, Any]] = []
        for train_result in train_results:
            params = HestonParams(
                v0=train_result["params"]["v0"],
                theta=train_result["params"]["theta"],
                kappa=train_result["params"]["kappa"],
                xi=train_result["params"]["xi"],
                rho=train_result["params"]["rho"],
            )
            validation_metrics = _fit_metrics(
                params,
                spot=thesis.spot,
                risk_free_rate=args.risk_free_rate,
                quotes=full_quotes,
                dividend_yield=args.dividend_yield,
            )
            compact = _compact_result(
                subset_size=len(subset_quotes),
                approach_result=train_result,
                validation_metrics=validation_metrics,
                full_quote_count=len(full_quotes),
            )
            compact["speedup_vs_lbfgsb_strict"] = round(baseline_time / train_result["wall_time_s"], 4)
            compact["validation_rmse_delta_vs_train"] = round(
                validation_metrics["rmse"] - train_result["rmse"],
                6,
            )
            validation_blocks.append(compact)

        results.append(
            {
                "subset_size": len(subset_quotes),
                "selected_quotes": [
                    {
                        "strike": quote.strike,
                        "T": round(quote.T, 6),
                        "right": quote.right,
                        "market_price": round(quote.market_price, 6),
                        "weight": round(quote.weight, 6),
                    }
                    for quote in subset_quotes
                ],
                "approaches": validation_blocks,
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
    for block in results:
        for result in block["approaches"]:
            print(
                f"subset={block['subset_size']} {result['approach']}: "
                f"time={result['wall_time_s']:.4f}s "
                f"train_rmse={result['train_rmse']:.6f} "
                f"validation_rmse={result['validation_rmse']:.6f}"
            )
    print(f"JSON: {json_path}")
    print(f"Summary: {md_path}")


if __name__ == "__main__":
    main()
