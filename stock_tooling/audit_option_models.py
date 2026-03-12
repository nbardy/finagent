"""
Audit a single option across BS, Heston, VG, and MJD.

This is the model-audit entrypoint for short-call pricing decisions.
It fetches a same-expiry strike slice from IBKR, calibrates the richer
models to observed mids, and reports where the exact target option sits
versus market and model prices.

Usage:
    uv run python stock_tooling/audit_option_models.py EWY 20260410 170 C
    uv run python stock_tooling/audit_option_models.py EWY 20260410 170 C --spot 130.5
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ib_insync import Option

from option_pricing.black_scholes import implied_volatility_from_price, option_price
from option_pricing.calibrate import MarketQuote, calibrate_all
from option_pricing.heston import heston_price
from option_pricing.merton_jump import mjd_price
from option_pricing.models import dte_and_time_to_expiry, normalize_expiry
from option_pricing.variance_gamma import vg_price


def _default_output_path(symbol: str, expiry: str, strike: float, right: str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    strike_label = str(int(strike)) if float(strike).is_integer() else str(strike).replace(".", "_")
    return Path("analysis") / today / f"{symbol.lower()}_{expiry}_{strike_label}{right.lower()}_model_audit.json"


def _safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return float(value)


def _strike_step(spot: float) -> float:
    if spot >= 200:
        return 10.0
    if spot >= 50:
        return 5.0
    return 2.5


def _build_strike_grid(center_strike: float, spot: float, span_steps: int) -> list[float]:
    step = _strike_step(spot)
    start = max(step, center_strike - span_steps * step)
    end = center_strike + span_steps * step
    strikes = []
    k = start
    while k <= end + 1e-9:
        strikes.append(round(k, 2))
        k += step
    if center_strike not in strikes:
        strikes.append(center_strike)
        strikes.sort()
    return strikes


def fetch_option_slice(
    symbol: str,
    expiry: str,
    right: str,
    target_strike: float,
    span_steps: int,
    client_id: int,
    settle_secs: float,
) -> tuple[float, dict, list[MarketQuote]]:
    from ibkr import connect

    expiry = normalize_expiry(expiry)
    right = right.upper()

    with connect(client_id=client_id, readonly=True, market_data_type=3, debug=False) as ib:
        provisional_spot = target_strike
        strikes = _build_strike_grid(target_strike, provisional_spot, span_steps)
        contracts = [Option(symbol, expiry, strike, right, "SMART") for strike in strikes]
        contracts = ib.qualifyContracts(*contracts)
        tickers = ib.reqTickers(*contracts)
        ib.sleep(settle_secs)

        spot_candidates = []
        for ticker in tickers:
            greeks = getattr(ticker, "modelGreeks", None)
            und_price = _safe_float(getattr(greeks, "undPrice", None))
            if und_price > 0:
                spot_candidates.append(und_price)
        spot = spot_candidates[0] if spot_candidates else 0.0
        if spot <= 0:
            spot = provisional_spot

        quotes: list[MarketQuote] = []
        target_snapshot: dict | None = None

        for ticker in tickers:
            bid = _safe_float(ticker.bid)
            ask = _safe_float(ticker.ask)
            last = _safe_float(ticker.last)
            mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0
            greeks = getattr(ticker, "modelGreeks", None)
            iv = _safe_float(getattr(greeks, "impliedVol", None))
            delta = _safe_float(getattr(greeks, "delta", None))
            und_price = _safe_float(getattr(greeks, "undPrice", None))
            market_data_type = getattr(ticker, "marketDataType", None)

            if bid > 0 and ask > 0 and mid > 0:
                quotes.append(MarketQuote(
                    strike=float(ticker.contract.strike),
                    T=dte_and_time_to_expiry(expiry)[1],
                    market_price=mid,
                    right=right,
                    weight=1.0,
                ))

            if float(ticker.contract.strike) == float(target_strike):
                target_snapshot = {
                    "symbol": symbol,
                    "expiry": expiry,
                    "strike": float(ticker.contract.strike),
                    "right": right,
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "last": last,
                    "iv": iv,
                    "delta": delta,
                    "und_price": und_price,
                    "market_data_type": market_data_type,
                }

        if target_snapshot is None:
            raise RuntimeError("Target option not returned by IBKR.")
        if spot <= 0:
            spot = _safe_float(target_snapshot.get("und_price"))
        if spot <= 0:
            raise RuntimeError("Could not recover underlying price from IBKR option greeks.")

        return spot, target_snapshot, quotes


def audit_option_models(
    symbol: str,
    expiry: str,
    strike: float,
    right: str,
    spot: float | None,
    risk_free_rate: float,
    dividend_yield: float,
    span_steps: int,
    client_id: int,
    settle_secs: float,
) -> dict:
    expiry = normalize_expiry(expiry)
    right = right.upper()

    ibkr_spot, target_snapshot, quotes = fetch_option_slice(
        symbol=symbol,
        expiry=expiry,
        right=right,
        target_strike=strike,
        span_steps=span_steps,
        client_id=client_id,
        settle_secs=settle_secs,
    )
    final_spot = spot if spot and spot > 0 else ibkr_spot

    dte, T = dte_and_time_to_expiry(expiry)
    market_mid = float(target_snapshot["mid"])
    target_iv = float(target_snapshot["iv"])
    if target_iv <= 0 and market_mid > 0:
        implied = implied_volatility_from_price(final_spot, strike, T, risk_free_rate, market_mid, right, dividend_yield)
        target_iv = implied or 0.0
    if target_iv <= 0:
        raise RuntimeError("Could not determine target implied volatility for BS audit.")

    bs_price = option_price(final_spot, strike, T, risk_free_rate, target_iv, right, dividend_yield)

    calibrations = calibrate_all(final_spot, risk_free_rate, quotes, dividend_yield)
    model_prices = {
        "BSM": {
            "price": round(bs_price, 4),
            "source_iv": round(target_iv, 6),
        }
    }

    for name, cal in calibrations.items():
        if name == "Heston":
            price = heston_price(final_spot, strike, T, risk_free_rate, cal.params, right, dividend_yield)
        elif name == "VG":
            price = vg_price(final_spot, strike, T, risk_free_rate, cal.params, right, dividend_yield)
        elif name == "MJD":
            price = mjd_price(final_spot, strike, T, risk_free_rate, cal.params, right, dividend_yield)
        else:
            continue
        model_prices[name] = {
            "price": round(price, 4),
            "rmse": cal.rmse,
            "max_error": cal.max_error,
            "params": asdict(cal.params),
        }

    consensus_prices = [payload["price"] for payload in model_prices.values()]
    rich_model_prices = [
        payload["price"] for name, payload in model_prices.items() if name != "BSM"
    ]

    def summarize(prices: list[float]) -> dict[str, float]:
        if not prices:
            return {
                "count": 0,
                "mean": 0.0,
                "stdev": 0.0,
                "min": 0.0,
                "max": 0.0,
            }
        return {
            "count": len(prices),
            "mean": round(statistics.mean(prices), 4),
            "stdev": round(statistics.pstdev(prices), 4) if len(prices) > 1 else 0.0,
            "min": round(min(prices), 4),
            "max": round(max(prices), 4),
        }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "expiry": expiry,
        "strike": strike,
        "right": right,
        "dte": dte,
        "spot": round(final_spot, 4),
        "risk_free_rate": risk_free_rate,
        "dividend_yield": dividend_yield,
        "target_market": {
            **target_snapshot,
            "spot_used": round(final_spot, 4),
        },
        "chain_quotes_used": len(quotes),
        "consensus_summary": summarize(consensus_prices),
        "rich_model_summary": summarize(rich_model_prices),
        "model_prices": model_prices,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a single option across BS, Heston, VG, and MJD.")
    parser.add_argument("symbol")
    parser.add_argument("expiry", help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("strike", type=float)
    parser.add_argument("right", choices=["C", "P", "c", "p"])
    parser.add_argument("--spot", type=float, default=None, help="Override spot instead of using IBKR model underlying.")
    parser.add_argument("--r", type=float, default=0.045, help="Risk-free rate")
    parser.add_argument("--q", type=float, default=0.0, help="Dividend yield")
    parser.add_argument("--span-steps", type=int, default=6, help="How many strike steps each side to use for calibration.")
    parser.add_argument("--client-id", type=int, default=190)
    parser.add_argument("--settle-secs", type=float, default=2.0)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    audit = audit_option_models(
        symbol=args.symbol.upper(),
        expiry=args.expiry,
        strike=args.strike,
        right=args.right.upper(),
        spot=args.spot,
        risk_free_rate=args.r,
        dividend_yield=args.q,
        span_steps=args.span_steps,
        client_id=args.client_id,
        settle_secs=args.settle_secs,
    )

    output_path = Path(args.output) if args.output else _default_output_path(
        audit["symbol"],
        audit["expiry"],
        float(audit["strike"]),
        audit["right"],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, indent=2) + "\n")

    print(json.dumps({
        "output": str(output_path),
        "spot": audit["spot"],
        "market": {
            "bid": audit["target_market"]["bid"],
            "ask": audit["target_market"]["ask"],
            "mid": audit["target_market"]["mid"],
            "iv": audit["target_market"]["iv"],
        },
        "models": audit["model_prices"],
    }, indent=2))


if __name__ == "__main__":
    main()
