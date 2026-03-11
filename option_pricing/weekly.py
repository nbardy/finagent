from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from .black_scholes import option_delta, option_price
from .models import (
    OptionContractSpec,
    OptionMarketSnapshot,
    display_expiry,
    dte_and_time_to_expiry,
    normalize_expiry,
)
from .probe import price_option_probe
from .yahoo import YAHOO_DELAY_WARNING, fetch_risk_free_rate, fetch_spot


@dataclass(frozen=True)
class CoverBucket:
    strike: float
    expiry: str
    qty_available: int
    avg_cost: float


def load_cover_inventory(path: str = "config/portfolio_state.json") -> list[CoverBucket]:
    state_path = Path(path)
    if not state_path.exists():
        raise RuntimeError(f"Portfolio state not found at {path}. Run portfolio.py first.")

    with state_path.open() as handle:
        payload = json.load(handle)

    buckets = []
    for item in payload.get("unencumbered_leaps", []):
        qty_available = int(item.get("qty_available", item.get("qty", 0)))
        if qty_available <= 0:
            continue
        buckets.append(CoverBucket(
            strike=float(item["strike"]),
            expiry=normalize_expiry(item["expiry"]),
            qty_available=qty_available,
            avg_cost=float(item.get("avg_cost", 0.0)),
        ))
    buckets.sort(key=lambda bucket: (bucket.strike, bucket.expiry))
    return buckets


def covered_buckets_for_strike(buckets: list[CoverBucket], short_strike: float) -> list[CoverBucket]:
    return [bucket for bucket in buckets if bucket.strike <= float(short_strike)]


def safe_cover_quantity(buckets: list[CoverBucket], short_strike: float) -> int:
    return sum(bucket.qty_available for bucket in covered_buckets_for_strike(buckets, short_strike))


def nearest_weekly_expiry(
    symbol: str,
    min_dte: int = 3,
    max_dte: int = 10,
    now: datetime | None = None,
) -> str:
    current = now or datetime.now()
    ticker = yf.Ticker(symbol)
    expiries = []
    for expiry_display in ticker.options:
        expiry = normalize_expiry(expiry_display)
        expiry_dt = datetime.strptime(expiry, "%Y%m%d")
        dte = (expiry_dt - current).days
        if min_dte <= dte <= max_dte:
            expiries.append((expiry, dte))
    if not expiries:
        raise RuntimeError(
            f"No weekly expiry found for {symbol} in {min_dte}-{max_dte} DTE window."
        )
    expiries.sort(key=lambda item: item[1])
    return expiries[0][0]


def realized_volatility(
    symbol: str,
    lookback_days: int = 30,
    fallback: float = 0.25,
) -> float:
    ticker = yf.Ticker(symbol)
    history = ticker.history(period=f"{max(lookback_days * 3, 90)}d", auto_adjust=False)
    closes = history.get("Close")
    if closes is None:
        return fallback
    closes = closes.dropna()
    if closes.empty or len(closes) < lookback_days + 1:
        return fallback

    log_returns = np.log(closes / closes.shift(1)).dropna().tail(lookback_days)
    if log_returns.empty:
        return fallback

    rv = float(log_returns.std(ddof=1) * math.sqrt(252.0))
    if not math.isfinite(rv) or rv <= 0.0:
        return fallback
    return rv


def probe_steps_for_price(anchor_price: float) -> tuple[int, ...]:
    if anchor_price < 0.25:
        return (1, 0)
    if anchor_price < 0.75:
        return (2, 1, 0)
    if anchor_price < 1.50:
        return (3, 2, 1, 0)
    return (4, 2, 0)


def project_weekly_candidate_scenario(
    candidate: dict,
    spot_move_pct: float = 0.0,
    iv_multiplier: float = 1.0,
    iv_shift: float = 0.0,
) -> dict:
    contract = candidate["contract"]
    market = candidate["market"]
    _, time_to_expiry = dte_and_time_to_expiry(contract.expiry)

    base_iv = market.implied_volatility if market.implied_volatility > 0 else 0.25
    scenario_iv = max(0.05, base_iv * iv_multiplier + iv_shift)
    scenario_spot = market.spot * (1.0 + spot_move_pct)

    base_model = option_price(
        spot=market.spot,
        strike=contract.strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=market.risk_free_rate,
        volatility=base_iv,
        right=contract.right,
        dividend_yield=market.dividend_yield,
    )
    scenario_model = option_price(
        spot=scenario_spot,
        strike=contract.strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=market.risk_free_rate,
        volatility=scenario_iv,
        right=contract.right,
        dividend_yield=market.dividend_yield,
    )
    model_shift = scenario_model - base_model

    base_bid = max(market.bid, 0.0)
    base_ask = max(market.ask, market.mid, market.last, 0.01)
    base_mid = market.mid if market.mid > 0 else max((base_bid + base_ask) / 2.0, 0.01)

    proxy_bid = max(base_bid + model_shift, 0.0)
    proxy_ask = max(base_ask + model_shift, 0.01)
    proxy_mid = max(base_mid + model_shift, 0.01)
    proxy_mid = min(max(proxy_mid, proxy_bid), proxy_ask)

    scenario_delta = option_delta(
        spot=scenario_spot,
        strike=contract.strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=market.risk_free_rate,
        volatility=scenario_iv,
        right=contract.right,
        dividend_yield=market.dividend_yield,
    )
    scenario_market = OptionMarketSnapshot(
        spot=scenario_spot,
        bid=round(proxy_bid, 4),
        ask=round(proxy_ask, 4),
        last=round(proxy_mid, 4),
        implied_volatility=scenario_iv,
        risk_free_rate=market.risk_free_rate,
        dividend_yield=market.dividend_yield,
        source=f"{market.source or 'scenario'}-scenario",
        quote_warning=market.quote_warning,
        volume=market.volume,
        open_interest=market.open_interest,
        quote_time=market.quote_time,
    )

    return {
        "spot_move_pct": round(spot_move_pct, 6),
        "scenario_spot": round(scenario_spot, 4),
        "scenario_iv": round(scenario_iv, 6),
        "base_model": round(base_model, 4),
        "scenario_model": round(scenario_model, 4),
        "model_shift": round(model_shift, 4),
        "delta_market": round(scenario_delta, 4),
        "prob_otm_estimate": round(max(0.0, 1.0 - max(0.0, scenario_delta)), 4),
        "proxy_market": scenario_market,
        "estimated_credit_mid": round(proxy_mid * candidate["safe_qty"] * 100.0, 2),
        "estimated_credit_ask": round(proxy_ask * candidate["safe_qty"] * 100.0, 2),
        "probe_steps": probe_steps_for_price(proxy_ask),
    }


def fetch_weekly_candidates(
    symbol: str,
    expiry: str,
    cover_buckets: list[CoverBucket],
    min_strike: float | None = None,
    max_strike: float | None = None,
    right: str = "C",
    default_rate: float = 0.045,
    dividend_yield: float = 0.0,
) -> dict:
    ticker = yf.Ticker(symbol)
    expiry_display = display_expiry(expiry)
    if expiry_display not in list(ticker.options):
        raise RuntimeError(f"Expiry {expiry_display} is not available for {symbol}.")

    chain = ticker.option_chain(expiry_display)
    frame = chain.calls if right.upper() == "C" else chain.puts
    spot = fetch_spot(ticker)
    risk_free_rate = fetch_risk_free_rate(default_rate)
    rv30 = realized_volatility(symbol)

    frame = frame.copy()
    frame = frame[frame["strike"].notna()]
    if min_strike is not None:
        frame = frame[frame["strike"] >= float(min_strike)]
    if max_strike is not None:
        frame = frame[frame["strike"] <= float(max_strike)]

    candidates = []
    for _, row in frame.iterrows():
        strike = float(row["strike"])
        bid = float(row["bid"]) if not pd.isna(row["bid"]) else 0.0
        ask = float(row["ask"]) if not pd.isna(row["ask"]) else 0.0
        last = float(row["lastPrice"]) if not pd.isna(row["lastPrice"]) else 0.0
        if ask <= 0.0 and bid <= 0.0 and last <= 0.0:
            continue

        safe_qty = safe_cover_quantity(cover_buckets, strike)
        if safe_qty <= 0:
            continue

        implied_volatility = (
            float(row["impliedVolatility"])
            if not pd.isna(row["impliedVolatility"]) and float(row["impliedVolatility"]) > 0.0
            else rv30
        )
        market = OptionMarketSnapshot(
            spot=spot,
            bid=bid,
            ask=ask,
            last=last,
            implied_volatility=implied_volatility,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
            source="yfinance",
            quote_warning=YAHOO_DELAY_WARNING,
            volume=int(row["volume"]) if not pd.isna(row["volume"]) else None,
            open_interest=int(row["openInterest"]) if not pd.isna(row["openInterest"]) else None,
            quote_time=str(row["lastTradeDate"]) if not pd.isna(row["lastTradeDate"]) else None,
        )
        contract = OptionContractSpec(symbol=symbol, expiry=expiry, strike=strike, right=right)

        tv_market_iv = option_price(
            spot=spot,
            strike=strike,
            time_to_expiry=max((datetime.strptime(expiry, "%Y%m%d") - datetime.now()).days, 1) / 365.0,
            risk_free_rate=risk_free_rate,
            volatility=implied_volatility,
            right=right,
            dividend_yield=dividend_yield,
        )
        tv_rv = option_price(
            spot=spot,
            strike=strike,
            time_to_expiry=max((datetime.strptime(expiry, "%Y%m%d") - datetime.now()).days, 1) / 365.0,
            risk_free_rate=risk_free_rate,
            volatility=rv30,
            right=right,
            dividend_yield=dividend_yield,
        )
        delta_market = option_delta(
            spot=spot,
            strike=strike,
            time_to_expiry=max((datetime.strptime(expiry, "%Y%m%d") - datetime.now()).days, 1) / 365.0,
            risk_free_rate=risk_free_rate,
            volatility=implied_volatility,
            right=right,
            dividend_yield=dividend_yield,
        )
        mid = market.mid
        spread_pct = market.spread_pct
        prob_otm = max(0.0, 1.0 - max(0.0, delta_market))
        edge_vs_rv = mid - tv_rv
        estimated_credit_mid = mid * safe_qty * 100.0
        estimated_credit_ask = ask * safe_qty * 100.0 if ask > 0 else 0.0
        score = (estimated_credit_mid / 1000.0) + (edge_vs_rv * 5.0) + (prob_otm * 2.0) - spread_pct

        probe = price_option_probe(
            contract=contract,
            market=market,
            total_qty=safe_qty,
            action="SELL",
            probe_qty=1,
            steps=probe_steps_for_price(ask if ask > 0 else max(mid, last, 0.05)),
        )

        candidates.append({
            "contract": contract,
            "market": market,
            "cover_buckets": [
                {
                    "strike": bucket.strike,
                    "expiry": bucket.expiry,
                    "qty_available": bucket.qty_available,
                }
                for bucket in covered_buckets_for_strike(cover_buckets, strike)
            ],
            "safe_qty": safe_qty,
            "theoretical_value_market_iv": round(tv_market_iv, 4),
            "theoretical_value_rv30": round(tv_rv, 4),
            "delta_market": round(delta_market, 4),
            "prob_otm_estimate": round(prob_otm, 4),
            "edge_vs_rv30": round(edge_vs_rv, 4),
            "estimated_credit_mid": round(estimated_credit_mid, 2),
            "estimated_credit_ask": round(estimated_credit_ask, 2),
            "score": round(score, 4),
            "probe_proposal": probe,
        })

    candidates.sort(
        key=lambda item: (
            item["score"],
            item["estimated_credit_mid"],
            item["prob_otm_estimate"],
        ),
        reverse=True,
    )
    return {
        "symbol": symbol,
        "spot": round(spot, 4),
        "expiry": normalize_expiry(expiry),
        "risk_free_rate": round(risk_free_rate, 6),
        "realized_volatility_30d": round(rv30, 6),
        "candidates": candidates,
    }
