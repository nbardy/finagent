"""
IBKR-backed CLI for pricing option exits.

The pricing logic lives in the `option_pricing` package. This file only adapts
IBKR quotes into the shared proposal format.
"""

from __future__ import annotations

import argparse
import json

from ibkr import connect, get_option_quotes, get_spot
from option_pricing import mc_option_pnl, price_option_exit
from option_pricing.models import OptionContractSpec, OptionMarketSnapshot, dte_and_time_to_expiry


def _require_implied_volatility(quote, *, symbol: str, expiry: str, strike: float, right: str, iv_override: float | None) -> float:
    if iv_override is not None:
        return iv_override
    if quote.iv > 0:
        return quote.iv
    raise ValueError(
        f"Missing IBKR IV for {symbol} {expiry} {strike:.1f}{right}; "
        "provide --iv-override if you want to price this manually."
    )


def price_exits(
    symbol: str,
    exits: list[dict],
    r: float = 0.045,
    dividend_yield: float = 0.0,
    iv_override: float | None = None,
    market_data_type: int = 3,
    output_file: str = "exit_proposal.json",
    debug: bool = True,
) -> dict:
    with connect(client_id=13, market_data_type=market_data_type, debug=debug) as ib:
        spot = get_spot(ib, symbol, debug=debug)
        print(f"\n{symbol} spot: ${spot:.2f}")

        specs = [(e["strike"], e["expiry"], e["right"]) for e in exits]
        quotes = get_option_quotes(ib, symbol, specs, debug=debug)

        print(f"\n{'='*80}")
        print(f"  EXIT PRICING — {symbol} via IBKR")
        print(f"{'='*80}")

        proposals = []
        total_cash = 0.0

        for exit_spec, quote in zip(exits, quotes):
            contract = OptionContractSpec(
                symbol=symbol,
                expiry=exit_spec["expiry"],
                strike=exit_spec["strike"],
                right=exit_spec["right"],
            )
            sigma = _require_implied_volatility(
                quote=quote,
                symbol=symbol,
                strike=contract.strike,
                expiry=contract.expiry,
                right=contract.right,
                iv_override=iv_override,
            )
            market = OptionMarketSnapshot(
                spot=spot,
                bid=quote.bid,
                ask=quote.ask,
                last=quote.last,
                implied_volatility=sigma,
                risk_free_rate=r,
                dividend_yield=dividend_yield,
                source="ibkr",
                market_data_type=market_data_type,
            )
            proposal = price_option_exit(
                contract=contract,
                market=market,
                total_qty=exit_spec["qty"],
                action=exit_spec.get("action", "SELL"),
                n_tranches=min(5, exit_spec["qty"]),
            )
            _, time_to_expiry = dte_and_time_to_expiry(contract.expiry)
            prob_profit, exp_pnl, tail = mc_option_pnl(
                S=spot,
                K=contract.strike,
                T=time_to_expiry,
                sigma=sigma,
                premium=proposal["metrics"]["suggested_limit"],
                is_long=(proposal["action"] == "BUY"),
                is_call=(contract.right == "C"),
            )
            proposal["analytics"] = {
                "prob_profit": round(prob_profit, 4),
                "expected_pnl": round(exp_pnl, 4),
                "tail_p05_pnl": round(tail, 4),
            }
            proposals.append(proposal)

            cash = proposal["metrics"]["suggested_limit"] * exit_spec["qty"] * 100
            total_cash += cash if proposal["action"] == "SELL" else -cash

            print(
                f"\n  ── {proposal['action']} {exit_spec['qty']}x "
                f"{contract.strike}{contract.right} {contract.expiry} ──"
            )
            print(
                f"  Market: [{proposal['market']['bid']:.2f} x {proposal['market']['ask']:.2f}]  "
                f"mid=${proposal['market']['mid']:.2f}"
            )
            print(
                f"  Model: TV=${proposal['metrics']['theoretical_value']:.2f}  "
                f"Δ={proposal['metrics']['delta']:.3f}  "
                f"Γ={proposal['metrics']['gamma']:.4f}"
            )
            print(
                f"  Suggested limit: ${proposal['metrics']['suggested_limit']:.2f}  "
                f"IV={proposal['metrics']['implied_volatility']:.2%}"
            )
            print(
                f"  MC: ProbProfit={proposal['analytics']['prob_profit']*100:.0f}%  "
                f"E[PnL]=${proposal['analytics']['expected_pnl']:.2f}  "
                f"Tail=${proposal['analytics']['tail_p05_pnl']:.2f}"
            )
            print("  Tranches:")
            for tranche in proposal["tranches"]:
                print(f"    T{tranche['tranche']}: {tranche['quantity']:3d}x @ ${tranche['lmtPrice']:.2f}")

        payload = {
            "symbol": symbol,
            "spot": round(spot, 4),
            "quote_source": "ibkr",
            "market_data_type": market_data_type,
            "total_cash": round(total_cash, 2),
            "trades": proposals,
        }

        with open(output_file, "w") as handle:
            json.dump(payload, handle, indent=2)

        print(f"\n{'='*80}")
        print(f"  TOTAL CASH: ${total_cash:+,.0f}")
        print(f"{'='*80}")
        print(f"\nSaved to {output_file}")
        return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Price exit limit orders from IBKR quotes")
    parser.add_argument("--symbol", default="EWY")
    parser.add_argument("--iv", type=float, default=None, help="IV override (e.g. 0.45)")
    parser.add_argument("--risk-free", type=float, default=0.045)
    parser.add_argument("--dividend-yield", type=float, default=0.0)
    parser.add_argument("--market-data-type", type=int, default=3, help="1=live, 3=delayed, 4=delayed-frozen")
    parser.add_argument("--output", default="exit_proposal.json")
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print detailed IBKR connection and quote diagnostics.",
    )
    args = parser.parse_args()

    if args.symbol == "EWY":
        exits = [
            {"strike": 145, "expiry": "20280121", "right": "C", "qty": 22, "action": "SELL"},
            {"strike": 150, "expiry": "20280121", "right": "C", "qty": 30, "action": "SELL"},
        ]
    else:
        print("Specify exits in code or extend CLI. For now, edit the exits list in main().")
        return

    price_exits(
        symbol=args.symbol.upper(),
        exits=exits,
        r=args.risk_free,
        dividend_yield=args.dividend_yield,
        iv_override=args.iv,
        market_data_type=args.market_data_type,
        output_file=args.output,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()
