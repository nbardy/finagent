from __future__ import annotations

import math
import unittest

from stratoforge.pricing.calibrate import MarketQuote, calibrate_heston
from stratoforge.pricing.heston import HestonParams, heston_price


class HestonCalibrationSolverTests(unittest.TestCase):
    def test_calibrate_heston_improves_over_naive_seed_and_returns_heston_params(self) -> None:
        spot = 658.0
        risk_free_rate = 0.045
        dividend_yield = 0.01
        true_params = HestonParams(v0=0.05, theta=0.045, kappa=2.5, xi=0.35, rho=-0.6)
        quotes = [
            MarketQuote(
                strike=strike,
                T=T,
                market_price=heston_price(
                    spot=spot,
                    strike=strike,
                    T=T,
                    r=risk_free_rate,
                    params=true_params,
                    right=right,
                    dividend_yield=dividend_yield,
                ),
                right=right,
                weight=1.0,
            )
            for T in (14 / 365, 35 / 365, 63 / 365)
            for strike, right in ((600.0, "P"), (640.0, "P"))
        ]

        def rmse(params: HestonParams) -> float:
            errors = []
            for quote in quotes:
                model_price = heston_price(
                    spot=spot,
                    strike=quote.strike,
                    T=quote.T,
                    r=risk_free_rate,
                    params=params,
                    right=quote.right,
                    dividend_yield=dividend_yield,
                )
                errors.append(model_price - quote.market_price)
            return math.sqrt(sum(error * error for error in errors) / len(errors))

        naive_params = HestonParams(v0=0.04, theta=0.02, kappa=1.5, xi=0.25, rho=-0.3)
        naive_rmse = rmse(naive_params)

        fitted = calibrate_heston(
            spot=spot,
            r=risk_free_rate,
            quotes=quotes,
            dividend_yield=dividend_yield,
        )

        self.assertEqual(fitted.model, "Heston")
        self.assertIsInstance(fitted.params, HestonParams)
        self.assertLess(fitted.rmse, naive_rmse)
        self.assertLess(fitted.rmse, 1.0)


if __name__ == "__main__":
    unittest.main()
