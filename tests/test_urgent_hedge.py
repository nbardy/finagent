import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from helpers.urgent_hedge import (
    build_execution_bundle,
    evaluate_candidate,
    get_us_equity_option_session_state,
    macro_scenario_set_from_dict,
    portfolio_book_from_dict,
    quote_structure,
    rank_candidates,
    select_default_expiries,
)
from helpers.urgent_hedge_types import HedgeStructureSpec


US_EASTERN = ZoneInfo("America/New_York")


class MacroScenarioTests(unittest.TestCase):
    def test_macro_loader_normalizes_probabilities_from_legacy_shape(self) -> None:
        payload = {
            "spot": 132.73,
            "risk_free_rate": 0.045,
            "book": {
                "positions": [
                    {"label": "EWY 150C", "right": "C", "strike": 150, "dte": 60, "qty": 10, "mark": 5.0, "iv": 0.5}
                ]
            },
            "scenarios": [
                {"label": "Flat", "days": 7, "spot": 132.73, "vol_shift": 0.0, "probability": 2.0},
                {"label": "Down", "days": 7, "spot": 125.0, "vol_shift": 0.05, "probability": 1.0},
            ],
        }
        loaded = macro_scenario_set_from_dict(payload, path_label="legacy")
        self.assertEqual(loaded.symbol, "EWY")
        self.assertAlmostEqual(sum(s.probability for s in loaded.scenarios), 1.0, places=6)
        self.assertAlmostEqual(loaded.scenarios[0].spot_move_pct, 0.0, places=6)
        self.assertLess(loaded.scenarios[1].spot_move_pct, 0.0)


class PortfolioBookTests(unittest.TestCase):
    def test_portfolio_book_loader_requires_explicit_iv(self) -> None:
        payload = {
            "spot": 132.73,
            "risk_free_rate": 0.045,
            "book": {
                "positions": [
                    {"label": "EWY 150C", "right": "C", "strike": 150, "dte": 90, "qty": 10, "mark": 7.5}
                ]
            },
        }
        with self.assertRaises(ValueError):
            portfolio_book_from_dict(payload, default_symbol="EWY")


class SessionStateTests(unittest.TestCase):
    def test_regular_session_state(self) -> None:
        state = get_us_equity_option_session_state(
            now=datetime(2026, 3, 11, 11, 0, tzinfo=US_EASTERN),
            close_buffer_minutes=15,
        )
        self.assertEqual(state.mode, "regular")
        self.assertTrue(state.is_open)

    def test_near_close_session_state(self) -> None:
        state = get_us_equity_option_session_state(
            now=datetime(2026, 3, 11, 15, 52, tzinfo=US_EASTERN),
            close_buffer_minutes=15,
        )
        self.assertEqual(state.mode, "near_close")
        self.assertTrue(state.is_open)

    def test_closed_session_state(self) -> None:
        state = get_us_equity_option_session_state(
            now=datetime(2026, 3, 11, 16, 30, tzinfo=US_EASTERN),
            close_buffer_minutes=15,
        )
        self.assertEqual(state.mode, "closed")
        self.assertFalse(state.is_open)


class HedgeEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = pd.DataFrame([
            {
                "strike": 135.0,
                "bid": 8.2,
                "ask": 8.8,
                "lastPrice": 8.5,
                "impliedVolatility": 0.62,
                "volume": 100,
                "openInterest": 1000,
            },
            {
                "strike": 125.0,
                "bid": 4.0,
                "ask": 4.4,
                "lastPrice": 4.2,
                "impliedVolatility": 0.66,
                "volume": 100,
                "openInterest": 900,
            },
            {
                "strike": 120.0,
                "bid": 2.7,
                "ask": 3.0,
                "lastPrice": 2.9,
                "impliedVolatility": 0.7,
                "volume": 100,
                "openInterest": 800,
            },
        ])
        self.scenarios = macro_scenario_set_from_dict(
            {
                "name": "ewy_test",
                "symbol": "EWY",
                "as_of": "2026-03-11T11:00:00-04:00",
                "reference_spot": 132.73,
                "risk_free_rate": 0.045,
                "scenarios": [
                    {
                        "label": "Bounce",
                        "horizon_days": 7,
                        "spot_move_pct": 0.03,
                        "vol_shift": -0.03,
                        "probability": 0.3,
                    },
                    {
                        "label": "Pullback",
                        "horizon_days": 7,
                        "spot_move_pct": -0.06,
                        "vol_shift": 0.03,
                        "probability": 0.7,
                    },
                ],
            }
        )
        self.book = portfolio_book_from_dict(
            {
                "symbol": "EWY",
                "spot": 132.73,
                "risk_free_rate": 0.045,
                "positions": [
                    {"label": "EWY 150C", "right": "C", "strike": 150, "dte": 300, "qty": 100, "mark": 30.0, "iv": 0.5}
                ],
            }
        )

    def test_quote_structure_resolves_nearest_strikes(self) -> None:
        spec = HedgeStructureSpec(
            name="test spread",
            expiry="20260417",
            structure="put_spread",
            long_strike=134.0,
            short_strike=124.0,
        )
        resolved, combo, max_value = quote_structure("EWY", spec, 132.73, self.frame)
        self.assertEqual(resolved.long_strike, 135.0)
        self.assertEqual(resolved.short_strike, 125.0)
        self.assertAlmostEqual(combo.combo_ask, 4.8, places=6)
        self.assertAlmostEqual(max_value, 10.0, places=6)

    def test_evaluate_candidate_scores_downside_cover(self) -> None:
        spec = HedgeStructureSpec(
            name="test spread",
            expiry="20260417",
            structure="put_spread",
            long_strike=135.0,
            short_strike=125.0,
        )
        resolved, combo, max_value = quote_structure("EWY", spec, 132.73, self.frame)
        candidate = evaluate_candidate(
            spec=resolved,
            combo=combo,
            max_value=max_value,
            scenario_set=self.scenarios,
            budget=10000,
            book=self.book,
        )
        self.assertGreater(candidate.target_quantity, 0)
        self.assertGreaterEqual(candidate.conditional_downside_coverage_pct, 0.0)
        self.assertEqual(len(candidate.scenario_outcomes), 2)

    def test_rank_candidates_prefers_higher_coverage(self) -> None:
        spec_one = HedgeStructureSpec(name="spread one", expiry="20260417", structure="put_spread", long_strike=135.0, short_strike=125.0)
        spec_two = HedgeStructureSpec(name="spread two", expiry="20260417", structure="put_spread", long_strike=135.0, short_strike=120.0)
        _, combo_one, max_one = quote_structure("EWY", spec_one, 132.73, self.frame)
        _, combo_two, max_two = quote_structure("EWY", spec_two, 132.73, self.frame)
        first = evaluate_candidate(spec_one, combo_one, max_one, self.scenarios, budget=10000, book=self.book)
        second = evaluate_candidate(spec_two, combo_two, max_two, self.scenarios, budget=10000, book=self.book)
        ranked = rank_candidates([first, second])
        self.assertEqual(len(ranked), 2)
        self.assertGreaterEqual(ranked[0].conditional_downside_coverage_pct, ranked[1].conditional_downside_coverage_pct)


class ExpirySelectionTests(unittest.TestCase):
    def test_select_default_expiries(self) -> None:
        expiries = ["20260313", "20260320", "20260327", "20260417", "20260515"]
        selected = select_default_expiries(expiries, as_of=datetime(2026, 3, 11, 12, 0, tzinfo=US_EASTERN))
        self.assertEqual(selected["crash"], "20260320")
        self.assertEqual(selected["swing"], "20260327")
        self.assertEqual(selected["core"], "20260417")


class ExecutionBundleTests(unittest.TestCase):
    def test_build_execution_bundle_writes_expected_shapes(self) -> None:
        frame = pd.DataFrame([
            {
                "strike": 135.0,
                "bid": 8.2,
                "ask": 8.8,
                "lastPrice": 8.5,
                "impliedVolatility": 0.62,
            },
            {
                "strike": 120.0,
                "bid": 2.7,
                "ask": 3.0,
                "lastPrice": 2.9,
                "impliedVolatility": 0.7,
            },
        ])
        scenario_set = macro_scenario_set_from_dict(
            {
                "name": "ewy_test",
                "symbol": "EWY",
                "as_of": "2026-03-11T11:00:00-04:00",
                "reference_spot": 132.73,
                "risk_free_rate": 0.045,
                "scenarios": [
                    {
                        "label": "Pullback",
                        "horizon_days": 7,
                        "spot_move_pct": -0.05,
                        "vol_shift": 0.02,
                        "probability": 1.0,
                    }
                ],
            }
        )
        spec = HedgeStructureSpec(name="spread", expiry="20260417", structure="put_spread", long_strike=135.0, short_strike=120.0)
        resolved, combo, max_value = quote_structure("EWY", spec, 132.73, frame)
        candidate = evaluate_candidate(resolved, combo, max_value, scenario_set, budget=10000)
        with tempfile.TemporaryDirectory() as temp_dir:
            plan, artifacts = build_execution_bundle(
                candidate=candidate,
                scenario_set=scenario_set,
                budget=10000,
                output_prefix="ewy_test",
                output_dir=temp_dir,
                session=get_us_equity_option_session_state(now=datetime(2026, 3, 11, 16, 30, tzinfo=US_EASTERN)),
            )
            self.assertEqual(plan.recommended_artifact, "open_ready")
            self.assertIn("probe", artifacts)
            self.assertIn("open_ready", artifacts)
            self.assertEqual(artifacts["probe"]["trades"][0]["contract"]["secType"], "BAG")
            self.assertEqual(sum(t["quantity"] for t in artifacts["open_ready"]["trades"][0]["tranches"]), candidate.target_quantity)


if __name__ == "__main__":
    unittest.main()
