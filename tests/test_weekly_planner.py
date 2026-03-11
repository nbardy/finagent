import unittest

from option_pricing import (
    CoverBucket,
    OptionContractSpec,
    OptionMarketSnapshot,
    covered_buckets_for_strike,
    project_weekly_candidate_scenario,
    probe_steps_for_price,
    safe_cover_quantity,
)


class WeeklyPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.buckets = [
            CoverBucket(strike=145.0, expiry="20280121", qty_available=18, avg_cost=43.97),
            CoverBucket(strike=150.0, expiry="20280121", qty_available=90, avg_cost=41.98),
            CoverBucket(strike=210.0, expiry="20280121", qty_available=110, avg_cost=24.45),
        ]

    def test_covered_buckets_only_include_eligible_strikes(self) -> None:
        covered = covered_buckets_for_strike(self.buckets, 151.0)
        self.assertEqual([bucket.strike for bucket in covered], [145.0, 150.0])

    def test_safe_cover_quantity_sums_eligible_buckets(self) -> None:
        self.assertEqual(safe_cover_quantity(self.buckets, 151.0), 108)
        self.assertEqual(safe_cover_quantity(self.buckets, 145.0), 18)
        self.assertEqual(safe_cover_quantity(self.buckets, 210.0), 218)

    def test_probe_steps_scale_for_cheap_weeklies(self) -> None:
        self.assertEqual(probe_steps_for_price(0.20), (1, 0))
        self.assertEqual(probe_steps_for_price(0.55), (2, 1, 0))
        self.assertEqual(probe_steps_for_price(1.10), (3, 2, 1, 0))

    def test_scenario_projection_raises_proxy_quote_on_positive_gap(self) -> None:
        candidate = {
            "contract": OptionContractSpec(symbol="EWY", expiry="20260313", strike=151.0, right="C"),
            "market": OptionMarketSnapshot(
                spot=133.89,
                bid=0.05,
                ask=0.55,
                last=0.20,
                implied_volatility=0.668949,
                risk_free_rate=0.03593,
                dividend_yield=0.0,
                source="yfinance",
            ),
            "safe_qty": 108,
        }
        scenario = project_weekly_candidate_scenario(candidate, spot_move_pct=0.03)

        self.assertGreater(scenario["scenario_spot"], 133.89)
        self.assertGreater(scenario["proxy_market"].ask, 0.55)


if __name__ == "__main__":
    unittest.main()
