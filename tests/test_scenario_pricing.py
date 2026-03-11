import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from helpers.scenario_pricing import option_lines_future_value, option_value_under_linear_path, ScenarioOptionLine
from stock_tooling.portfolio_scenario_ev import (
    analyze,
    apply_macro_scenario_set,
    pure_hedge_config,
    refresh_market_snapshot,
)


class ScenarioPricingTests(unittest.TestCase):
    def test_option_value_uses_intrinsic_at_interpolated_expiry_when_scenario_runs_past_expiry(self) -> None:
        value = option_value_under_linear_path(
            spot_now=100.0,
            scenario_spot=70.0,
            scenario_days=30,
            strike=100.0,
            right="P",
            dte=10,
            iv=0.6,
            vol_shift=0.0,
            risk_free_rate=0.0,
        )
        self.assertAlmostEqual(value, 10.0, places=6)

    def test_option_value_marks_with_remaining_time_before_expiry(self) -> None:
        value = option_value_under_linear_path(
            spot_now=100.0,
            scenario_spot=90.0,
            scenario_days=5,
            strike=100.0,
            right="P",
            dte=10,
            iv=0.6,
            vol_shift=0.0,
            risk_free_rate=0.0,
        )
        self.assertGreater(value, 10.0)

    def test_option_lines_future_value_handles_mixed_expiries(self) -> None:
        value = option_lines_future_value(
            lines=[
                ScenarioOptionLine(right="P", strike=100.0, dte=10, qty=1, iv=0.6),
                ScenarioOptionLine(right="C", strike=110.0, dte=40, qty=-1, iv=0.5),
            ],
            spot_now=100.0,
            scenario_spot=70.0,
            scenario_days=30,
            vol_shift=0.0,
            risk_free_rate=0.0,
        )
        self.assertGreater(value, 0.0)


class PortfolioScenarioAnalyzerTests(unittest.TestCase):
    def test_analyzer_uses_linear_path_for_expired_hedge_legs(self) -> None:
        output = analyze(
            {
                "spot": 100.0,
                "risk_free_rate": 0.0,
                "book": {"positions": []},
                "scenarios": [
                    {
                        "label": "Month down",
                        "days": 30,
                        "spot": 70.0,
                        "vol_shift": 0.0,
                        "probability": 1.0,
                    }
                ],
                "hedges": [
                    {
                        "name": "Test put",
                        "entry_cost": 500.0,
                        "legs": [
                            {
                                "label": "Long 100P",
                                "right": "P",
                                "strike": 100.0,
                                "dte": 10,
                                "qty": 1,
                                "mark": 5.0,
                                "iv": 0.6,
                            }
                        ],
                    }
                ],
            }
        )
        scenario = output["scenarios"][0]["hedges"]["Test put"]
        self.assertEqual(scenario["book"]["pnl"], 0.0)
        self.assertAlmostEqual(scenario["overlay"]["pnl"], 500.0, places=2)
        self.assertAlmostEqual(scenario["combined"]["pnl"], 500.0, places=2)
        self.assertAlmostEqual(scenario["hedge_pnl"], 500.0, places=2)
        summary = output["summaries"]["Test put"]
        self.assertAlmostEqual(summary["book"]["expected_pnl"], 0.0, places=2)
        self.assertAlmostEqual(summary["overlay"]["expected_pnl"], 500.0, places=2)
        self.assertAlmostEqual(summary["combined"]["expected_pnl"], 500.0, places=2)
        self.assertAlmostEqual(summary["expected_overlay_pnl"], 500.0, places=2)

    def test_apply_macro_scenario_set_replaces_scenarios(self) -> None:
        config = {
            "spot": 100.0,
            "risk_free_rate": 0.0,
            "book": {"positions": []},
            "scenarios": [],
            "hedges": [],
        }
        with TemporaryDirectory() as tmpdir:
            macro_path = Path(tmpdir) / "macro.json"
            macro_path.write_text(
                """
                {
                  "name": "Test thesis",
                  "symbol": "EWY",
                  "as_of": "2026-03-11",
                  "reference_spot": 105.0,
                  "risk_free_rate": 0.03,
                  "scenarios": [
                    {
                      "label": "Down",
                      "horizon_days": 10,
                      "spot_move_pct": -0.1,
                      "vol_shift": 0.02,
                      "probability": 1.0
                    }
                  ]
                }
                """.strip()
            )
            updated = apply_macro_scenario_set(config, str(macro_path))

        self.assertEqual(updated["spot"], 100.0)
        self.assertEqual(updated["risk_free_rate"], 0.03)
        self.assertEqual(updated["scenarios"][0]["days"], 10)
        self.assertAlmostEqual(updated["scenarios"][0]["spot"], 90.0, places=6)
        self.assertEqual(updated["macro"]["name"], "Test thesis")

    def test_pure_hedge_config_zeros_book_positions(self) -> None:
        updated = pure_hedge_config(
            {
                "spot": 100.0,
                "book": {
                    "positions": [
                        {
                            "label": "Long call",
                            "right": "C",
                            "strike": 100.0,
                            "dte": 10,
                            "qty": 1,
                            "mark": 5.0,
                            "iv": 0.5,
                        }
                    ]
                },
            }
        )
        self.assertEqual(updated["book"]["positions"], [])

    def test_refresh_market_snapshot_prefers_ibkr_marks_and_rescales_scenarios(self) -> None:
        config = {
            "spot": 100.0,
            "risk_free_rate": 0.0,
            "book": {
                "positions": [
                    {
                        "label": "EWY 100C 20260417",
                        "right": "C",
                        "strike": 100.0,
                        "dte": 37,
                        "qty": 1,
                        "mark": 1.0,
                    }
                ]
            },
            "scenarios": [
                {
                    "label": "Down 10%",
                    "days": 10,
                    "spot": 90.0,
                    "vol_shift": 0.0,
                    "probability": 1.0,
                }
            ],
            "hedges": [
                {
                    "name": "Long Apr17 100P",
                    "entry_cost": 100.0,
                    "legs": [
                        {
                            "label": "Long Apr17 100P",
                            "right": "P",
                            "strike": 100.0,
                            "dte": 37,
                            "qty": 1,
                            "mark": 1.0,
                        }
                    ],
                }
            ],
        }

        def fake_quotes(_ib, _symbol, specs, debug=False):
            quotes = []
            for strike, expiry, right in specs:
                mid = 6.5 if right == "C" else 4.0
                quotes.append(
                    SimpleNamespace(
                        strike=strike,
                        expiry=expiry,
                        right=right,
                        bid=mid - 0.1,
                        ask=mid + 0.1,
                        mid=mid,
                        last=mid - 0.05,
                        iv=0.55 if right == "C" else 0.6,
                        has_market=True,
                    )
                )
            return quotes

        with patch("stock_tooling.portfolio_scenario_ev.connect") as mock_connect, patch(
            "stock_tooling.portfolio_scenario_ev.get_spot",
            return_value=105.0,
        ), patch(
            "stock_tooling.portfolio_scenario_ev.get_portfolio",
            return_value=[
                SimpleNamespace(
                    symbol="EWY",
                    sec_type="OPT",
                    right="C",
                    strike=100.0,
                    expiry="20260417",
                    dte=37,
                    qty=2,
                    market_price=6.0,
                )
            ],
        ), patch(
            "stock_tooling.portfolio_scenario_ev.get_option_quotes",
            side_effect=fake_quotes,
        ):
            mock_connect.return_value.__enter__.return_value = object()
            mock_connect.return_value.__exit__.return_value = False
            refreshed = refresh_market_snapshot(config, symbol="EWY", fallback_to_disk=False)

        self.assertTrue(refreshed["market_refresh"]["succeeded"])
        self.assertEqual(refreshed["spot"], 105.0)
        self.assertEqual(refreshed["scenarios"][0]["spot"], 94.5)
        self.assertEqual(len(refreshed["book"]["positions"]), 1)
        self.assertEqual(refreshed["book"]["positions"][0]["qty"], 2)
        self.assertEqual(refreshed["book"]["positions"][0]["mark"], 6.5)
        self.assertEqual(refreshed["hedges"][0]["legs"][0]["mark"], 4.0)
        self.assertEqual(refreshed["hedges"][0]["entry_cost"], 400.0)

    def test_refresh_market_snapshot_raises_when_quote_iv_missing(self) -> None:
        config = {
            "spot": 100.0,
            "risk_free_rate": 0.0,
            "book": {
                "positions": [
                    {
                        "label": "EWY 100C 20260417",
                        "right": "C",
                        "strike": 100.0,
                        "dte": 37,
                        "qty": 1,
                        "mark": 1.0,
                    }
                ]
            },
            "scenarios": [],
            "hedges": [],
        }

        def fake_quotes(_ib, _symbol, specs, debug=False):
            return [
                SimpleNamespace(
                    strike=strike,
                    expiry=expiry,
                    right=right,
                    bid=1.9,
                    ask=2.1,
                    mid=2.0,
                    last=2.0,
                    iv=0.0,
                    has_market=True,
                )
                for strike, expiry, right in specs
            ]

        with patch("stock_tooling.portfolio_scenario_ev.connect") as mock_connect, patch(
            "stock_tooling.portfolio_scenario_ev.get_spot",
            return_value=105.0,
        ), patch(
            "stock_tooling.portfolio_scenario_ev.get_portfolio",
            return_value=[],
        ), patch(
            "stock_tooling.portfolio_scenario_ev.get_option_quotes",
            side_effect=fake_quotes,
        ):
            mock_connect.return_value.__enter__.return_value = object()
            mock_connect.return_value.__exit__.return_value = False
            with self.assertRaises(ValueError):
                refresh_market_snapshot(config, symbol="EWY", fallback_to_disk=False)


if __name__ == "__main__":
    unittest.main()
