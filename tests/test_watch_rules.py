import unittest

from stock_tooling.watch_rules import assess_watch_state, load_watch_rules


class WatchRulesTests(unittest.TestCase):
    def test_tight_two_sided_market_prefers_short_watch(self) -> None:
        rules = load_watch_rules()
        assessment = assess_watch_state(
            bid=1.00,
            ask=1.10,
            last=1.05,
            open_order_count=3,
            new_fill_count=0,
            observed_seconds=30,
            rules=rules,
        )

        self.assertEqual(assessment["liquidity_regime"], "tight")
        self.assertGreaterEqual(assessment["confidence"], 0.8)
        self.assertEqual(assessment["suggested_action"], "keep_watching")
        self.assertEqual(assessment["recommended_poll_seconds"], 20)

    def test_wide_one_sided_market_after_full_window_says_do_not_force(self) -> None:
        rules = load_watch_rules()
        assessment = assess_watch_state(
            bid=0.0,
            ask=1.25,
            last=0.0,
            open_order_count=3,
            new_fill_count=0,
            observed_seconds=1800,
            rules=rules,
        )

        self.assertEqual(assessment["quote_quality"], "one_sided")
        self.assertEqual(assessment["liquidity_regime"], "very_wide")
        self.assertEqual(assessment["suggested_action"], "do_not_force")
        self.assertLessEqual(assessment["confidence"], 0.3)

    def test_fill_signal_can_flip_assessment_to_bulk_ready(self) -> None:
        rules = load_watch_rules()
        assessment = assess_watch_state(
            bid=0.90,
            ask=1.00,
            last=0.95,
            open_order_count=4,
            new_fill_count=2,
            new_fill_qty=8,
            total_target_qty=16,
            observed_seconds=120,
            rules=rules,
        )

        self.assertEqual(assessment["suggested_action"], "bulk_ready")
        self.assertGreaterEqual(assessment["confidence"], rules.thresholds.bulk_ready_confidence)


if __name__ == "__main__":
    unittest.main()
