"""
Scenario return matrix for any stock — compares instruments across outcomes.

Given a budget and a set of scenarios (stock moves 2x, 4x, 10x, etc.),
computes the return for each instrument type: stock, ATM LEAP, OTM LEAP,
debit spreads. Outputs a matrix showing ROI, dollar return, and risk stats.

Usage:
    uv run python scenario_analyzer.py                           # uses scenario_input.json
    uv run python scenario_analyzer.py --input my_scenarios.json
    uv run python scenario_analyzer.py --spot 50 --iv 0.60       # override, skip IBKR

The input JSON spec is documented in scenario_input.json.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

from stratoforge.pricing.black_scholes import option_price, implied_volatility_from_price
from stratoforge.pricing.heston import HestonParams, heston_price


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    label: str
    move: float        # fractional: 1.0 = 2x, 3.0 = 4x, -0.3 = -30%
    probability: float

    @property
    def terminal_spot_factor(self) -> float:
        return 1.0 + self.move


@dataclass(frozen=True)
class InstrumentResult:
    """Return profile for one instrument in one scenario."""
    entry_cost: float       # per-unit cost to enter
    exit_value: float       # per-unit value at scenario
    quantity: float         # how many units the budget buys
    dollar_pnl: float       # total PnL
    pct_return: float       # percentage return
    max_loss_pct: float     # worst case (for options: -100%)


# ---------------------------------------------------------------------------
# Pricing engines
# ---------------------------------------------------------------------------

def price_option_at_scenario(
    spot: float,
    strike: float,
    move: float,
    iv: float,
    T_entry: float,
    T_exit: float,
    r: float,
    right: str = "C",
    model: str = "bs",
    heston_params: HestonParams | None = None,
) -> tuple[float, float]:
    """
    Price an option at entry and at a scenario exit.

    Returns (entry_price, exit_price).

    At exit, the stock has moved by `move` (fractional), and
    the option has T_exit time remaining.

    IV adjustment at exit: mean-revert toward long-run vol.
    When stock rallies, IV typically drops (inverse correlation).
    Simple model: exit_iv = iv * (1 - move * 0.15), clamped to [0.15, iv*1.5]
    """
    terminal_spot = spot * (1.0 + move)

    # IV adjustment: big rally → IV compresses, big drop → IV expands
    exit_iv = iv * (1.0 - move * 0.15)
    exit_iv = max(0.15, min(exit_iv, iv * 1.5))

    if model == "heston" and heston_params is not None:
        entry = heston_price(spot, strike, T_entry, r, heston_params, right)
        # For exit, rebuild params with adjusted v0
        exit_params = HestonParams(
            v0=exit_iv ** 2,
            theta=heston_params.theta,
            kappa=heston_params.kappa,
            xi=heston_params.xi,
            rho=heston_params.rho,
        )
        exit_val = heston_price(terminal_spot, strike, T_exit, r, exit_params, right)
    else:
        entry = option_price(spot, strike, T_entry, r, iv, right)
        exit_val = option_price(terminal_spot, strike, T_exit, r, exit_iv, right)

    return entry, exit_val


# ---------------------------------------------------------------------------
# Instrument evaluators
# ---------------------------------------------------------------------------

def evaluate_stock(
    spot: float, budget: float, scenario: Scenario
) -> InstrumentResult:
    qty = budget / spot
    terminal = spot * scenario.terminal_spot_factor
    pnl = (terminal - spot) * qty
    pct = scenario.move * 100
    return InstrumentResult(
        entry_cost=spot, exit_value=terminal, quantity=qty,
        dollar_pnl=round(pnl, 2), pct_return=round(pct, 1),
        max_loss_pct=-100.0,  # stock can go to zero
    )


def evaluate_call(
    spot: float, strike: float, budget: float,
    scenario: Scenario, iv: float,
    T_entry: float, T_exit: float, r: float,
    model: str, heston_params: HestonParams | None,
) -> InstrumentResult:
    entry, exit_val = price_option_at_scenario(
        spot, strike, scenario.move, iv, T_entry, T_exit, r,
        "C", model, heston_params,
    )
    if entry <= 0:
        return InstrumentResult(0, 0, 0, 0, 0, -100.0)

    # Cost per contract = entry * 100 shares
    cost_per_contract = entry * 100
    qty = budget / cost_per_contract
    pnl = (exit_val - entry) * 100 * qty
    pct = (exit_val - entry) / entry * 100

    return InstrumentResult(
        entry_cost=round(entry, 4),
        exit_value=round(exit_val, 4),
        quantity=round(qty, 2),
        dollar_pnl=round(pnl, 2),
        pct_return=round(pct, 1),
        max_loss_pct=-100.0,
    )


def evaluate_debit_spread(
    spot: float, long_strike: float, short_strike: float,
    budget: float, scenario: Scenario, iv: float,
    T_entry: float, T_exit: float, r: float,
    model: str, heston_params: HestonParams | None,
) -> InstrumentResult:
    long_entry, long_exit = price_option_at_scenario(
        spot, long_strike, scenario.move, iv, T_entry, T_exit, r,
        "C", model, heston_params,
    )
    short_entry, short_exit = price_option_at_scenario(
        spot, short_strike, scenario.move, iv, T_entry, T_exit, r,
        "C", model, heston_params,
    )

    # Net debit = long cost - short credit
    net_debit = long_entry - short_entry
    if net_debit <= 0:
        return InstrumentResult(0, 0, 0, 0, 0, -100.0)

    # Net value at exit
    net_exit = long_exit - short_exit

    cost_per_spread = net_debit * 100
    qty = budget / cost_per_spread
    pnl = (net_exit - net_debit) * 100 * qty
    pct = (net_exit - net_debit) / net_debit * 100

    return InstrumentResult(
        entry_cost=round(net_debit, 4),
        exit_value=round(net_exit, 4),
        quantity=round(qty, 2),
        dollar_pnl=round(pnl, 2),
        pct_return=round(pct, 1),
        max_loss_pct=-100.0,
    )


# ---------------------------------------------------------------------------
# Main analyzer
# ---------------------------------------------------------------------------

def analyze(config: dict) -> dict:
    symbol = config["symbol"]
    budget = config["budget"]
    settings = config.get("settings", {})
    r = settings.get("risk_free_rate", 0.045)
    hold_days = settings.get("hold_period_days", 180)
    pricing_model = settings.get("pricing_model", "bs")
    fetch_live = settings.get("fetch_live_quotes", False)

    # Get spot and IV
    spot = config.get("spot")
    iv = config.get("iv")

    if fetch_live and (spot is None or iv is None):
        from ibkr import connect, get_spot, get_option_quotes
        with connect(client_id=17) as ib:
            if spot is None:
                spot = get_spot(ib, symbol)
            if iv is None:
                # Get ATM IV from nearest LEAP
                expiry = config["instruments"][1].get("expiry", "20280121")
                atm_strike = round(spot / 5) * 5  # round to nearest $5
                quotes = get_option_quotes(ib, symbol, [(atm_strike, expiry, "C")])
                if quotes and quotes[0].iv > 0:
                    iv = quotes[0].iv
                else:
                    iv = 0.50
                    print(f"  WARNING: No IV from IBKR, using {iv:.0%}")
            print(f"  {symbol}: spot=${spot:.2f}, IV={iv:.1%}")

    if spot is None or iv is None:
        raise ValueError("spot and iv must be provided or fetch_live_quotes must be true")

    # Parse scenarios
    scenarios = [Scenario(**s) for s in config["scenarios"]]

    # Normalize probabilities
    total_prob = sum(s.probability for s in scenarios)
    if abs(total_prob - 1.0) > 0.01:
        print(f"  WARNING: probabilities sum to {total_prob:.2f}, normalizing")
        scenarios = [
            Scenario(s.label, s.move, s.probability / total_prob)
            for s in scenarios
        ]

    # Parse instruments
    instruments = config["instruments"]

    # Time parameters
    # Find the longest expiry across all instruments for T_entry
    expiries = set()
    for inst in instruments:
        if "expiry" in inst:
            expiries.add(inst["expiry"])
    # Default expiry
    default_expiry = max(expiries) if expiries else "20280121"

    # Heston params — use calibrated values from config, or skip Heston
    heston_cfg = settings.get("heston_params")
    if heston_cfg is not None:
        heston_params = HestonParams(**heston_cfg)
    elif pricing_model == "heston":
        raise ValueError(
            "pricing_model='heston' requires settings.heston_params "
            "with calibrated v0, theta, kappa, xi, rho — no silent defaults"
        )
    else:
        heston_params = None  # BS mode, Heston not needed

    # Build the matrix
    # matrix[instrument_label][scenario_label] = InstrumentResult
    matrix: dict[str, dict[str, InstrumentResult]] = {}

    for inst in instruments:
        label = inst["label"]
        inst_type = inst["type"]
        expiry = inst.get("expiry", default_expiry)

        from stratoforge.pricing.models import dte_and_time_to_expiry
        dte, T_entry = dte_and_time_to_expiry(expiry)
        T_exit = max((dte - hold_days) / 365, 0.001)

        model = pricing_model if pricing_model != "both" else "bs"
        hp = heston_params if model == "heston" else None

        row: dict[str, InstrumentResult] = {}

        for scenario in scenarios:
            if inst_type == "stock":
                result = evaluate_stock(spot, budget, scenario)

            elif inst_type == "call":
                strike = round(spot * inst["strike_pct"] / 5) * 5  # round to $5
                result = evaluate_call(
                    spot, strike, budget, scenario, iv,
                    T_entry, T_exit, r, model, hp,
                )

            elif inst_type == "debit_spread":
                long_strike = round(spot * inst["long_strike_pct"] / 5) * 5
                short_strike = round(spot * inst["short_strike_pct"] / 5) * 5
                result = evaluate_debit_spread(
                    spot, long_strike, short_strike, budget, scenario, iv,
                    T_entry, T_exit, r, model, hp,
                )
            else:
                continue

            row[scenario.label] = result

        matrix[label] = row

    # Compute summary stats per instrument
    summaries: dict[str, dict] = {}
    for label, row in matrix.items():
        returns = []
        weighted_return = 0.0
        for scenario in scenarios:
            r_val = row[scenario.label]
            returns.append(r_val.pct_return)
            weighted_return += r_val.pct_return * scenario.probability

        prob_loss = sum(
            s.probability for s in scenarios
            if row[s.label].pct_return < 0
        )
        dollar_at_exit = budget + weighted_return / 100 * budget

        summaries[label] = {
            "expected_return_pct": round(weighted_return, 1),
            "prob_loss": round(prob_loss * 100, 1),
            "worst_return_pct": round(min(returns), 1),
            "best_return_pct": round(max(returns), 1),
            "budget_becomes": round(dollar_at_exit, 0),
        }

    # Print the matrix
    scenario_labels = [s.label for s in scenarios]
    inst_labels = [inst["label"] for inst in instruments]
    col_width = 12

    print(f"\n{'='*90}")
    print(f"  {symbol} SCENARIO MATRIX — ${budget:,.0f} budget, {hold_days}d hold")
    print(f"  Spot: ${spot:.2f}  IV: {iv:.1%}  Model: {pricing_model}")
    print(f"{'='*90}")

    # Header
    header = f"  {'':>18}"
    for sl in scenario_labels:
        header += f"{sl:>{col_width}}"
    header += f"  {'E[R]':>{col_width}}{'P(loss)':>{col_width}}{'$10K→':>{col_width}}"
    print(header)
    print(f"  {'─' * (18 + col_width * (len(scenario_labels) + 3) + 2)}")

    for label in inst_labels:
        row = matrix[label]
        summary = summaries[label]
        line = f"  {label:>18}"
        for sl in scenario_labels:
            pct = row[sl].pct_return
            line += f"{pct:>+{col_width}.0f}%"
        line += f"  {summary['expected_return_pct']:>+{col_width}.0f}%"
        line += f"{summary['prob_loss']:>{col_width}.0f}%"
        line += f"  ${summary['budget_becomes']:>{col_width - 1},.0f}"
        print(line)

    print(f"  {'─' * (18 + col_width * (len(scenario_labels) + 3) + 2)}")

    # Dollar PnL row
    print(f"\n  Dollar P&L on ${budget:,.0f}:")
    header2 = f"  {'':>18}"
    for sl in scenario_labels:
        header2 += f"{sl:>{col_width}}"
    print(header2)
    print(f"  {'─' * (18 + col_width * len(scenario_labels))}")

    for label in inst_labels:
        row = matrix[label]
        line = f"  {label:>18}"
        for sl in scenario_labels:
            pnl = row[sl].dollar_pnl
            line += f"{'${:>+,.0f}'.format(pnl):>{col_width}}"
        print(line)

    print(f"\n{'='*90}")

    # Instrument details
    print(f"\n  INSTRUMENT DETAILS:")
    for inst in instruments:
        label = inst["label"]
        if inst["type"] == "stock":
            qty = budget / spot
            print(f"  {label}: {qty:.1f} shares @ ${spot:.2f}")
        elif inst["type"] == "call":
            strike = round(spot * inst["strike_pct"] / 5) * 5
            entry = matrix[label][scenarios[0].label].entry_cost
            qty = matrix[label][scenarios[0].label].quantity
            print(f"  {label}: {qty:.1f} contracts, {strike}C @ ${entry:.2f}/sh (${entry*100:.0f}/contract)")
        elif inst["type"] == "debit_spread":
            long_strike = round(spot * inst["long_strike_pct"] / 5) * 5
            short_strike = round(spot * inst["short_strike_pct"] / 5) * 5
            entry = matrix[label][scenarios[0].label].entry_cost
            qty = matrix[label][scenarios[0].label].quantity
            print(f"  {label}: {qty:.1f} spreads, {long_strike}C/{short_strike}C @ ${entry:.2f} net debit")

    print(f"{'='*90}")

    # Build output JSON
    output = {
        "symbol": symbol,
        "spot": spot,
        "iv": round(iv, 4),
        "budget": budget,
        "hold_period_days": hold_days,
        "pricing_model": pricing_model,
        "scenarios": [
            {"label": s.label, "move": s.move, "probability": s.probability,
             "terminal_spot": round(spot * s.terminal_spot_factor, 2)}
            for s in scenarios
        ],
        "matrix": {
            label: {
                sl: {
                    "pct_return": row[sl].pct_return,
                    "dollar_pnl": row[sl].dollar_pnl,
                    "entry_cost": row[sl].entry_cost,
                    "exit_value": row[sl].exit_value,
                    "quantity": row[sl].quantity,
                }
                for sl in scenario_labels
            }
            for label, row in matrix.items()
        },
        "summaries": summaries,
    }

    output_file = config.get("output_file", "scenario_matrix.json")
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Saved to {output_file}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Scenario return matrix analyzer")
    parser.add_argument("--input", default="scenario_input.json", help="Input config JSON")
    parser.add_argument("--spot", type=float, default=None, help="Override spot price")
    parser.add_argument("--iv", type=float, default=None, help="Override IV (e.g. 0.60)")
    parser.add_argument("--budget", type=float, default=None, help="Override budget")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    with open(args.input) as f:
        config = json.load(f)

    if args.spot is not None:
        config["spot"] = args.spot
    if args.iv is not None:
        config["iv"] = args.iv
    if args.budget is not None:
        config["budget"] = args.budget
    if args.output is not None:
        config["output_file"] = args.output

    analyze(config)


if __name__ == "__main__":
    main()
