import pandas as pd

from stock_tooling.equity_snapshot import (
    _build_valuation_snapshot,
    _period_label,
    build_anchored_moves,
    extract_free_cash_flow,
    extract_market_value,
)


def test_build_anchored_moves_uses_last_close_on_or_before_target() -> None:
    close = pd.Series(
        [100.0, 111.0],
        index=pd.to_datetime(["2026-02-11", "2026-03-12"]),
    )

    moves = build_anchored_moves(close, periods_months=(1,))

    assert moves["1m"].target_date == "2026-02-12"
    assert moves["1m"].anchor_date == "2026-02-11"
    assert moves["1m"].anchor_close == 100.0
    assert moves["1m"].latest_close == 111.0
    assert moves["1m"].pct_change == 11.0


def test_period_label_uses_years_for_12m_and_above() -> None:
    assert _period_label(1) == "1m"
    assert _period_label(12) == "1y"
    assert _period_label(60) == "5y"


def test_extract_market_value_falls_back_to_total_assets_for_etf() -> None:
    value, kind, source = extract_market_value({"quoteType": "ETF", "totalAssets": 7_440_000_000})

    assert value == 7_440_000_000.0
    assert kind == "net_assets"
    assert source == "info.totalAssets"


def test_extract_free_cash_flow_prefers_info_then_cashflow() -> None:
    info_value, info_source = extract_free_cash_flow({"freeCashflow": 123.0}, pd.DataFrame())

    assert info_value == 123.0
    assert info_source == "info.freeCashflow"

    cashflow = pd.DataFrame(
        {
            pd.Timestamp("2025-03-31"): [456.0],
        },
        index=["Free Cash Flow"],
    )

    fallback_value, fallback_source = extract_free_cash_flow({}, cashflow)

    assert fallback_value == 456.0
    assert fallback_source == "cashflow.Free Cash Flow[2025-03-31]"


def test_build_valuation_snapshot_disables_cross_currency_fcf_ratios() -> None:
    valuation, notes = _build_valuation_snapshot(
        {
            "currency": "USD",
            "financialCurrency": "JPY",
            "marketCap": 1000.0,
            "freeCashflow": 200.0,
        },
        pd.DataFrame(),
    )

    assert valuation.fcf_yield_pct is None
    assert valuation.price_to_fcf is None
    assert "fcf-based ratios disabled because quote currency differs from financial statement currency" in notes
