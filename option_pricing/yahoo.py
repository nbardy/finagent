from __future__ import annotations

from datetime import datetime

import pandas as pd
import yfinance as yf

from .models import OptionContractSpec, OptionMarketSnapshot, display_expiry


YAHOO_DELAY_WARNING = (
    "Yahoo Finance quotes are public snapshots and may be delayed. "
    "Verify against your broker before transmitting orders."
)


def fetch_spot(ticker: yf.Ticker) -> float:
    try:
        fast_info = ticker.fast_info
        if fast_info:
            for key in ("lastPrice", "regularMarketPrice", "previousClose"):
                value = fast_info.get(key)
                if value is not None and not pd.isna(value):
                    return float(value)
    except Exception:
        pass

    history = ticker.history(period="5d", auto_adjust=False)
    if history.empty:
        raise RuntimeError("Unable to fetch underlying price from Yahoo Finance.")
    return float(history["Close"].dropna().iloc[-1])


def fetch_risk_free_rate(default_rate: float = 0.045) -> float:
    try:
        irx = yf.Ticker("^IRX")
        history = irx.history(period="5d", auto_adjust=False)
        if not history.empty:
            close = float(history["Close"].dropna().iloc[-1])
            rate = close / 100.0
            if 0.0 < rate < 1.0:
                return rate
    except Exception:
        pass
    return default_rate


def _pick_contract_frame(
    quotes: pd.DataFrame,
    spot: float,
    strike: float | None,
) -> tuple[pd.Series, list[dict]]:
    valid = quotes.copy()
    valid = valid[valid["strike"].notna()]
    valid = valid[valid["bid"].notna() & valid["ask"].notna()]
    valid = valid[(valid["bid"] > 0) & (valid["ask"] > 0)]

    if valid.empty:
        raise RuntimeError("No options with usable bid/ask quotes were returned.")

    if strike is not None:
        chosen_frame = valid[valid["strike"] == float(strike)]
        if chosen_frame.empty:
            available = ", ".join(f"{s:.2f}" for s in valid["strike"].sort_values().tolist()[:20])
            raise RuntimeError(
                f"Strike {strike:.2f} was not found in the Yahoo chain. "
                f"First available strikes: {available}"
            )
        chosen = chosen_frame.iloc[0]
    else:
        chosen = valid.iloc[(valid["strike"] - spot).abs().argsort().iloc[0]]

    nearest = valid.assign(distance=(valid["strike"] - spot).abs())
    nearest = nearest.sort_values(["distance", "strike"]).head(5)
    rows = []
    for _, row in nearest.iterrows():
        rows.append({
            "strike": float(row["strike"]),
            "bid": float(row["bid"]),
            "ask": float(row["ask"]),
            "implied_volatility": float(row["impliedVolatility"])
            if not pd.isna(row["impliedVolatility"])
            else None,
        })

    return chosen, rows


def fetch_option_snapshot(
    symbol: str,
    expiry: str,
    strike: float | None = None,
    right: str = "C",
    default_rate: float = 0.045,
    dividend_yield: float = 0.0,
) -> tuple[OptionContractSpec, OptionMarketSnapshot, list[dict]]:
    ticker = yf.Ticker(symbol)
    expiry_display = display_expiry(expiry)
    expirations = list(ticker.options)
    if expiry_display not in expirations:
        raise RuntimeError(
            f"Expiry {expiry_display} not available from Yahoo Finance. "
            f"Available expirations: {', '.join(expirations)}"
        )

    chain = ticker.option_chain(expiry_display)
    frame = chain.calls if right.upper() == "C" else chain.puts
    spot = fetch_spot(ticker)
    chosen, nearest = _pick_contract_frame(frame, spot=spot, strike=strike)

    contract = OptionContractSpec(
        symbol=symbol,
        expiry=expiry,
        strike=float(chosen["strike"]),
        right=right,
    )
    market = OptionMarketSnapshot(
        spot=spot,
        bid=float(chosen["bid"]),
        ask=float(chosen["ask"]),
        last=float(chosen["lastPrice"]) if not pd.isna(chosen["lastPrice"]) else 0.0,
        implied_volatility=float(chosen["impliedVolatility"])
        if not pd.isna(chosen["impliedVolatility"]) and float(chosen["impliedVolatility"]) > 0
        else 0.25,
        risk_free_rate=fetch_risk_free_rate(default_rate),
        dividend_yield=dividend_yield,
        source="yfinance",
        quote_warning=YAHOO_DELAY_WARNING,
        volume=int(chosen["volume"]) if not pd.isna(chosen["volume"]) else None,
        open_interest=int(chosen["openInterest"]) if not pd.isna(chosen["openInterest"]) else None,
        quote_time=str(chosen["lastTradeDate"]) if not pd.isna(chosen["lastTradeDate"]) else None,
    )
    return contract, market, nearest
