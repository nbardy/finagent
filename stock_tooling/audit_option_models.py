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
from typing import Any
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ib_insync import Option

from ibkr import connect, select_chain_strikes

from stratoforge.pricing.black_scholes import implied_volatility_from_price, option_price
from stratoforge.pricing.calibrate import MarketQuote, calibrate_all
from stratoforge.pricing.heston import heston_price
from stratoforge.pricing.merton_jump import mjd_price
from stratoforge.pricing.models import dte_and_time_to_expiry, normalize_expiry
from stratoforge.pricing.variance_gamma import vg_price
from stock_tooling.pricing_support import (
    PricingToolError,
    build_failure_payload,
    ensure_expiry_or_raise,
    ensure_strike_or_raise,
    load_smart_chain_or_raise,
)


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


def _identity(symbol: str, expiry: str, strike: float, right: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "expiry": expiry,
        "strike": strike,
        "right": right,
    }


def _failure_defaults() -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "chain_quotes_used": 0,
        "consensus_summary": {"count": 0, "mean": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0},
        "rich_model_summary": {"count": 0, "mean": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0},
        "model_prices": {},
    }


def _failure(
    symbol: str,
    expiry: str,
    strike: float,
    right: str,
    *,
    status: str,
    reason: str,
    used_fallback: bool = False,
    fallback_source: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return build_failure_payload(
        _identity(symbol, expiry, strike, right),
        status=status,
        reason=reason,
        used_fallback=used_fallback,
        fallback_source=fallback_source,
        defaults=_failure_defaults(),
        **extra,
    )


def fetch_option_slice(
    symbol: str,
    expiry: str,
    right: str,
    target_strike: float,
    span_steps: int,
    client_id: int,
    settle_secs: float,
) -> tuple[float, dict, list[MarketQuote]]:
    expiry = normalize_expiry(expiry)
    right = right.upper()

    with connect(client_id=client_id, readonly=True, market_data_type=3, debug=False) as ib:
        identity = _identity(symbol, expiry, target_strike, right)
        defaults = _failure_defaults()
        chain = load_smart_chain_or_raise(
            ib,
            symbol,
            identity={**identity, "expiry": "", "strike": 0.0, "right": ""},
            defaults=defaults,
        )
        ensure_expiry_or_raise(
            chain,
            expiry,
            identity=identity,
            defaults=defaults,
        )
        ensure_strike_or_raise(
            chain,
            target_strike,
            identity=identity,
            defaults=defaults,
        )

        strikes = select_chain_strikes(chain, target_strike, span_steps)
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

        quotes: list[MarketQuote] = []
        target_snapshot: dict | None = None
        quote_rows: list[dict] = []

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
            greeks_present = bool(greeks and (iv > 0 or delta != 0 or und_price > 0))

            quote_row = {
                "expiry": ticker.contract.lastTradeDateOrContractMonth,
                "strike": float(ticker.contract.strike),
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": last,
                "iv": iv,
                "delta": delta,
                "und_price": und_price,
                "market_data_type": market_data_type,
                "greeks_present": greeks_present,
                "quote_present": bid > 0 and ask > 0,
            }
            quote_rows.append(quote_row)

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
                    "greeks_present": greeks_present,
                    "quote_present": bid > 0 and ask > 0,
                }

        if target_snapshot is None:
            raise PricingToolError(
                _failure(
                    symbol,
                    expiry,
                    target_strike,
                    right,
                    status="target_unavailable",
                    reason="Target option was not returned by IBKR.",
                    chain={"expirations": list(chain.expirations[:25]), "strikes_sample": [round(x, 2) for x in strikes]},
                    quotes=quote_rows,
                )
            )
        if spot <= 0:
            spot = _safe_float(target_snapshot.get("und_price"))
        if spot <= 0:
            raise PricingToolError(
                _failure(
                    symbol,
                    expiry,
                    target_strike,
                    right,
                    status="missing_underlying_price",
                    reason="Could not recover underlying price from IBKR option greeks.",
                    target_market=target_snapshot,
                    chain={"expirations": list(chain.expirations[:25]), "strikes_sample": [round(x, 2) for x in strikes]},
                    quotes=quote_rows,
                )
            )

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

    try:
        ibkr_spot, target_snapshot, quotes = fetch_option_slice(
            symbol=symbol,
            expiry=expiry,
            right=right,
            target_strike=strike,
            span_steps=span_steps,
            client_id=client_id,
            settle_secs=settle_secs,
        )
    except PricingToolError as exc:
        return exc.payload

    final_spot = spot if spot and spot > 0 else ibkr_spot

    dte, T = dte_and_time_to_expiry(expiry)
    market_mid = float(target_snapshot["mid"])
    target_iv = float(target_snapshot["iv"])
    used_fallback = False
    fallback_source: str | None = None
    if target_iv <= 0 and market_mid > 0:
        implied = implied_volatility_from_price(final_spot, strike, T, risk_free_rate, market_mid, right, dividend_yield)
        target_iv = implied or 0.0
        if target_iv > 0:
            used_fallback = True
            fallback_source = "market_mid_implied_volatility"
    if target_iv <= 0:
        return _failure(
            symbol,
            expiry,
            strike,
            right,
            status="missing_iv",
            reason="Could not determine target implied volatility for BS audit.",
            target_market=target_snapshot,
            chain_quotes_used=len(quotes),
        )

    bs_price = option_price(final_spot, strike, T, risk_free_rate, target_iv, right, dividend_yield)

    model_prices = {
        "BSM": {
            "price": round(bs_price, 4),
            "source_iv": round(target_iv, 6),
        }
    }

    if len(quotes) >= 3:
        try:
            calibrations = calibrate_all(final_spot, risk_free_rate, quotes, dividend_yield)
        except Exception as exc:
            return _failure(
                symbol,
                expiry,
                strike,
                right,
                status="calibration_failed",
                reason=f"Model calibration failed: {type(exc).__name__}: {exc}",
                used_fallback=used_fallback,
                fallback_source=fallback_source,
                target_market={**target_snapshot, "spot_used": round(final_spot, 4)},
                chain_quotes_used=len(quotes),
                model_prices=model_prices,
            )

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
        "status": "success",
        "reason": None,
        "used_fallback": used_fallback,
        "fallback_source": fallback_source,
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

    try:
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
    except Exception as exc:
        audit = _failure(
            args.symbol.upper(),
            normalize_expiry(args.expiry),
            args.strike,
            args.right.upper(),
            status="unexpected_error",
            reason=f"{type(exc).__name__}: {exc}",
        )

    output_path = Path(args.output) if args.output else _default_output_path(
        audit["symbol"],
        audit["expiry"],
        float(audit["strike"]),
        audit["right"],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, indent=2) + "\n")

    if audit.get("status") == "success":
        print(json.dumps({
            "output": str(output_path),
            "status": audit["status"],
            "spot": audit["spot"],
            "market": {
                "bid": audit["target_market"]["bid"],
                "ask": audit["target_market"]["ask"],
                "mid": audit["target_market"]["mid"],
                "iv": audit["target_market"]["iv"],
            },
            "models": audit["model_prices"],
        }, indent=2))
    else:
        print(json.dumps({
            "output": str(output_path),
            "status": audit.get("status"),
            "reason": audit.get("reason"),
            "target_market": audit.get("target_market"),
            "chain_quotes_used": audit.get("chain_quotes_used", 0),
        }, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
