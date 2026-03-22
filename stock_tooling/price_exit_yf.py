"""
Yahoo-backed CLI for pricing option exits.

Fallback-only helper.

The repo direction is IBKR-first for live pricing. Prefer
`stock_tooling/price_exit.py` whenever IBKR quotes are available. Use this file
only when you intentionally want a Yahoo-backed fallback path.

The pricing logic lives in the `option_pricing` package. This file is only a
thin command-line wrapper around those reusable modules.
"""

from __future__ import annotations

import argparse
import json

from stratoforge.pricing import price_option_exit
from stratoforge.pricing.models import display_expiry
from stratoforge.pricing.yahoo import fetch_option_snapshot


def price_exit_yf(
    symbol: str,
    expiry: str,
    total_qty: int,
    strike: float | None,
    n_tranches: int,
    default_rate: float,
    dividend_yield: float,
    output_file: str,
) -> dict:
    print("WARNING: price_exit_yf.py is a fallback path. Prefer stock_tooling/price_exit.py for IBKR-first pricing.")
    contract, market, nearby = fetch_option_snapshot(
        symbol=symbol,
        expiry=expiry,
        strike=strike,
        right="C",
        default_rate=default_rate,
        dividend_yield=dividend_yield,
    )
    proposal = price_option_exit(
        contract=contract,
        market=market,
        total_qty=total_qty,
        action="SELL",
        n_tranches=n_tranches,
    )

    with open(output_file, "w") as handle:
        json.dump(proposal, handle, indent=2)

    print(f"\n{contract.symbol} spot: ${proposal['spot_at_pricing']:.2f}")
    print(f"Expiry: {display_expiry(contract.expiry)}  DTE={proposal['metrics']['dte']}")
    if strike is None:
        print("Selected strike: nearest ATM from Yahoo chain")
    print(f"Chosen contract: {contract.strike:.2f}{contract.right}")
    print(
        f"Market: [{proposal['market']['bid']:.2f} x {proposal['market']['ask']:.2f}]  "
        f"last=${proposal['market']['last_price']:.2f}"
    )
    print(
        f"IV: {proposal['metrics']['implied_volatility']:.2%}  "
        f"r: {proposal['metrics']['risk_free_rate']:.2%}  "
        f"q: {proposal['metrics']['dividend_yield']:.2%}"
    )
    print(
        f"Model: TV=${proposal['metrics']['theoretical_value']:.2f}  "
        f"mid=${proposal['market']['mid']:.2f}  "
        f"suggested=${proposal['metrics']['suggested_limit']:.2f}"
    )

    print("\nNearest quoted strikes:")
    for row in nearby:
        iv = row["implied_volatility"]
        iv_text = f"{iv:.2%}" if iv is not None else "N/A"
        print(f"  {row['strike']:.2f}C  [{row['bid']:.2f} x {row['ask']:.2f}]  IV={iv_text}")

    print(f"\nExit ladder for {total_qty} contracts:")
    for tranche in proposal["tranches"]:
        print(f"  T{tranche['tranche']}: {tranche['quantity']:>3d} @ ${tranche['lmtPrice']:.2f}")

    print(f"\nSaved proposal to {output_file}")
    return proposal


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Yahoo-backed fallback for option exit pricing. Prefer stock_tooling/price_exit.py for IBKR-first pricing."
    )
    parser.add_argument("--symbol", default="EWY")
    parser.add_argument("--expiry", required=True, help="Option expiry in YYYY-MM-DD format.")
    parser.add_argument("--qty", type=int, default=100, help="Total contracts to exit.")
    parser.add_argument("--strike", type=float, help="Exact strike to price. Defaults to nearest ATM.")
    parser.add_argument("--tranches", type=int, default=5, help="Number of limit tranches.")
    parser.add_argument(
        "--risk-free",
        type=float,
        default=0.045,
        help="Fallback risk-free rate as a decimal if ^IRX fetch fails.",
    )
    parser.add_argument(
        "--dividend-yield",
        type=float,
        default=0.0,
        help="Annual dividend yield as a decimal for BSM pricing.",
    )
    parser.add_argument("--output", default="trade_proposal_yf.json")
    args = parser.parse_args()

    price_exit_yf(
        symbol=args.symbol.upper(),
        expiry=args.expiry,
        total_qty=args.qty,
        strike=args.strike,
        n_tranches=args.tranches,
        default_rate=args.risk_free,
        dividend_yield=args.dividend_yield,
        output_file=args.output,
    )


if __name__ == "__main__":
    main()
