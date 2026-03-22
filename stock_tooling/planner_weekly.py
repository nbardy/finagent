from __future__ import annotations

import argparse
import json
from datetime import datetime

from stratoforge.pricing import (
    fetch_weekly_candidates,
    load_cover_inventory,
    nearest_weekly_expiry,
    price_option_probe,
    project_weekly_candidate_scenario,
)


def _candidate_by_strike(candidates: list[dict], strike: float) -> dict:
    for candidate in candidates:
        if abs(float(candidate["contract"].strike) - float(strike)) < 1e-9:
            return candidate
    raise RuntimeError(f"No candidate found for strike {strike:.2f}.")


def _pick_candidate(candidates: list[dict], strike: float | None) -> dict:
    if not candidates:
        raise RuntimeError("No weekly candidates matched the requested filters.")
    if strike is not None:
        return _candidate_by_strike(candidates, strike)
    return candidates[0]


def _proposal_for_candidate(
    candidate: dict,
    qty_cap: int | None,
    probe_qty: int,
    tif: str,
    spot_move_pct: float,
    iv_multiplier: float,
    iv_shift: float,
) -> dict:
    total_qty = candidate["safe_qty"]
    if qty_cap is not None:
        total_qty = min(total_qty, int(qty_cap))
    if total_qty <= 0:
        raise RuntimeError("Selected weekly candidate has no quantity available after qty cap.")

    market = candidate["market"]
    scenario = None
    steps = tuple(probe["ticks_from_anchor"] for probe in candidate["probe_proposal"]["probes"])
    if spot_move_pct != 0.0 or iv_multiplier != 1.0 or iv_shift != 0.0:
        scenario = project_weekly_candidate_scenario(
            candidate=candidate,
            spot_move_pct=spot_move_pct,
            iv_multiplier=iv_multiplier,
            iv_shift=iv_shift,
        )
        market = scenario["proxy_market"]
        steps = scenario["probe_steps"]

    proposal = price_option_probe(
        contract=candidate["contract"],
        market=market,
        total_qty=total_qty,
        action="SELL",
        probe_qty=probe_qty,
        steps=steps,
        tif=tif,
    )
    proposal["weekly_plan"] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "safe_cover_quantity": candidate["safe_qty"],
        "selected_quantity": total_qty,
        "estimated_credit_mid": round(candidate["market"].mid * total_qty * 100.0, 2),
        "estimated_credit_ask": round(candidate["market"].ask * total_qty * 100.0, 2),
        "theoretical_value_market_iv": candidate["theoretical_value_market_iv"],
        "theoretical_value_rv30": candidate["theoretical_value_rv30"],
        "delta_market": candidate["delta_market"],
        "prob_otm_estimate": candidate["prob_otm_estimate"],
        "edge_vs_rv30": candidate["edge_vs_rv30"],
        "cover_buckets": candidate["cover_buckets"],
    }
    if scenario is not None:
        proposal["weekly_plan"]["scenario"] = {
            "spot_move_pct": scenario["spot_move_pct"],
            "scenario_spot": scenario["scenario_spot"],
            "scenario_iv": scenario["scenario_iv"],
            "base_model": scenario["base_model"],
            "scenario_model": scenario["scenario_model"],
            "model_shift": scenario["model_shift"],
            "delta_market": scenario["delta_market"],
            "prob_otm_estimate": scenario["prob_otm_estimate"],
            "estimated_credit_mid": round(market.mid * total_qty * 100.0, 2),
            "estimated_credit_ask": round(market.ask * total_qty * 100.0, 2),
        }
    return proposal


def _print_candidate_table(result: dict, candidates: list[dict], top: int) -> None:
    print(f"\nEWY weekly scan for {result['expiry']}  spot=${result['spot']:.2f}")
    print(
        f"Rate={result['risk_free_rate']:.3%}  "
        f"RV30={result['realized_volatility_30d']:.2%}"
    )
    print("")
    print("Strike  Bid   Ask   Mid   SafeQty  Delta  P(OTM)  Credit@Mid  Score")
    print("------  ----  ----  ----  -------  -----  ------  ----------  -----")
    for candidate in candidates[:top]:
        market = candidate["market"]
        contract = candidate["contract"]
        print(
            f"{contract.strike:>6.1f}  "
            f"{market.bid:>4.2f}  "
            f"{market.ask:>4.2f}  "
            f"{market.mid:>4.2f}  "
            f"{candidate['safe_qty']:>7d}  "
            f"{candidate['delta_market']:>5.2f}  "
            f"{candidate['prob_otm_estimate']:>6.2f}  "
            f"${candidate['estimated_credit_mid']:>9,.0f}  "
            f"{candidate['score']:>5.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build open-ready weekly EWY call sale probes")
    parser.add_argument("--symbol", default="EWY")
    parser.add_argument("--portfolio-state", default="config/portfolio_state.json")
    parser.add_argument("--expiry", default=None, help="Weekly expiry YYYYMMDD; defaults to nearest 3-10 DTE")
    parser.add_argument("--min-dte", type=int, default=3)
    parser.add_argument("--max-dte", type=int, default=10)
    parser.add_argument("--strike", type=float, default=None, help="Pick an exact strike instead of best-ranked")
    parser.add_argument("--min-strike", type=float, default=None)
    parser.add_argument("--max-strike", type=float, default=None)
    parser.add_argument("--qty-cap", type=int, default=None, help="Optional cap below safe cover quantity")
    parser.add_argument("--probe-qty", type=int, default=1)
    parser.add_argument("--top", type=int, default=8, help="How many candidates to print")
    parser.add_argument("--risk-free", type=float, default=0.045)
    parser.add_argument("--dividend-yield", type=float, default=0.0)
    parser.add_argument("--right", default="C")
    parser.add_argument("--tif", default="DAY")
    parser.add_argument("--scenario-spot-move-pct", type=float, default=0.0)
    parser.add_argument("--scenario-iv-multiplier", type=float, default=1.0)
    parser.add_argument("--scenario-iv-shift", type=float, default=0.0)
    parser.add_argument("--output", default="weekly_probe_proposal.json")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    expiry = args.expiry or nearest_weekly_expiry(symbol, min_dte=args.min_dte, max_dte=args.max_dte)
    cover_buckets = load_cover_inventory(args.portfolio_state)
    result = fetch_weekly_candidates(
        symbol=symbol,
        expiry=expiry,
        cover_buckets=cover_buckets,
        min_strike=args.min_strike,
        max_strike=args.max_strike,
        right=args.right.upper(),
        default_rate=args.risk_free,
        dividend_yield=args.dividend_yield,
    )

    candidates = result["candidates"]
    _print_candidate_table(result, candidates, args.top)

    selected = _pick_candidate(candidates, args.strike)
    proposal = _proposal_for_candidate(
        candidate=selected,
        qty_cap=args.qty_cap,
        probe_qty=args.probe_qty,
        tif=args.tif,
        spot_move_pct=args.scenario_spot_move_pct,
        iv_multiplier=args.scenario_iv_multiplier,
        iv_shift=args.scenario_iv_shift,
    )

    with open(args.output, "w") as handle:
        json.dump(proposal, handle, indent=2)

    contract = selected["contract"]
    market = selected["market"]
    selected_qty = proposal["weekly_plan"]["selected_quantity"]
    print("\nSelected:")
    print(
        f"  SELL {selected_qty}x {contract.symbol} {contract.strike:.1f}{contract.right} "
        f"{contract.expiry}"
    )
    print(
        f"  Market=[{market.bid:.2f} x {market.ask:.2f}]  mid=${market.mid:.2f}  "
        f"TV@IV=${selected['theoretical_value_market_iv']:.2f}  "
        f"P(OTM)~{selected['prob_otm_estimate']:.0%}"
    )
    print(
        f"  Credit@mid~${proposal['weekly_plan']['estimated_credit_mid']:,.0f}  "
        f"Credit@ask~${proposal['weekly_plan']['estimated_credit_ask']:,.0f}"
    )
    if "scenario" in proposal["weekly_plan"]:
        scenario = proposal["weekly_plan"]["scenario"]
        print(
            f"  Scenario: spot {scenario['spot_move_pct']:+.1%} -> "
            f"${scenario['scenario_spot']:.2f}, IV {scenario['scenario_iv']:.1%}, "
            f"proxy ask ${proposal['market']['ask']:.2f}"
        )
    print("  Probes:")
    for probe in proposal["probes"]:
        print(
            f"    {probe['quantity']}x @ ${probe['lmtPrice']:.2f} "
            f"(+{probe['ticks_from_anchor']} ticks)"
        )
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
