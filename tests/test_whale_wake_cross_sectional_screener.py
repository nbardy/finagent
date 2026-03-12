import unittest
from datetime import datetime

from custom_scripts.whale_wake_cross_sectional_screener import (
    RankedOpportunity,
    build_order_payload,
    compute_volume_weighted_footprints,
    kelly_bet_size,
    select_target_expiries,
    size_position_contracts,
)


class WhaleWakeCrossSectionalScreenerTests(unittest.TestCase):
    def test_compute_volume_weighted_footprints_returns_positive_trend_metrics(self) -> None:
        closes = [100.0 + idx * 0.8 for idx in range(30)]
        highs = [price * 1.01 for price in closes]
        lows = [price * 0.99 for price in closes]
        volumes = [1_000_000 + idx * 25_000 for idx in range(30)]

        result = compute_volume_weighted_footprints(
            closes=closes,
            highs=highs,
            lows=lows,
            volumes=volumes,
            lookback_days=14,
        )

        self.assertGreater(result.mu, 0.0)
        self.assertGreaterEqual(result.hurst, 0.01)
        self.assertLessEqual(result.hurst, 0.99)
        self.assertGreaterEqual(result.sigma, 0.05)
        self.assertEqual(result.bar_count, 30)

    def test_select_target_expiries_picks_nearest_dates_in_window(self) -> None:
        now = datetime(2026, 3, 12)
        expiries = ["20260320", "20260327", "20260403", "20260417", "20260515"]

        result = select_target_expiries(
            expiries,
            target_dte=21,
            min_dte=5,
            max_dte=40,
            max_count=2,
            now=now,
        )

        self.assertEqual(result, ["20260403", "20260327"])

    def test_kelly_bet_size_caps_at_max_risk(self) -> None:
        self.assertEqual(kelly_bet_size(win_prob=0.90, edge_ratio=4.0, max_portfolio_risk_pct=0.05), 0.05)
        self.assertEqual(kelly_bet_size(win_prob=0.45, edge_ratio=1.10, max_portfolio_risk_pct=0.05), 0.0)

    def test_size_position_contracts_uses_ask_cost(self) -> None:
        budget, contracts = size_position_contracts(net_liq=100_000.0, option_ask=2.50, risk_fraction=0.02)

        self.assertEqual(budget, 2000.0)
        self.assertEqual(contracts, 8)

    def test_build_order_payload_emits_executor_shape(self) -> None:
        opportunity = RankedOpportunity(
            symbol="PLTR",
            spot=120.0,
            mu=1.2,
            hurst=0.67,
            sigma=0.42,
            expiry="20260403",
            strike=122.0,
            bid=1.15,
            ask=1.30,
            mid=1.225,
            market_iv=0.55,
            dte=22,
            theoretical_value=1.95,
            suggested_limit=1.25,
            edge_ratio=1.50,
            kelly_pct=0.03,
            budget_dollars=3000.0,
            contracts=5,
            has_open_orders=False,
            existing_option_position_qty=0,
        )

        payload = build_order_payload([opportunity], max_trades=1)

        self.assertEqual(payload["generated"], datetime.now().strftime("%Y-%m-%d"))
        self.assertEqual(len(payload["trades"]), 1)
        trade = payload["trades"][0]
        self.assertEqual(trade["intent"], "add")
        self.assertEqual(trade["action"], "BUY")
        self.assertEqual(trade["contract"]["symbol"], "PLTR")
        self.assertEqual(sum(tranche["quantity"] for tranche in trade["tranches"]), 5)


if __name__ == "__main__":
    unittest.main()
