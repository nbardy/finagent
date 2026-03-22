from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stratoforge.domain.contracts import ChainIndex, load_option_contracts
from stratoforge.domain.thesis import ThesisSchema
from stratoforge.scoring import run_scored_stratoforge


ANALYSIS_ROOT = REPO_ROOT / "analysis"


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


def _default_output_base(thesis: ThesisSchema) -> Path:
    date_dir = ANALYSIS_ROOT / thesis.asof_date.isoformat()
    date_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    topic = _slugify(f"stratoforge_scored_{thesis.symbol}_{thesis.objective}_{timestamp}")
    return date_dir / topic


def _load_thesis(path: str | Path) -> ThesisSchema:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return ThesisSchema.from_dict(payload)


def _summary_markdown(payload: dict, *, top_n: int) -> str:
    thesis = payload["thesis"]
    ranked = payload["ranked_candidates"]
    scenario_nodes = payload["scenario_nodes"]
    family_counts = Counter(candidate["family"] for candidate in ranked)

    lines = [
        f"# Stratoforge Scored Universe — {thesis['symbol']}",
        "",
        f"- as_of: `{thesis['asof_date']}`",
        f"- objective: `{thesis['objective']}`",
        f"- spot: `{thesis['spot']}`",
        f"- enumerated_candidates: `{payload['candidate_count']}`",
        f"- ranked_candidates: `{payload['ranked_candidate_count']}`",
        f"- filtered_out_after_scoring: `{payload['unranked_filtered_out']}`",
        f"- contract_tensor_contract_count: `{payload['contract_tensor_contract_count']}`",
        "",
        "## Scenarios",
        "",
    ]
    for scenario in scenario_nodes:
        lines.append(
            f"- `{scenario['label']}` "
            f"prob=`{scenario['probability']:.2%}` "
            f"days=`{scenario['horizon_days']}` "
            f"move=`{scenario['spot_move_pct']:.2%}` "
            f"target_spot=`{scenario['target_spot']}` "
            f"path=`{scenario['path_model']}`"
        )

    lines.extend(["", "## Surface", ""])
    surface_summary = payload.get("surface_summary")
    if surface_summary:
        lines.append(
            f"- `{surface_summary['model']}` "
            f"rmse_iv=`{surface_summary['rmse_iv']}` "
            f"max_abs_iv_error=`{surface_summary['max_abs_iv_error']}` "
            f"n_quotes=`{surface_summary['quote_count']}` "
            f"arb_ok=`{surface_summary['passed_basic_arb_checks']}`"
        )
        lines.append(
            f"- params "
            f"`rho={surface_summary['parameters']['rho']}` "
            f"`eta={surface_summary['parameters']['eta']}` "
            f"`lam={surface_summary['parameters']['lam']}`"
        )
    else:
        lines.append("- No SSVI surface fit was available.")

    lines.extend(["", "## Calibrations", ""])
    if payload["calibration_summary"]:
        for name, summary in sorted(payload["calibration_summary"].items()):
            lines.append(
                f"- `{name}` "
                f"rmse=`{summary['rmse']}` "
                f"max_error=`{summary['max_error']}` "
                f"n_quotes=`{summary['n_quotes']}` "
                f"used_in_consensus=`{summary.get('used_in_consensus', False)}`"
            )
    else:
        lines.append("- No stochastic calibrations were available; ranking fell back to BS or market-mid fallback.")

    lines.extend(["", "## Ranked Family Counts", ""])
    for family, count in sorted(family_counts.items()):
        lines.append(f"- `{family}`: `{count}`")

    lines.extend(["", f"## Top {min(top_n, len(ranked))}", ""])
    for candidate in ranked[:top_n]:
        lines.append(
            f"- `#{candidate['rank']}` "
            f"`{candidate['family']}` "
            f"`EV={candidate['expected_value']}` "
            f"`ROC={candidate['return_on_capital']}` "
            f"`P(loss)={candidate['probability_of_loss']:.2%}` "
            f"`max_loss={candidate['max_loss']}` "
            f"`{candidate['name']}`"
        )
    return "\n".join(lines) + "\n"


def _write_outputs(payload: dict, *, thesis: ThesisSchema, output_path: str | Path | None, top_n: int) -> tuple[Path, Path]:
    base = Path(output_path) if output_path is not None else _default_output_base(thesis)
    if base.suffix:
        json_path = base
        md_path = base.with_suffix(".md")
    else:
        json_path = base.with_suffix(".json")
        md_path = base.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_summary_markdown(payload, top_n=top_n), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enumerate and score a thesis-driven options universe for Stratoforge.",
    )
    parser.add_argument("--thesis", required=True, help="Path to thesis JSON.")
    parser.add_argument("--chain", required=True, help="Path to option chain JSON.")
    parser.add_argument(
        "--family",
        action="append",
        default=None,
        help="Optional family id filter. Repeat to include multiple.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. Defaults to analysis/{date}/stratoforge_scored_{symbol}_{objective}.json",
    )
    parser.add_argument("--risk-free-rate", type=float, default=0.045, help="Risk-free rate for scenario pricing.")
    parser.add_argument("--dividend-yield", type=float, default=0.0, help="Dividend yield for scenario pricing.")
    parser.add_argument("--top", type=int, default=20, help="How many ranked candidates to print and summarize.")
    parser.add_argument(
        "--no-calibrate",
        action="store_true",
        help="Skip Heston/VG/MJD calibration and score with BS / market-mid fallback only.",
    )
    args = parser.parse_args()

    thesis = _load_thesis(args.thesis)
    if args.family:
        thesis = ThesisSchema(
            symbol=thesis.symbol,
            asof_date=thesis.asof_date,
            spot=thesis.spot,
            objective=thesis.objective,
            branches=thesis.branches,
            constraints=thesis.constraints,
            allowed_families=tuple(args.family),
            notes=thesis.notes,
        )

    contracts = load_option_contracts(args.chain)
    full_chain = ChainIndex(contracts)
    payload = run_scored_stratoforge(
        thesis,
        full_chain,
        risk_free_rate=args.risk_free_rate,
        dividend_yield=args.dividend_yield,
        use_calibrations=not args.no_calibrate,
    )
    json_path, md_path = _write_outputs(payload, thesis=thesis, output_path=args.output, top_n=args.top)

    print(f"Ranked {payload['ranked_candidate_count']} candidates from {payload['candidate_count']} enumerated setups.")
    print(f"JSON: {json_path}")
    print(f"Summary: {md_path}")
    for candidate in payload["ranked_candidates"][: args.top]:
        print(
            f"#{candidate['rank']:>2}  "
            f"{candidate['family']:<28}  "
            f"EV={candidate['expected_value']:>8.2f}  "
            f"ROC={candidate['return_on_capital']:>8.4f}  "
            f"P(loss)={candidate['probability_of_loss']:>7.2%}  "
            f"{candidate['name']}"
        )


if __name__ == "__main__":
    main()
