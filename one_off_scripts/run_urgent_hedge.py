from __future__ import annotations

import argparse

from helpers.urgent_hedge import (
    build_candidate_universe,
    build_execution_bundle,
    get_us_equity_option_session_state,
    load_macro_scenarios,
    load_portfolio_book,
    write_execution_bundle,
)
from helpers.urgent_hedge_types import ChasePolicy


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank urgent EWY hedge candidates and emit executable order files.")
    parser.add_argument("--macro", required=True, help="Macro scenario JSON.")
    parser.add_argument("--portfolio", default=None, help="Optional portfolio JSON for downside coverage scoring.")
    parser.add_argument("--symbol", default=None, help="Override symbol from the macro file.")
    parser.add_argument("--budget", type=float, required=True, help="Max dollars to spend on the hedge.")
    parser.add_argument("--output-prefix", default="urgent_hedge")
    parser.add_argument("--output-dir", default=".")
    parser.add_argument(
        "--open-max-debit",
        type=float,
        default=None,
        help="Optional max unit debit for the open-ready ladder.",
    )
    args = parser.parse_args()

    scenario_set = load_macro_scenarios(args.macro)
    symbol = (args.symbol or scenario_set.symbol).upper()
    book = None
    if args.portfolio:
        book = load_portfolio_book(args.portfolio, default_symbol=symbol)
    elif scenario_set.symbol == symbol:
        try:
            book = load_portfolio_book(args.macro, default_symbol=symbol)
        except Exception:
            book = None

    candidates = build_candidate_universe(
        symbol=symbol,
        scenario_set=scenario_set,
        budget=args.budget,
        book=book,
    )
    if not candidates:
        raise RuntimeError(f"No hedge candidates could be priced for {symbol}.")

    selected = candidates[0]
    session = get_us_equity_option_session_state()
    chase_policy = None
    if args.open_max_debit is not None:
        chase_policy = ChasePolicy(
            max_rounds=3,
            tick_up_per_round=0.05,
            max_unit_debit=float(args.open_max_debit),
        )
    plan, artifacts = build_execution_bundle(
        candidate=selected,
        scenario_set=scenario_set,
        budget=args.budget,
        output_prefix=args.output_prefix,
        output_dir=args.output_dir,
        session=session,
        chase_policy=chase_policy,
    )
    paths = write_execution_bundle(
        plan=plan,
        artifacts=artifacts,
        ranked_candidates=candidates,
        output_prefix=args.output_prefix,
        output_dir=args.output_dir,
    )

    print(f"Selected: {selected.spec.name}")
    print(
        f"Qty={selected.target_quantity}  "
        f"Debit~${selected.entry_debit:,.0f}  "
        f"Coverage={selected.conditional_downside_coverage_pct:.1f}%  "
        f"Carry={selected.carry_loss_pct:.1f}%  "
        f"Score={selected.score:.2f}"
    )
    if selected.expected_combined_pnl is not None:
        print(
            f"Expected hedge PnL={selected.expected_pnl:+,.0f}  "
            f"Expected combined PnL={selected.expected_combined_pnl:+,.0f}"
        )
    else:
        print(f"Expected hedge PnL={selected.expected_pnl:+,.0f}")
    print(f"Session mode: {session.mode}  recommended artifact: {plan.recommended_artifact}")
    print(f"Ranked: {paths['ranked']}")
    print(f"Selected plan: {paths['selected']}")
    print(f"Probe: {paths['probe']}")
    print(f"Full: {paths['full']}")
    print(f"Open-ready: {paths['open_ready']}")


if __name__ == "__main__":
    main()
