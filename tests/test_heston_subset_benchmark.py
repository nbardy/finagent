from __future__ import annotations

import unittest

from custom_scripts.benchmark_heston_subset_sensitivity import _select_quote_subset
from stratoforge.pricing.calibrate import MarketQuote


class HestonSubsetBenchmarkTests(unittest.TestCase):
    def test_select_quote_subset_is_deterministic_and_unique(self) -> None:
        quotes = [
            MarketQuote(strike=500.0 + idx * 5.0, T=idx / 12.0, market_price=1.0 + idx, right="P", weight=1.0)
            for idx in range(1, 11)
        ]

        subset = _select_quote_subset(quotes, 4)
        self.assertEqual(len(subset), 4)
        self.assertEqual(len({(quote.strike, quote.T, quote.right) for quote in subset}), 4)

        subset_again = _select_quote_subset(quotes, 4)
        self.assertEqual(
            [(quote.strike, quote.T, quote.right) for quote in subset],
            [(quote.strike, quote.T, quote.right) for quote in subset_again],
        )

    def test_select_quote_subset_returns_all_quots_when_requested_size_exceeds_available(self) -> None:
        quotes = [
            MarketQuote(strike=500.0 + idx * 5.0, T=idx / 12.0, market_price=1.0 + idx, right="P", weight=1.0)
            for idx in range(1, 6)
        ]

        subset = _select_quote_subset(quotes, 10)
        self.assertEqual(len(subset), len(quotes))


if __name__ == "__main__":
    unittest.main()
