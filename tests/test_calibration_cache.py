from __future__ import annotations

from dataclasses import dataclass
from tempfile import TemporaryDirectory
import unittest

from stratoforge.pricing.bates import BatesParams
from stratoforge.pricing.calibration_cache import (
    CalibrationCache,
    build_calibration_key,
    quote_slice_hash,
)
from stratoforge.pricing.heston import HestonParams
from stratoforge.pricing.merton_jump import MJDParams
from stratoforge.pricing.variance_gamma import VGParams


@dataclass(frozen=True)
class QuoteStub:
    strike: float
    T: float
    market_price: float
    right: str
    weight: float = 1.0


class CalibrationCacheTests(unittest.TestCase):
    def test_quote_slice_hash_is_order_invariant(self) -> None:
        quotes_a = [
            QuoteStub(600.0, 0.1, 12.5, "P", 0.9),
            QuoteStub(610.0, 0.2, 9.1, "P", 0.8),
        ]
        quotes_b = list(reversed(quotes_a))

        self.assertEqual(quote_slice_hash(quotes_a), quote_slice_hash(quotes_b))

    def test_quote_slice_hash_changes_when_quote_changes(self) -> None:
        quotes_a = [QuoteStub(600.0, 0.1, 12.5, "P")]
        quotes_b = [QuoteStub(600.0, 0.1, 12.6, "P")]

        self.assertNotEqual(quote_slice_hash(quotes_a), quote_slice_hash(quotes_b))

    def test_cache_round_trip_supports_all_model_param_types(self) -> None:
        params_cases = [
            ("Heston", HestonParams(v0=0.04, theta=0.05, kappa=2.0, xi=0.4, rho=-0.6)),
            ("VG", VGParams(sigma=0.25, theta=-0.1, nu=0.2)),
            ("MJD", MJDParams(sigma=0.24, lam=1.0, mu_j=-0.05, sigma_j=0.12)),
            (
                "Bates",
                BatesParams(
                    v0=0.04,
                    theta=0.05,
                    kappa=2.0,
                    xi=0.4,
                    rho=-0.6,
                    lam=1.0,
                    mu_j=-0.05,
                    sigma_j=0.12,
                ),
            ),
        ]
        quotes = [
            QuoteStub(600.0, 0.1, 12.5, "P"),
            QuoteStub(610.0, 0.2, 9.1, "P"),
        ]

        with TemporaryDirectory() as tmpdir:
            cache_path = f"{tmpdir}/calibration_cache.json"
            cache = CalibrationCache(cache_path)
            for model, params in params_cases:
                key = build_calibration_key(
                    model=model,
                    spot=658.0,
                    risk_free_rate=0.045,
                    dividend_yield=0.01,
                    quotes=quotes,
                )
                cache.put(
                    key=key,
                    params=params,
                    diagnostics={"rmse": 0.1234, "max_error": 0.25, "model": model},
                    quotes=quotes,
                )

            cache.save()
            loaded = CalibrationCache.load(cache_path)
            self.assertEqual(len(loaded), 4)

            for model, params in params_cases:
                key = build_calibration_key(
                    model=model,
                    spot=658.0,
                    risk_free_rate=0.045,
                    dividend_yield=0.01,
                    quotes=quotes,
                )
                entry = loaded.get(key)
                self.assertIsNotNone(entry)
                assert entry is not None
                self.assertEqual(entry.key.cache_id(), key.cache_id())
                self.assertEqual(entry.params, params)
                self.assertEqual(entry.diagnostics["model"], model)
                self.assertEqual(len(entry.quote_slice), 2)

    def test_cache_key_changes_with_pricing_inputs(self) -> None:
        quotes = [QuoteStub(600.0, 0.1, 12.5, "P")]
        key_a = build_calibration_key(
            model="Heston",
            spot=658.0,
            risk_free_rate=0.045,
            dividend_yield=0.01,
            quotes=quotes,
        )
        key_b = build_calibration_key(
            model="Heston",
            spot=659.0,
            risk_free_rate=0.045,
            dividend_yield=0.01,
            quotes=quotes,
        )
        key_c = build_calibration_key(
            model="Heston",
            spot=658.0,
            risk_free_rate=0.050,
            dividend_yield=0.01,
            quotes=quotes,
        )

        self.assertNotEqual(key_a.cache_id(), key_b.cache_id())
        self.assertNotEqual(key_a.cache_id(), key_c.cache_id())


if __name__ == "__main__":
    unittest.main()
