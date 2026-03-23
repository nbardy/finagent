from __future__ import annotations

import math
import unittest

from stratoforge.pricing.bates import BatesParams, bates_price, bates_price_fixed_grid
from stratoforge.pricing.heston import HestonParams, heston_price, heston_price_fixed_grid


class FixedGridPricerTests(unittest.TestCase):
    def test_heston_fixed_grid_tracks_quad_reference(self) -> None:
        params = HestonParams(v0=0.04, theta=0.05, kappa=3.0, xi=0.35, rho=-0.6)
        cases = [
            (658.0, strike, T, "P")
            for T in (7 / 365, 21 / 365, 63 / 365)
            for strike in (520.0, 600.0, 640.0)
        ]

        for spot, strike, time_to_expiry, right in cases:
            reference = heston_price(spot, strike, time_to_expiry, 0.045, params, right, 0.01)
            fixed_grid = heston_price_fixed_grid(
                spot,
                strike,
                time_to_expiry,
                0.045,
                params,
                right,
                0.01,
                grid_size=1024,
            )
            self.assertTrue(
                math.isclose(reference, fixed_grid, rel_tol=0.01, abs_tol=0.12),
                msg=f"Heston fixed-grid mismatch ref={reference:.6f} fast={fixed_grid:.6f}",
            )

    def test_bates_fixed_grid_tracks_quad_reference(self) -> None:
        params = BatesParams(
            v0=0.04,
            theta=0.05,
            kappa=3.0,
            xi=0.35,
            rho=-0.6,
            lam=1.0,
            mu_j=-0.05,
            sigma_j=0.12,
        )
        cases = [
            (658.0, strike, T, "P")
            for T in (7 / 365, 21 / 365, 63 / 365)
            for strike in (520.0, 600.0, 640.0)
        ]

        for spot, strike, time_to_expiry, right in cases:
            reference = bates_price(spot, strike, time_to_expiry, 0.045, params, right, 0.01)
            fixed_grid = bates_price_fixed_grid(
                spot,
                strike,
                time_to_expiry,
                0.045,
                params,
                right,
                0.01,
                grid_size=1024,
            )
            self.assertTrue(
                math.isclose(reference, fixed_grid, rel_tol=0.015, abs_tol=0.15),
                msg=f"Bates fixed-grid mismatch ref={reference:.6f} fast={fixed_grid:.6f}",
            )


if __name__ == "__main__":
    unittest.main()
