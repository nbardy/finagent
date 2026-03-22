from __future__ import annotations

from datetime import date
import unittest

from stratoforge.domain.scenario_contract import ScenarioNode
from stratoforge.domain.setup import PotentialLeg, PotentialSetup
from stratoforge.domain.thesis import ThesisBranch, ThesisSchema
from stratoforge.scoring import build_scenario_nodes, score_candidate_universe


class StratoforgeScoringTests(unittest.TestCase):
    def test_build_scenario_nodes_normalizes_probabilities(self) -> None:
        thesis = ThesisSchema(
            symbol="SPY",
            asof_date=date(2026, 3, 19),
            spot=100.0,
            objective="hold_down",
            branches=(
                ThesisBranch(label="a", horizon_days=5, move_pct=-0.05, probability=2.0),
                ThesisBranch(label="b", horizon_days=10, move_pct=-0.1, probability=1.0),
            ),
        )

        scenarios = build_scenario_nodes(thesis)

        self.assertAlmostEqual(sum(s.probability for s in scenarios), 1.0, places=6)
        self.assertAlmostEqual(scenarios[0].probability, 2.0 / 3.0, places=6)
        self.assertAlmostEqual(scenarios[1].probability, 1.0 / 3.0, places=6)

    def test_score_candidate_universe_ranks_by_expected_value(self) -> None:
        expiry = date(2026, 4, 17)
        candidate_a = PotentialSetup(
            family="long_put",
            kernel="single_option",
            name="A",
            legs=(PotentialLeg(action="BUY", right="P", expiry=expiry, strike=100.0, qty=1),),
            entry_style="debit",
            path_model_required="terminal",
            assignment_risk="low",
            canonical_id="a",
            estimated_net_debit=50.0,
            anchor_source="spot",
            anchor_label="spot",
            anchor_price=100.0,
        )
        candidate_b = PotentialSetup(
            family="long_put",
            kernel="single_option",
            name="B",
            legs=(PotentialLeg(action="BUY", right="P", expiry=expiry, strike=95.0, qty=1),),
            entry_style="debit",
            path_model_required="terminal",
            assignment_risk="low",
            canonical_id="b",
            estimated_net_debit=40.0,
            anchor_source="spot",
            anchor_label="spot",
            anchor_price=100.0,
        )
        scenarios = (
            ScenarioNode(label="down", horizon_days=5, probability=0.8, spot_move_pct=-0.1),
            ScenarioNode(label="up", horizon_days=5, probability=0.2, spot_move_pct=0.02),
        )
        tensor = {
            "2026-04-17|P|100": {
                "down": {"pnl_from_mid": 100.0, "model_dispersion_per_contract": 0.0, "models_used": ["BS"]},
                "up": {"pnl_from_mid": -10.0, "model_dispersion_per_contract": 0.0, "models_used": ["BS"]},
            },
            "2026-04-17|P|95": {
                "down": {"pnl_from_mid": 60.0, "model_dispersion_per_contract": 0.0, "models_used": ["BS"]},
                "up": {"pnl_from_mid": 10.0, "model_dispersion_per_contract": 0.0, "models_used": ["BS"]},
            },
        }

        ranked = score_candidate_universe(
            [candidate_a, candidate_b],
            contract_tensor=tensor,
            scenarios=scenarios,
        )

        self.assertEqual(ranked[0]["name"], "A")
        self.assertGreater(ranked[0]["expected_value"], ranked[1]["expected_value"])


if __name__ == "__main__":
    unittest.main()
