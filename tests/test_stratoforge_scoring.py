from __future__ import annotations

from datetime import date
import unittest

from stratoforge.pricing.bates import BatesParams
from stratoforge.pricing.calibrate import CalibrationResult
from stratoforge.pricing.heston import HestonParams
from stratoforge.pricing.merton_jump import MJDParams
from stratoforge.pricing.variance_gamma import VGParams
from stratoforge.domain.scenario_contract import ScenarioNode
from stratoforge.domain.setup import PotentialLeg, PotentialSetup
from stratoforge.domain.thesis import ThesisBranch, ThesisSchema
from stratoforge.scoring import (
    _consensus_model_names,
    _select_structural_models_for_consensus,
    build_scenario_nodes,
    score_candidate_universe,
)


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

    def test_frontier_consensus_prefers_bates_and_heston_over_weak_models(self) -> None:
        calibrations = {
            "Bates": CalibrationResult(
                params=BatesParams(v0=0.05, theta=0.04, kappa=2.0, xi=0.4, rho=-0.7, lam=1.0, mu_j=-0.05, sigma_j=0.12),
                rmse=0.04,
                max_error=0.09,
                per_strike_errors=[],
                n_quotes=25,
                model="Bates",
            ),
            "Heston": CalibrationResult(
                params=HestonParams(v0=0.05, theta=0.04, kappa=2.0, xi=0.4, rho=-0.7),
                rmse=0.13,
                max_error=0.3,
                per_strike_errors=[],
                n_quotes=25,
                model="Heston",
            ),
            "MJD": CalibrationResult(
                params=MJDParams(sigma=0.24, lam=1.2, mu_j=-0.07, sigma_j=0.15),
                rmse=0.44,
                max_error=1.2,
                per_strike_errors=[],
                n_quotes=25,
                model="MJD",
            ),
            "VG": CalibrationResult(
                params=VGParams(sigma=0.24, theta=-0.12, nu=0.2),
                rmse=1.75,
                max_error=4.5,
                per_strike_errors=[],
                n_quotes=25,
                model="VG",
            ),
        }

        enabled = _select_structural_models_for_consensus(calibrations)
        self.assertEqual(enabled, ("Bates", "Heston"))
        self.assertEqual(
            _consensus_model_names(
                {
                    "BS": 10.0,
                    "SSVI": 11.0,
                    "Bates": 12.0,
                    "Heston": 13.0,
                    "MJD": 14.0,
                    "VG": 15.0,
                },
                enabled_structural_models=enabled,
            ),
            ("SSVI", "Bates", "Heston"),
        )


if __name__ == "__main__":
    unittest.main()
