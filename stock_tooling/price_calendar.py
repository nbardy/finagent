"""
Price a put/call calendar spread using calibrated models (BS + Heston + VG + MJD).

The models are calibrated to observed option mids across both expiries and a strike
slice around the target strike, then each leg is priced individually and netted
into a calendar value.

Usage:
    uv run python stock_tooling/price_calendar.py EWY 120 P 20260410 20260424
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ib_insync import Option

from ibkr import connect
from option_pricing.black_scholes import implied_volatility_from_price, option_price
from option_pricing.calibrate import MarketQuote, calibrate_all
from option_pricing.heston import heston_price
from option_pricing.merton_jump import mjd_price
from option_pricing.models import dte_and_time_to_expiry, normalize_expiry
from option_pricing.variance_gamma import vg_price


def _default_output_path(symbol: str, short_expiry: str, long_expiry: str, strike: float, right: str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    strike_label = str(int(strike)) if float(strike).is_integer() else str(strike).replace(".", "_")
    return Path("analysis") / today / f"{symbol.lower()}_{short_expiry}_{long_expiry}_{strike_label}{right.lower()}_calendar_model_audit.json"


def _safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, float) and value != value:
        return default
    return float(value)


def _strike_step(spot: float) -> float:
    if spot >= 200:
        return 10.0
    if spot >= 50:
        return 5.0
    return 2.5


def _build_strike_grid(center_strike: float, provisional_spot: float, span_steps: int) -> list[float]:
    step = _strike_step(provisional_spot)
    start = max(step, center_strike - span_steps * step)
    end = center_strike + span_steps * step
    strikes: list[float] = []
    value = start
    while value <= end + 1e-9:
        strikes.append(round(value, 2))
        value += step
    if center_strike not in strikes:
        strikes.append(center_strike)
        strikes.sort()
    return strikes


def fetch_calendar_slice(
    *,
    symbol: str,
    short_expiry: str,
    long_expiry: str,
    strike: float,
    right: str,
    span_steps: int,
    client_id: int,
    settle_secs: float,
    market_data_type: int,
) -> tuple[float, dict, dict, list[MarketQuote]]:
    right = right.upper()
    short_expiry = normalize_expiry(short_expiry)
    long_expiry = normalize_expiry(long_expiry)

    with connect(client_id=client_id, readonly=True, market_data_type=market_data_type, debug=False) as ib:
        provisional_spot = strike
        strikes = _build_strike_grid(strike, provisional_spot, span_steps)
        contracts = []
        for expiry in (short_expiry, long_expiry):
            for k in strikes:
                contracts.append(Option(symbol, expiry, k, right, "SMART"))
        contracts = ib.qualifyContracts(*contracts)
        tickers = ib.reqTickers(*contracts)
        ib.sleep(settle_secs)

        spot_candidates = []
        quotes: list[MarketQuote] = []
        short_snapshot: dict | None = None
        long_snapshot: dict | None = None

        for ticker in tickers:
            greeks = getattr(ticker, "modelGreeks", None)
            und_price = _safe_float(getattr(greeks, "undPrice", None))
            if und_price > 0:
                spot_candidates.append(und_price)

            bid = _safe_float(ticker.bid)
            ask = _safe_float(ticker.ask)
            last = _safe_float(ticker.last)
            mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0
            iv = _safe_float(getattr(greeks, "impliedVol", None))

            expiry = ticker.contract.lastTradeDateOrContractMonth
            k = float(ticker.contract.strike)

            t = dte_and_time_to_expiry(expiry)[1]
            if bid > 0 and ask > 0 and mid > 0:
                quotes.append(MarketQuote(
                    strike=k,
                    T=t,
                    market_price=mid,
                    right=right,
                    weight=1.0,
                ))

            snapshot = {
                "symbol": symbol,
                "expiry": expiry,
                "strike": k,
                "right": right,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": last,
                "iv": iv,
                "und_price": und_price,
                "market_data_type": getattr(ticker, "marketDataType", None),
            }
            if expiry == short_expiry and k == float(strike):
                short_snapshot = snapshot
            elif expiry == long_expiry and k == float(strike):
                long_snapshot = snapshot

    if not spot_candidates:
        raise RuntimeError("Could not recover underlying price from IBKR option greeks for calendar audit.")
    if short_snapshot is None or long_snapshot is None:
        raise RuntimeError("Target calendar leg was not returned by IBKR.")

    return float(spot_candidates[0]), short_snapshot, long_snapshot, quotes


def _price_model(name: str, *, spot: float, strike: float, T: float, r: float, right: str, dividend_yield: float, params) -> float:
    if name == "Heston":
        return heston_price(spot, strike, T, r, params, right, dividend_yield)
    if name == "VG":
        return vg_price(spot, strike, T, r, params, right, dividend_yield)
    if name == "MJD":
        return mjd_price(spot, strike, T, r, params, right, dividend_yield)
    raise ValueError(f"Unsupported model: {name}")


def audit_calendar_models(
    *,
    symbol: str,
    short_expiry: str,
    long_expiry: str,
    strike: float,
    right: str,
    spot: float | None,
    risk_free_rate: float,
    dividend_yield: float,
    span_steps: int,
    client_id: int,
    settle_secs: float,
    market_data_type: int,
) -> dict:
    short_expiry = normalize_expiry(short_expiry)
    long_expiry = normalize_expiry(long_expiry)
    right = right.upper()

    ibkr_spot, short_snapshot, long_snapshot, quotes = fetch_calendar_slice(
        symbol=symbol,
        short_expiry=short_expiry,
        long_expiry=long_expiry,
        strike=strike,
        right=right,
        span_steps=span_steps,
        client_id=client_id,
        settle_secs=settle_secs,
        market_data_type=market_data_type,
    )
    final_spot = spot if spot and spot > 0 else ibkr_spot

    short_dte, short_t = dte_and_time_to_expiry(short_expiry)
    long_dte, long_t = dte_and_time_to_expiry(long_expiry)

    short_mid = float(short_snapshot["mid"])
    long_mid = float(long_snapshot["mid"])
    market_calendar = long_mid - short_mid

    short_iv = float(short_snapshot["iv"])
    if short_iv <= 0 and short_mid > 0:
        short_iv = implied_volatility_from_price(final_spot, strike, short_t, risk_free_rate, short_mid, right, dividend_yield) or 0.0
    long_iv = float(long_snapshot["iv"])
    if long_iv <= 0 and long_mid > 0:
        long_iv = implied_volatility_from_price(final_spot, strike, long_t, risk_free_rate, long_mid, right, dividend_yield) or 0.0
    if short_iv <= 0 or long_iv <= 0:
        raise RuntimeError("Could not determine leg implied volatilities for calendar BS audit.")

    bs_short = option_price(final_spot, strike, short_t, risk_free_rate, short_iv, right, dividend_yield)
    bs_long = option_price(final_spot, strike, long_t, risk_free_rate, long_iv, right, dividend_yield)
    bs_calendar = bs_long - bs_short

    calibrations = calibrate_all(final_spot, risk_free_rate, quotes, dividend_yield)
    model_prices = {
        "BSM": {
            "short_leg": round(bs_short, 4),
            "long_leg": round(bs_long, 4),
            "calendar": round(bs_calendar, 4),
            "short_iv": round(short_iv, 6),
            "long_iv": round(long_iv, 6),
        }
    }

    for name, cal in calibrations.items():
        short_price = _price_model(
            name,
            spot=final_spot,
            strike=strike,
            T=short_t,
            r=risk_free_rate,
            right=right,
            dividend_yield=dividend_yield,
            params=cal.params,
        )
        long_price = _price_model(
            name,
            spot=final_spot,
            strike=strike,
            T=long_t,
            r=risk_free_rate,
            right=right,
            dividend_yield=dividend_yield,
            params=cal.params,
        )
        model_prices[name] = {
            "short_leg": round(short_price, 4),
            "long_leg": round(long_price, 4),
            "calendar": round(long_price - short_price, 4),
            "rmse": cal.rmse,
            "max_error": cal.max_error,
            "params": asdict(cal.params),
        }

    calendar_values = [float(row["calendar"]) for row in model_prices.values()]
    consensus = {
        "mean_calendar": round(statistics.mean(calendar_values), 4),
        "stdev_calendar": round(statistics.stdev(calendar_values), 4) if len(calendar_values) > 1 else 0.0,
        "min_calendar": round(min(calendar_values), 4),
        "max_calendar": round(max(calendar_values), 4),
        "market_calendar": round(market_calendar, 4),
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "short_expiry": short_expiry,
        "long_expiry": long_expiry,
        "strike": strike,
        "right": right,
        "spot": round(final_spot, 4),
        "risk_free_rate": risk_free_rate,
        "dividend_yield": dividend_yield,
        "chain_quotes_used": len(quotes),
        "target_market": {
            "short_leg": short_snapshot,
            "long_leg": long_snapshot,
            "calendar_mid": round(market_calendar, 4),
        },
        "model_prices": model_prices,
        "consensus": consensus,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a calendar spread across BS, Heston, VG, and MJD.")
    parser.add_argument("symbol")
    parser.add_argument("strike", type=float)
    parser.add_argument("right", choices=["C", "P", "c", "p"])
    parser.add_argument("short_expiry", help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("long_expiry", help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--spot", type=float, default=None)
    parser.add_argument("--r", type=float, default=0.045)
    parser.add_argument("--q", type=float, default=0.0)
    parser.add_argument("--span-steps", type=int, default=6)
    parser.add_argument("--client-id", type=int, default=191)
    parser.add_argument("--settle-secs", type=float, default=2.0)
    parser.add_argument("--market-data-type", type=int, default=4)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    audit = audit_calendar_models(
        symbol=args.symbol.upper(),
        short_expiry=args.short_expiry,
        long_expiry=args.long_expiry,
        strike=args.strike,
        right=args.right.upper(),
        spot=args.spot,
        risk_free_rate=args.r,
        dividend_yield=args.q,
        span_steps=args.span_steps,
        client_id=args.client_id,
        settle_secs=args.settle_secs,
        market_data_type=args.market_data_type,
    )

    output_path = Path(args.output) if args.output else _default_output_path(
        audit["symbol"],
        audit["short_expiry"],
        audit["long_expiry"],
        float(audit["strike"]),
        audit["right"],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, indent=2) + "\n")

    print(json.dumps({
        "output": str(output_path),
        "spot": audit["spot"],
        "market": audit["target_market"],
        "consensus": audit["consensus"],
        "models": audit["model_prices"],
    }, indent=2))


if __name__ == "__main__":
    main()
