from __future__ import annotations

from datetime import date
import math
import unittest

from stratoforge.domain.contracts import ChainIndex, OptionContract
from stratoforge.domain.scenario_contract import ScenarioNode
from stratoforge.pricing.bates import BatesParams, bates_price
from stratoforge.pricing.calibrate import CalibrationResult
from stratoforge.pricing.heston import HestonParams, heston_price
from stratoforge.scoring import build_contract_scenario_tensor


class BatesPricingTests(unittest.TestCase):
    def test_bates_reduces_to_heston_when_jump_intensity_is_zero(self) -> None:
        heston_params = HestonParams(v0=0.05, theta=0.045, kappa=2.5, xi=0.4, rho=-0.65)
        bates_params = BatesParams(
            v0=heston_params.v0,
            theta=heston_params.theta,
            kappa=heston_params.kappa,
            xi=heston_params.xi,
            rho=heston_params.rho,
            lam=0.0,
            mu_j=-0.08,
            sigma_j=0.2,
        )
        cases = [
            (658.0, 540.0, 14 / 365, "P"),
            (658.0, 600.0, 30 / 365, "P"),
            (658.0, 680.0, 45 / 365, "C"),
        ]

        for spot, strike, time_to_expiry, right in cases:
            heston_value = heston_price(
                spot=spot,
                strike=strike,
                T=time_to_expiry,
                r=0.045,
                params=heston_params,
                right=right,
                dividend_yield=0.01,
            )
            bates_value = bates_price(
                spot=spot,
                strike=strike,
                T=time_to_expiry,
                r=0.045,
                params=bates_params,
                right=right,
                dividend_yield=0.01,
            )
            self.assertTrue(
                math.isclose(heston_value, bates_value, rel_tol=1e-8, abs_tol=1e-7),
                msg=(
                    f"Bates should collapse to Heston when lam=0. "
                    f"heston={heston_value:.10f} bates={bates_value:.10f}"
                ),
            )

    def test_bates_calibration_flows_into_contract_tensor(self) -> None:
        asof_date = date(2026, 3, 22)
        expiry = date(2026, 4, 17)
        chain = ChainIndex((
            OptionContract(
                symbol="SPY",
                expiry=expiry,
                strike=600.0,
                right="P",
                bid=12.8,
                ask=13.2,
                mid=13.0,
                iv=0.24,
            ),
        ))
        calibration = CalibrationResult(
            params=BatesParams(
                v0=0.24**2,
                theta=0.22**2,
                kappa=2.0,
                xi=0.45,
                rho=-0.7,
                lam=1.0,
                mu_j=-0.06,
                sigma_j=0.14,
            ),
            rmse=0.0,
            max_error=0.0,
            per_strike_errors=[],
            n_quotes=1,
            model="Bates",
        )
        tensor = build_contract_scenario_tensor(
            chain,
            scenarios=(ScenarioNode(label="down", horizon_days=5, probability=1.0, spot_move_pct=-0.06),),
            asof_date=asof_date,
            spot_now=658.0,
            risk_free_rate=0.045,
            dividend_yield=0.01,
            calibrations={"Bates": calibration},
            surface_fit=None,
        )

        entry = tensor[f"{expiry.isoformat()}|P|600"]["down"]
        self.assertIn("Bates", entry["models_used"])
        self.assertIn("Bates", entry["model_values"])


if __name__ == "__main__":
    unittest.main()
