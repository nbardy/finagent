"""
Price a debit spread using calibrated models (BS + Heston + VG + MJD).

Reads market quotes from IBKR, calibrates all models to the chain,
prices the target spread, and optionally generates a buy proposal JSON.

Usage:
    # Price AAOI 155/165 Jun 2028 spread, generate proposal
    uv run python price_spread.py AAOI 155 165 20280616 --budget 10000 --proposal

    # Price AXTI 40/45 Jan 2027 spread, just show prices
    uv run python price_spread.py AXTI 40 45 20270115

    # Use manual quotes (no IBKR needed)
    uv run python price_spread.py AAOI 155 165 20280616 --spot 113.38 --iv 1.18 --no-live
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime

from option_pricing.black_scholes import option_price
from option_pricing.calibrate import CalibrationResult, MarketQuote, calibrate_all
from option_pricing.heston import heston_price
from option_pricing.merton_jump import mjd_price
from option_pricing.models import dte_and_time_to_expiry
from option_pricing.variance_gamma import vg_price


def fetch_chain_quotes(
    symbol: str, expiry: str, spot: float, client_id: int = 30,
) -> list[MarketQuote]:
    """Fetch option quotes from IBKR and return as MarketQuote list."""
    from ibkr import connect, get_option_quotes

    dte, T = dte_and_time_to_expiry(expiry)

    # Build strike list: range around spot
    strikes = []
    step = 5 if spot > 50 else 2.5
    k = max(round(spot * 0.5 / step) * step, step)
    while k <= spot * 2.0:
        strikes.append((k, expiry, "C"))
        k += step

    quotes = []
    with connect(client_id=client_id) as ib:
        raw = get_option_quotes(ib, symbol, strikes)
        for q in raw:
            if q.bid > 0 and q.ask > 0:
                mid = (q.bid + q.ask) / 2.0
                quotes.append(MarketQuote(
                    strike=q.strike, T=T, market_price=mid, right="C",
                    weight=1.0,
                ))

    return quotes


def price_spread_bs(spot: float, long_k: float, short_k: float, T: float, r: float, iv: float) -> float:
    """BS spread price."""
    return option_price(spot, long_k, T, r, iv, "C") - option_price(spot, short_k, T, r, iv, "C")


def price_spread_calibrated(
    spot: float, long_k: float, short_k: float, T: float, r: float,
    cal: CalibrationResult,
) -> float:
    """Price spread using a calibrated model."""
    p = cal.params
    if cal.model == "Heston":
        return heston_price(spot, long_k, T, r, p, "C") - heston_price(spot, short_k, T, r, p, "C")
    elif cal.model == "VG":
        return vg_price(spot, long_k, T, r, p, "C") - vg_price(spot, short_k, T, r, p, "C")
    elif cal.model == "MJD":
        return mjd_price(spot, long_k, T, r, p, "C") - mjd_price(spot, short_k, T, r, p, "C")
    raise ValueError(f"Unknown model: {cal.model}")


def generate_proposal(
    symbol: str, long_k: float, short_k: float, expiry: str,
    limit_price: float, budget: float, tif: str = "GTC",
) -> dict:
    """Generate executor-compatible buy proposal for a debit spread."""
    cost_per = limit_price * 100
    n_contracts = int(budget / cost_per)

    # Split into 3 tranches: start at limit, walk down
    tranche_limits = [limit_price, limit_price * 0.85, limit_price * 0.70]
    tranche_qtys = [
        max(1, int(n_contracts * 0.5)),   # 50% at target
        max(1, int(n_contracts * 0.3)),   # 30% lower
        max(1, n_contracts - int(n_contracts * 0.5) - int(n_contracts * 0.3)),  # rest
    ]

    return {
        "description": f"{symbol} {int(long_k)}/{int(short_k)} {expiry} debit spread",
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "trades": [
            {
                "contract": {
                    "secType": "BAG",
                    "symbol": symbol,
                    "exchange": "SMART",
                    "currency": "USD",
                    "legs": [
                        {
                            "action": "BUY",
                            "strike": long_k,
                            "right": "C",
                            "expiry": expiry,
                            "ratio": 1,
                        },
                        {
                            "action": "SELL",
                            "strike": short_k,
                            "right": "C",
                            "expiry": expiry,
                            "ratio": 1,
                        },
                    ],
                },
                "action": "BUY",
                "tif": tif,
                "tranches": [
                    {
                        "tranche": i + 1,
                        "quantity": qty,
                        "lmtPrice": round(lmt, 2),
                        "note": f"{'Target' if i == 0 else 'Lower'} fill @ ${lmt:.2f}/sh = ${lmt*100:.0f}/contract",
                    }
                    for i, (qty, lmt) in enumerate(zip(tranche_qtys, tranche_limits))
                ],
            }
        ],
        "pricing": {
            "budget": budget,
            "contracts_at_target": n_contracts,
            "limit_per_share": limit_price,
            "limit_per_contract": limit_price * 100,
            "max_spread_value": (short_k - long_k),
            "max_return_pct": round((short_k - long_k - limit_price) / limit_price * 100, 1),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Price a debit spread with calibrated models")
    parser.add_argument("symbol", help="Underlying symbol")
    parser.add_argument("long_strike", type=float, help="Long leg strike")
    parser.add_argument("short_strike", type=float, help="Short leg strike")
    parser.add_argument("expiry", help="Expiry YYYYMMDD")
    parser.add_argument("--budget", type=float, default=10000, help="Budget in USD")
    parser.add_argument("--spot", type=float, default=None, help="Override spot price")
    parser.add_argument("--iv", type=float, default=None, help="Override IV for BS")
    parser.add_argument("--no-live", action="store_true", help="Skip IBKR, use --spot and --iv only")
    parser.add_argument("--proposal", action="store_true", help="Generate buy proposal JSON")
    parser.add_argument("--r", type=float, default=0.045, help="Risk-free rate")
    args = parser.parse_args()

    long_k = args.long_strike
    short_k = args.short_strike
    width = short_k - long_k

    dte, T = dte_and_time_to_expiry(args.expiry)
    print(f"\n{'='*70}")
    print(f"  {args.symbol} {int(long_k)}/{int(short_k)} DEBIT SPREAD")
    print(f"  Expiry: {args.expiry} ({dte} DTE, T={T:.4f}yr)")
    print(f"  Spread width: ${width:.0f}")
    print(f"{'='*70}")

    # Get spot
    spot = args.spot
    if spot is None and not args.no_live:
        from ibkr import connect, get_spot
        with connect(client_id=29) as ib:
            spot = get_spot(ib, args.symbol)
    if spot is None:
        print("ERROR: No spot price. Provide --spot or connect to IBKR.")
        sys.exit(1)

    print(f"  Spot: ${spot:.2f}")

    # Get chain quotes for calibration
    quotes = []
    if not args.no_live:
        print(f"  Fetching option chain from IBKR...")
        quotes = fetch_chain_quotes(args.symbol, args.expiry, spot)
        print(f"  Got {len(quotes)} quotes with valid bid/ask")

    # BS pricing (always available)
    iv = args.iv
    if iv is None and quotes:
        # Use the ATM quote to back out IV
        atm_quotes = [q for q in quotes if abs(q.strike - spot) < spot * 0.1]
        if atm_quotes:
            from option_pricing.black_scholes import implied_volatility_from_price
            q = min(atm_quotes, key=lambda q: abs(q.strike - spot))
            iv = implied_volatility_from_price(spot, q.strike, T, args.r, q.market_price, "C")
            print(f"  ATM IV (from K={q.strike}): {iv:.1%}")

    if iv is None:
        print("ERROR: No IV available. Provide --iv or connect to IBKR.")
        sys.exit(1)

    bs_spread = price_spread_bs(spot, long_k, short_k, T, args.r, iv)

    print(f"\n  --- MODEL PRICES ---")
    print(f"  {'Model':<12} {'155C':>10} {'165C':>10} {'Spread':>10} {'MaxRet':>10} {'RMSE':>10}")
    print(f"  {'─'*62}")

    bs_long = option_price(spot, long_k, T, args.r, iv, "C")
    bs_short = option_price(spot, short_k, T, args.r, iv, "C")
    print(f"  {'BS':<12} ${bs_long:>8.2f} ${bs_short:>8.2f} ${bs_spread:>8.4f} {(width-bs_spread)/bs_spread*100:>8.0f}%  {'—':>10}")

    all_spreads = {"BS": bs_spread}

    # Calibrate if we have quotes
    if len(quotes) >= 3:
        print(f"\n  Calibrating 3 models to {len(quotes)} market quotes...")
        calibrations = calibrate_all(spot, args.r, quotes)

        for name, cal in calibrations.items():
            spread = price_spread_calibrated(spot, long_k, short_k, T, args.r, cal)
            all_spreads[name] = spread

            # Get individual leg prices for display
            p = cal.params
            if name == "Heston":
                lp = heston_price(spot, long_k, T, args.r, p, "C")
                sp = heston_price(spot, short_k, T, args.r, p, "C")
            elif name == "VG":
                lp = vg_price(spot, long_k, T, args.r, p, "C")
                sp = vg_price(spot, short_k, T, args.r, p, "C")
            elif name == "MJD":
                lp = mjd_price(spot, long_k, T, args.r, p, "C")
                sp = mjd_price(spot, short_k, T, args.r, p, "C")

            print(f"  {name:<12} ${lp:>8.2f} ${sp:>8.2f} ${spread:>8.4f} {(width-spread)/spread*100:>8.0f}%  ${cal.rmse:>8.4f}")

        # Print calibrated params for inspection
        print(f"\n  --- CALIBRATED PARAMETERS ---")
        for name, cal in calibrations.items():
            print(f"  {name}: {cal.params}")
    else:
        print(f"\n  (Skipping calibration — need 3+ quotes, got {len(quotes)})")

    # Consensus
    spread_values = list(all_spreads.values())
    mean_spread = statistics.mean(spread_values)
    stdev_spread = statistics.stdev(spread_values) if len(spread_values) > 1 else 0

    print(f"\n  --- CONSENSUS ---")
    print(f"  Mean:  ${mean_spread:.4f}/sh (${mean_spread*100:.0f}/contract)")
    print(f"  StDev: ${stdev_spread:.4f}")
    print(f"  Range: ${min(spread_values):.4f} - ${max(spread_values):.4f}")
    print(f"  95%CI: ${mean_spread - 2*stdev_spread:.4f} - ${mean_spread + 2*stdev_spread:.4f}")

    # Find market mid if we have the right quotes
    long_quotes = [q for q in quotes if q.strike == long_k]
    short_quotes = [q for q in quotes if q.strike == short_k]
    if long_quotes and short_quotes:
        market_spread = long_quotes[0].market_price - short_quotes[0].market_price
        print(f"  Market mid: ${market_spread:.4f}/sh")
        print(f"  Discount to consensus: {(1 - market_spread/mean_spread)*100:.0f}%")

    # Budget analysis
    budget = args.budget
    print(f"\n  --- ${budget:,.0f} BUDGET ---")
    for label, price in [("Market mid", market_spread if long_quotes and short_quotes else mean_spread),
                          ("Consensus", mean_spread),
                          ("Conservative", mean_spread + stdev_spread)]:
        if price <= 0:
            continue
        cost = price * 100
        n = int(budget / cost)
        max_val = n * width * 100
        print(f"  {label} (${price:.2f}): {n} contracts, max ${max_val:,.0f} ({(width-price)/price*100:.0f}% ret)")

    # Generate proposal
    if args.proposal:
        # Start limit at market mid, cap at consensus
        start_limit = market_spread if (long_quotes and short_quotes) else mean_spread
        proposal = generate_proposal(
            args.symbol, long_k, short_k, args.expiry,
            limit_price=round(start_limit, 2),
            budget=budget,
        )
        filename = f"{args.symbol.lower()}_spread_proposal.json"
        with open(filename, "w") as f:
            json.dump(proposal, f, indent=2)
        print(f"\n  Proposal saved to {filename}")
        print(f"  Execute: uv run python executor.py --file {filename}")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()
