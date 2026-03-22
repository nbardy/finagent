from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf


DEFAULT_PERIOD_MONTHS = (1, 3, 6, 12, 60)
ANALYSIS_ROOT = Path(__file__).resolve().parents[1] / "analysis"


@dataclass(frozen=True)
class AnchoredMove:
    months: int
    target_date: str
    anchor_date: str | None
    anchor_close: float | None
    latest_close: float | None
    pct_change: float | None


@dataclass(frozen=True)
class ValuationSnapshot:
    currency: str | None
    financial_currency: str | None
    market_value: float | None
    market_value_kind: str | None
    market_value_source: str | None
    free_cash_flow: float | None
    free_cash_flow_source: str | None
    trailing_pe: float | None
    forward_pe: float | None
    fcf_yield_pct: float | None
    price_to_fcf: float | None


@dataclass(frozen=True)
class EquitySnapshot:
    symbol: str
    name: str | None
    quote_type: str | None
    exchange: str | None
    as_of: str | None
    latest_close: float | None
    valuation: ValuationSnapshot
    moves: dict[str, AnchoredMove]
    notes: list[str]
    error: str | None = None


def _is_valid_number(value: Any) -> bool:
    return value is not None and not pd.isna(value)


def _normalize_close_history(history: pd.DataFrame) -> pd.Series:
    if history.empty or "Close" not in history:
        return pd.Series(dtype=float)
    close = history["Close"].dropna().astype(float).sort_index()
    index = pd.to_datetime(close.index)
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    close.index = index
    return close


def build_anchored_moves(
    close: pd.Series,
    periods_months: tuple[int, ...] = DEFAULT_PERIOD_MONTHS,
) -> dict[str, AnchoredMove]:
    if close.empty:
        return {
            _period_label(months): AnchoredMove(
                months=months,
                target_date="",
                anchor_date=None,
                anchor_close=None,
                latest_close=None,
                pct_change=None,
            )
            for months in periods_months
        }

    latest_ts = pd.Timestamp(close.index[-1])
    latest_close = float(close.iloc[-1])
    moves: dict[str, AnchoredMove] = {}

    for months in periods_months:
        target_ts = latest_ts - pd.DateOffset(months=months)
        eligible = close[close.index <= target_ts]
        anchor_ts = pd.Timestamp(eligible.index[-1]) if not eligible.empty else None
        anchor_close = float(eligible.iloc[-1]) if not eligible.empty else None
        pct_change = None
        if anchor_close and anchor_close != 0:
            pct_change = round(((latest_close / anchor_close) - 1.0) * 100.0, 2)

        moves[_period_label(months)] = AnchoredMove(
            months=months,
            target_date=target_ts.date().isoformat(),
            anchor_date=anchor_ts.date().isoformat() if anchor_ts is not None else None,
            anchor_close=round(anchor_close, 4) if anchor_close is not None else None,
            latest_close=round(latest_close, 4),
            pct_change=pct_change,
        )

    return moves


def _period_label(months: int) -> str:
    if months >= 12 and months % 12 == 0:
        return f"{months // 12}y"
    return f"{months}m"


def extract_market_value(info: dict[str, Any]) -> tuple[float | None, str | None, str | None]:
    market_cap = info.get("marketCap")
    if _is_valid_number(market_cap):
        return float(market_cap), "market_cap", "info.marketCap"

    total_assets = info.get("totalAssets")
    if str(info.get("quoteType") or "").upper() == "ETF" and _is_valid_number(total_assets):
        return float(total_assets), "net_assets", "info.totalAssets"

    return None, None, None


def extract_free_cash_flow(
    info: dict[str, Any],
    cashflow: pd.DataFrame,
) -> tuple[float | None, str | None]:
    free_cash_flow = info.get("freeCashflow")
    if _is_valid_number(free_cash_flow):
        return float(free_cash_flow), "info.freeCashflow"

    if cashflow.empty or "Free Cash Flow" not in cashflow.index:
        return None, None

    fcf_series = cashflow.loc["Free Cash Flow"].dropna()
    if fcf_series.empty:
        return None, None

    latest_period = pd.Timestamp(fcf_series.index[0]).date().isoformat()
    return float(fcf_series.iloc[0]), f"cashflow.Free Cash Flow[{latest_period}]"


def _build_valuation_snapshot(
    info: dict[str, Any],
    cashflow: pd.DataFrame,
) -> tuple[ValuationSnapshot, list[str]]:
    market_value, market_value_kind, market_value_source = extract_market_value(info)
    free_cash_flow, free_cash_flow_source = extract_free_cash_flow(info, cashflow)

    currency = info.get("currency")
    financial_currency = info.get("financialCurrency")
    trailing_pe = info.get("trailingPE")
    forward_pe = info.get("forwardPE")
    notes: list[str] = []

    if trailing_pe is None:
        notes.append("trailingPE unavailable from provider")
    if forward_pe is None:
        notes.append("forwardPE unavailable from provider")
    if free_cash_flow is None:
        notes.append("freeCashflow unavailable from provider")
    if market_value_kind == "net_assets":
        notes.append("ETF uses net assets because marketCap is not provided")

    fcf_yield_pct = None
    price_to_fcf = None
    same_currency = (
        currency is None
        or financial_currency is None
        or str(currency).upper() == str(financial_currency).upper()
    )
    if free_cash_flow is not None and not same_currency:
        notes.append("fcf-based ratios disabled because quote currency differs from financial statement currency")

    if (
        market_value is not None
        and market_value_kind == "market_cap"
        and free_cash_flow is not None
        and same_currency
        and market_value != 0
    ):
        fcf_yield_pct = round((free_cash_flow / market_value) * 100.0, 2)
        if free_cash_flow != 0:
            price_to_fcf = round(market_value / free_cash_flow, 2)

    return (
        ValuationSnapshot(
            currency=currency,
            financial_currency=financial_currency,
            market_value=market_value,
            market_value_kind=market_value_kind,
            market_value_source=market_value_source,
            free_cash_flow=free_cash_flow,
            free_cash_flow_source=free_cash_flow_source,
            trailing_pe=float(trailing_pe) if _is_valid_number(trailing_pe) else None,
            forward_pe=float(forward_pe) if _is_valid_number(forward_pe) else None,
            fcf_yield_pct=fcf_yield_pct,
            price_to_fcf=price_to_fcf,
        ),
        notes,
    )


def fetch_equity_snapshot(symbol: str) -> EquitySnapshot:
    ticker = yf.Ticker(symbol)

    try:
        history = ticker.history(period="6y", auto_adjust=False)
    except Exception as exc:
        return EquitySnapshot(
            symbol=symbol,
            name=None,
            quote_type=None,
            exchange=None,
            as_of=None,
            latest_close=None,
            valuation=ValuationSnapshot(
                currency=None,
                financial_currency=None,
                market_value=None,
                market_value_kind=None,
                market_value_source=None,
                free_cash_flow=None,
                free_cash_flow_source=None,
                trailing_pe=None,
                forward_pe=None,
                fcf_yield_pct=None,
                price_to_fcf=None,
            ),
            moves={},
            notes=[],
            error=str(exc),
        )

    close = _normalize_close_history(history)
    if close.empty:
        return EquitySnapshot(
            symbol=symbol,
            name=None,
            quote_type=None,
            exchange=None,
            as_of=None,
            latest_close=None,
            valuation=ValuationSnapshot(
                currency=None,
                financial_currency=None,
                market_value=None,
                market_value_kind=None,
                market_value_source=None,
                free_cash_flow=None,
                free_cash_flow_source=None,
                trailing_pe=None,
                forward_pe=None,
                fcf_yield_pct=None,
                price_to_fcf=None,
            ),
            moves={},
            notes=[],
            error="No price history returned by provider",
        )

    try:
        info = ticker.info or {}
    except Exception as exc:
        info = {}
        info_error = f"info_error: {exc}"
    else:
        info_error = None

    cashflow = ticker.cashflow
    valuation, notes = _build_valuation_snapshot(info, cashflow)
    if info_error:
        notes.insert(0, info_error)

    latest_close = float(close.iloc[-1])
    return EquitySnapshot(
        symbol=symbol,
        name=info.get("longName") or info.get("shortName"),
        quote_type=info.get("quoteType"),
        exchange=info.get("exchange"),
        as_of=close.index[-1].date().isoformat(),
        latest_close=round(latest_close, 4),
        valuation=valuation,
        moves=build_anchored_moves(close),
        notes=notes,
    )


def build_snapshot_payload(symbols: list[str]) -> dict[str, Any]:
    items = [fetch_equity_snapshot(symbol) for symbol in symbols]
    return {
        "generated": date.today().isoformat(),
        "source": "yfinance",
        "source_detail": {
            "price_history": "yfinance.Ticker.history(period='6y', auto_adjust=False)",
            "company_info": "yfinance.Ticker.info",
            "cashflow": "yfinance.Ticker.cashflow",
        },
        "symbols": symbols,
        "items": [asdict(item) for item in items],
    }


def _default_output_path() -> Path:
    output_dir = ANALYSIS_ROOT / date.today().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "equity_snapshot.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch anchored price moves and valuation fields for equities or ETFs.",
    )
    parser.add_argument("--symbols", nargs="+", required=True, help="Ticker symbols to fetch.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path. Defaults to analysis/{today}/equity_snapshot.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_snapshot_payload(args.symbols)
    output_path = args.output or _default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
