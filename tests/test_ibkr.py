import math
import unittest

from ibkr import get_spot


class FakeTicker:
    def __init__(self, market_price: float, close: float) -> None:
        self._market_price = market_price
        self.close = close
        self.bid = 0.0
        self.ask = 0.0
        self.last = 0.0

    def marketPrice(self) -> float:
        return self._market_price


class FakeIB:
    def __init__(self, ticker: FakeTicker) -> None:
        self._ticker = ticker

    def qualifyContracts(self, *_contracts) -> None:
        return None

    def reqTickers(self, *_contracts):
        return [self._ticker]

    def sleep(self, _seconds: float) -> None:
        return None


class IbkrSpotTests(unittest.TestCase):
    def test_get_spot_raises_without_explicit_close_fallback(self) -> None:
        ib = FakeIB(FakeTicker(market_price=math.nan, close=123.45))
        with self.assertRaises(ValueError):
            get_spot(ib, "EWY")

    def test_get_spot_can_use_explicit_close_fallback(self) -> None:
        ib = FakeIB(FakeTicker(market_price=math.nan, close=123.45))
        self.assertEqual(get_spot(ib, "EWY", allow_close_fallback=True), 123.45)
