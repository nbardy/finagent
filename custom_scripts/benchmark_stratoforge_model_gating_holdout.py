from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stratoforge.domain.contracts import ChainIndex, OptionContract, load_option_contracts
from stratoforge.domain.thesis import ThesisSchema
from stratoforge.pricing.black_scholes import option_price
from stratoforge.pricing.bates import bates_price
from stratoforge.pricing.heston import heston_price
from stratoforge.pricing.merton_jump import mjd_price
from stratoforge.pricing.variance_gamma import vg_price
from stratoforge.scoring import (
    _select_structural_models_for_consensus,
    calibrate_model_suite,
    fit_surface_state,
)
from stratoforge.search.search_space import build_relevant_subchain, build_search_space
from stratoforge.surface.ssvi import ssvi_implied_vol


ANALYSIS_ROOT = REPO_ROOT / "analysis"
DEFAULT_THESIS = ANALYSIS_ROOT / "2026-03-19" / "spy_geopolitical_bottom_stratoforge_thesis.json"
DEFAULT_CHAIN = ANALYSIS_ROOT / "2026-03-19" / "spy_geopolitical_bottom_chain.json"
DEFAULT_OUTPUT_BASENAME = ANALYSIS_ROOT / "2026-03-23" / "spy_model_gating_holdout"


@dataclass(frozen=True)
class ModelPrediction:
    name: str
    price: float
    abs_error: float
    signed_error: float


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


def _load_thesis(path: str | Path) -> ThesisSchema:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return ThesisSchema.from_dict(payload)


def _default_output_base(thesis: ThesisSchema) -> Path:
    date_dir = ANALYSIS_ROOT / date.today().isoformat()
    date_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    topic = _slugify(f"stratoforge_model_gating_holdout_{thesis.symbol}_{timestamp}")
    return date_dir / topic


def _parse_fractions(values: list[float] | None) -> tuple[float, ...]:
    if not values:
        return (0.15, 0.25, 0.35)
    fractions = tuple(sorted({float(value) for value in values if 0.0 < float(value) < 0.5}))
    if not fractions:
        raise ValueError("At least one holdout fraction in (0, 0.5) is required.")
    return fractions


def _quote_sort_key(
    contract: OptionContract,
    spot: float,
    asof_date: date,
    *,
    risk_free_rate: float,
    dividend_yield: float,
) -> tuple[float, float, float]:
    dte = max((contract.expiry - asof_date).days, 0)
    time_to_expiry = max(dte / 365.0, 1 / 365.0)
    forward = spot * math.exp((risk_free_rate - dividend_yield) * time_to_expiry)
    if forward <= 0 or contract.strike <= 0:
        log_moneyness = float("inf")
    else:
        log_moneyness = abs(math.log(contract.strike / forward))
    return (log_moneyness, contract.strike, contract.mid)


def _split_train_holdout(
    contracts: tuple[OptionContract, ...],
    *,
    asof_date: date,
    spot: float,
    risk_free_rate: float,
    dividend_yield: float,
    holdout_fraction: float,
) -> tuple[tuple[OptionContract, ...], tuple[OptionContract, ...]]:
    grouped: dict[date, list[OptionContract]] = defaultdict(list)
    for contract in contracts:
        if contract.mid <= 0:
            continue
        dte = max((contract.expiry - asof_date).days, 0)
        if dte <= 0:
            continue
        grouped[contract.expiry].append(contract)

    train: list[OptionContract] = []
    holdout: list[OptionContract] = []
    for expiry, expiry_contracts in sorted(grouped.items()):
        ordered = sorted(
            expiry_contracts,
            key=lambda contract: _quote_sort_key(
                contract,
                spot,
                asof_date,
                risk_free_rate=risk_free_rate,
                dividend_yield=dividend_yield,
            ),
        )
        if len(ordered) <= 4:
            train.extend(ordered)
            continue
        holdout_count = max(2, int(round(len(ordered) * holdout_fraction)))
        holdout_count = min(holdout_count, len(ordered) - 2)
        holdout_slice = ordered[-holdout_count:]
        train_slice = ordered[:-holdout_count]
        train.extend(train_slice)
        holdout.extend(holdout_slice)

    return tuple(train), tuple(holdout)


def _model_predictions_for_contract(
    contract: OptionContract,
    *,
    thesis: ThesisSchema,
    risk_free_rate: float,
    dividend_yield: float,
    calibrations: dict[str, Any],
    surface_fit: Any | None,
    selected_structural_models: tuple[str, ...],
) -> dict[str, float]:
    dte = max((contract.expiry - thesis.asof_date).days, 0)
    if dte <= 0 or contract.mid <= 0:
        return {}

    time_to_expiry = max(dte / 365.0, 1 / 365.0)
    forward = thesis.spot * math.exp((risk_free_rate - dividend_yield) * time_to_expiry)
    model_values: dict[str, float] = {}

    if contract.iv is not None and contract.iv > 0:
        model_values["BS_MARKET_IV"] = option_price(
            spot=thesis.spot,
            strike=contract.strike,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=contract.iv,
            right=contract.right,
            dividend_yield=dividend_yield,
        )

    if surface_fit is not None:
        theta = surface_fit.surface_state.theta_by_expiry().get(contract.expiry)
        if theta is not None:
            try:
                vol = ssvi_implied_vol(
                    math.log(contract.strike / forward),
                    theta,
                    time_to_expiry,
                    surface_fit.surface_state.parameters,
                )
                model_values["SSVI"] = option_price(
                    spot=thesis.spot,
                    strike=contract.strike,
                    time_to_expiry=time_to_expiry,
                    risk_free_rate=risk_free_rate,
                    volatility=vol,
                    right=contract.right,
                    dividend_yield=dividend_yield,
                )
            except Exception:
                pass

    bates_cal = calibrations.get("Bates")
    if bates_cal is not None:
        try:
            model_values["Bates"] = bates_price(
                thesis.spot,
                contract.strike,
                time_to_expiry,
                risk_free_rate,
                bates_cal.params,
                contract.right,
                dividend_yield,
            )
        except Exception:
            pass

    heston_cal = calibrations.get("Heston")
    if heston_cal is not None:
        try:
            model_values["Heston"] = heston_price(
                thesis.spot,
                contract.strike,
                time_to_expiry,
                risk_free_rate,
                heston_cal.params,
                contract.right,
                dividend_yield,
            )
        except Exception:
            pass

    vg_cal = calibrations.get("VG")
    if vg_cal is not None:
        try:
            model_values["VG"] = vg_price(
                thesis.spot,
                contract.strike,
                time_to_expiry,
                risk_free_rate,
                vg_cal.params,
                contract.right,
                dividend_yield,
            )
        except Exception:
            pass

    mjd_cal = calibrations.get("MJD")
    if mjd_cal is not None:
        try:
            model_values["MJD"] = mjd_price(
                thesis.spot,
                contract.strike,
                time_to_expiry,
                risk_free_rate,
                mjd_cal.params,
                contract.right,
                dividend_yield,
            )
        except Exception:
            pass

    if selected_structural_models:
        consensus_names = []
        if "SSVI" in model_values:
            consensus_names.append("SSVI")
        for name in selected_structural_models:
            if name in model_values:
                consensus_names.append(name)
        if not consensus_names and "BS_MARKET_IV" in model_values:
            consensus_names.append("BS_MARKET_IV")
        if consensus_names:
            model_values["CONSENSUS"] = sum(model_values[name] for name in consensus_names) / len(consensus_names)

    return model_values


def _metric_bucket() -> dict[str, Any]:
    return {
        "abs_errors": [],
        "signed_errors": [],
        "count": 0,
    }


def _update_metric(bucket: dict[str, Any], error: float) -> None:
    bucket["abs_errors"].append(abs(error))
    bucket["signed_errors"].append(error)
    bucket["count"] += 1


def _summarize_metric(bucket: dict[str, Any]) -> dict[str, Any]:
    abs_errors = bucket["abs_errors"]
    signed_errors = bucket["signed_errors"]
    if not abs_errors:
        return {
            "count": 0,
            "rmse": None,
            "mae": None,
            "median_abs_error": None,
            "p95_abs_error": None,
            "bias": None,
        }

    ordered = sorted(abs_errors)
    p95_index = min(len(ordered) - 1, max(0, int(math.ceil(0.95 * len(ordered))) - 1))
    rmse = math.sqrt(sum(error * error for error in signed_errors) / len(signed_errors))
    return {
        "count": bucket["count"],
        "rmse": round(rmse, 6),
        "mae": round(mean(abs_errors), 6),
        "median_abs_error": round(median(abs_errors), 6),
        "p95_abs_error": round(ordered[p95_index], 6),
        "bias": round(mean(signed_errors), 6),
    }


def _describe_model_rankings(metrics: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for name, summary in metrics.items():
        if summary["rmse"] is None:
            continue
        ranked.append({"model": name, **summary})
    ranked.sort(key=lambda item: (item["rmse"], item["mae"], item["median_abs_error"]))
    return ranked


def _run_holdout_fold(
    *,
    thesis: ThesisSchema,
    contracts: tuple[OptionContract, ...],
    holdout_fraction: float,
    risk_free_rate: float,
    dividend_yield: float,
) -> dict[str, Any]:
    train_contracts, holdout_contracts = _split_train_holdout(
        contracts,
        asof_date=thesis.asof_date,
        spot=thesis.spot,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        holdout_fraction=holdout_fraction,
    )
    train_chain = ChainIndex(train_contracts)
    search_space = build_search_space(thesis, train_chain)
    relevant_train_chain = build_relevant_subchain(thesis, train_chain, search_space)

    calibrations = calibrate_model_suite(
        relevant_train_chain,
        asof_date=thesis.asof_date,
        spot=thesis.spot,
        scope_id=thesis.symbol,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )
    surface_fit = fit_surface_state(
        relevant_train_chain,
        symbol=thesis.symbol,
        asof_date=thesis.asof_date,
        spot=thesis.spot,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )
    selected_structural_models = _select_structural_models_for_consensus(calibrations)

    metrics: dict[str, dict[str, Any]] = defaultdict(_metric_bucket)
    contract_rows: list[dict[str, Any]] = []
    for contract in holdout_contracts:
        model_values = _model_predictions_for_contract(
            contract,
            thesis=thesis,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
            calibrations=calibrations,
            surface_fit=surface_fit,
            selected_structural_models=selected_structural_models,
        )
        if not model_values:
            continue

        for name, predicted in model_values.items():
            error = predicted - contract.mid
            _update_metric(metrics[name], error)

        contract_rows.append(
            {
                "expiry": contract.expiry.isoformat(),
                "strike": contract.strike,
                "right": contract.right,
                "mid": contract.mid,
                "iv": contract.iv,
                "log_moneyness_rank": None,
                "model_values": {name: round(value, 6) for name, value in sorted(model_values.items())},
                "errors": {name: round(value - contract.mid, 6) for name, value in sorted(model_values.items())},
            }
        )

    summarized = {name: _summarize_metric(bucket) for name, bucket in metrics.items()}
    ranked_models = _describe_model_rankings(summarized)
    consensus = summarized.get("CONSENSUS", {})
    best_predictive = next((row for row in ranked_models if row["model"] != "BS_MARKET_IV"), None)
    bs_reference = summarized.get("BS_MARKET_IV")

    return {
        "holdout_fraction": holdout_fraction,
        "train_contract_count": len(train_contracts),
        "holdout_contract_count": len(holdout_contracts),
        "train_expiries": sorted({contract.expiry.isoformat() for contract in train_contracts}),
        "holdout_expiries": sorted({contract.expiry.isoformat() for contract in holdout_contracts}),
        "calibration_summary": {
            name: {
                "model": result.model,
                "rmse": result.rmse,
                "max_error": result.max_error,
                "n_quotes": result.n_quotes,
                "used_in_consensus": name in selected_structural_models,
            }
            for name, result in calibrations.items()
        },
        "surface_summary": (
            {
                "model": "SSVI",
                "quote_count": surface_fit.quote_count,
                "rmse_total_variance": surface_fit.rmse_total_variance,
                "rmse_iv": surface_fit.rmse_iv,
                "max_abs_iv_error": surface_fit.max_abs_iv_error,
                "success": surface_fit.success,
                "passed_basic_arb_checks": surface_fit.arbitrage_report.passed,
            }
            if surface_fit is not None
            else None
        ),
        "selected_structural_models": list(selected_structural_models),
        "model_rankings": ranked_models,
        "metrics": summarized,
        "consensus_metrics": consensus,
        "best_predictive_model": best_predictive,
        "bs_reference_metrics": bs_reference,
        "rows": contract_rows,
    }


def _summary_markdown(payload: dict[str, Any]) -> str:
    thesis = payload["thesis"]
    folds = payload["folds"]
    aggregate = payload["aggregate"]

    lines = [
        f"# Stratoforge Model Gating Holdout - {thesis['symbol']}",
        "",
        f"- as_of: `{thesis['asof_date']}`",
        f"- snapshot: `{payload['chain_path']}`",
        f"- methodology: `expiry-local wing holdout`",
        f"- note: this is not date-based walk-forward; the repo only has one saved SPY snapshot, so the validation holds out wings within each expiry to test cross-sectional generalization.",
        "",
        "## Conclusion",
        "",
        f"- consensus_rmse_weighted=`{aggregate['consensus_rmse_weighted']}`",
        f"- best_predictive_model=`{aggregate['best_predictive_model']}`",
        f"- consensus_vs_best_gap=`{aggregate['consensus_vs_best_gap']}`",
        f"- selected_structural_models_stability=`{aggregate['selected_structural_models_stability']}`",
        "",
    ]

    if aggregate["consensus_vs_best_gap"] is not None and aggregate["consensus_vs_best_gap"] <= 0.10:
        lines.append("- The fit-gated policy looks broadly sensible on this snapshot: consensus stays close to the best predictive model on the held-out wing quotes.")
    else:
        lines.append("- The fit-gated policy is not clearly superior on this snapshot; the validation is useful, but the available data is too thin to claim a decisive win.")

    lines.extend(["", "## Fold Results", ""])
    for fold in folds:
        lines.append(
            f"- frac=`{fold['holdout_fraction']:.2f}` "
            f"train=`{fold['train_contract_count']}` "
            f"holdout=`{fold['holdout_contract_count']}` "
            f"selected=`{fold['selected_structural_models']}` "
            f"consensus_rmse=`{fold['consensus_metrics'].get('rmse')}` "
            f"best=`{fold['best_predictive_model']['model'] if fold['best_predictive_model'] else 'n/a'}`"
        )

    lines.extend(["", "## Aggregate Models", ""])
    for row in aggregate["ranked_models"]:
        lines.append(
            f"- `{row['model']}` rmse=`{row['rmse']}` mae=`{row['mae']}` "
            f"median_abs=`{row['median_abs_error']}` p95_abs=`{row['p95_abs_error']}`"
        )

    lines.extend(["", "## Limitations", ""])
    lines.append("- There is no true temporal walk-forward here because the repo only provides one saved SPY chain snapshot.")
    lines.append("- BS with market IV is a reference baseline, not a predictive generalization model.")
    lines.append("- SSVI in this repo is slice-based, so the holdout must stay within each expiry; future-expiry extrapolation would require new interpolation logic.")

    return "\n".join(lines) + "\n"


def _aggregate_folds(folds: list[dict[str, Any]]) -> dict[str, Any]:
    weighted_counts = defaultdict(float)
    model_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    selected_models: set[tuple[str, ...]] = set()
    consensus_gaps: list[float] = []
    best_predictive_models: list[str] = []

    for fold in folds:
        consensus = fold["consensus_metrics"]
        best = fold["best_predictive_model"]
        if consensus and consensus.get("rmse") is not None:
            weighted_counts["consensus_rmse_sum"] += consensus["rmse"] * fold["holdout_contract_count"]
            weighted_counts["consensus_count"] += fold["holdout_contract_count"]
        if best and best.get("rmse") is not None:
            weighted_counts["best_rmse_sum"] += best["rmse"] * fold["holdout_contract_count"]
            weighted_counts["best_count"] += fold["holdout_contract_count"]
            best_predictive_models.append(best["model"])
            if consensus and consensus.get("rmse") is not None:
                consensus_gaps.append(consensus["rmse"] - best["rmse"])
        selected_models.add(tuple(fold["selected_structural_models"]))
        for row in fold["model_rankings"]:
            model_by_name[row["model"]].append(row)

    consensus_rmse_weighted = (
        round(weighted_counts["consensus_rmse_sum"] / weighted_counts["consensus_count"], 6)
        if weighted_counts["consensus_count"]
        else None
    )
    best_rmse_weighted = (
        round(weighted_counts["best_rmse_sum"] / weighted_counts["best_count"], 6)
        if weighted_counts["best_count"]
        else None
    )
    consensus_vs_best_gap = (
        round(consensus_rmse_weighted - best_rmse_weighted, 6)
        if consensus_rmse_weighted is not None and best_rmse_weighted is not None
        else None
    )

    ranked_models = []
    for model, rows in model_by_name.items():
        if not rows:
            continue
        ranked_models.append(
            {
                "model": model,
                "rmse": round(mean(row["rmse"] for row in rows if row["rmse"] is not None), 6),
                "mae": round(mean(row["mae"] for row in rows if row["mae"] is not None), 6),
                "median_abs_error": round(mean(row["median_abs_error"] for row in rows if row["median_abs_error"] is not None), 6),
                "p95_abs_error": round(mean(row["p95_abs_error"] for row in rows if row["p95_abs_error"] is not None), 6),
                "folds": len(rows),
            }
        )
    ranked_models.sort(key=lambda item: (item["rmse"], item["mae"], item["median_abs_error"]))

    return {
        "consensus_rmse_weighted": consensus_rmse_weighted,
        "best_predictive_rmse_weighted": best_rmse_weighted,
        "consensus_vs_best_gap": consensus_vs_best_gap,
        "best_predictive_model": max(set(best_predictive_models), key=best_predictive_models.count) if best_predictive_models else None,
        "selected_structural_models_stability": sorted({"|".join(models) for models in selected_models}),
        "ranked_models": ranked_models,
        "consensus_gaps": consensus_gaps,
    }


def _write_outputs(payload: dict[str, Any], *, output_path: str | Path | None) -> tuple[Path, Path]:
    base = Path(output_path) if output_path is not None else _default_output_base(ThesisSchema.from_dict(payload["thesis"]))
    if base.suffix:
        json_path = base
        md_path = base.with_suffix(".md")
    else:
        json_path = base.with_suffix(".json")
        md_path = base.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_summary_markdown(payload), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Stratoforge model gating with expiry-local wing holdout on a saved SPY snapshot.",
    )
    parser.add_argument("--thesis", default=str(DEFAULT_THESIS), help="Path to thesis JSON.")
    parser.add_argument("--chain", default=str(DEFAULT_CHAIN), help="Path to option chain JSON.")
    parser.add_argument(
        "--holdout-fractions",
        type=float,
        nargs="*",
        default=None,
        help="Wing holdout fractions per expiry. Defaults to 0.15 0.25 0.35.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_BASENAME), help="Base output path.")
    parser.add_argument("--risk-free-rate", type=float, default=0.045, help="Risk-free rate.")
    parser.add_argument("--dividend-yield", type=float, default=0.0, help="Dividend yield.")
    args = parser.parse_args()

    thesis = _load_thesis(args.thesis)
    contracts = load_option_contracts(args.chain)
    fractions = _parse_fractions(args.holdout_fractions)
    folds = [
        _run_holdout_fold(
            thesis=thesis,
            contracts=contracts,
            holdout_fraction=fraction,
            risk_free_rate=args.risk_free_rate,
            dividend_yield=args.dividend_yield,
        )
        for fraction in fractions
    ]
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "thesis": thesis.to_dict(),
        "chain_path": str(Path(args.chain)),
        "holdout_fractions": list(fractions),
        "folds": folds,
        "aggregate": _aggregate_folds(folds),
    }
    json_path, md_path = _write_outputs(payload, output_path=args.output)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Consensus weighted RMSE: {payload['aggregate']['consensus_rmse_weighted']}")
    print(f"Best predictive weighted RMSE: {payload['aggregate']['best_predictive_rmse_weighted']}")


if __name__ == "__main__":
    main()
