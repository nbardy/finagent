import math
import unittest
from unittest.mock import patch

from ibkr import get_option_quotes, get_portfolio, get_spot


class FakeModelGreeks:
    def __init__(self, implied_vol: float = 0.0, delta: float = 0.0, gamma: float = 0.0, theta: float = 0.0, vega: float = 0.0) -> None:
        self.impliedVol = implied_vol
        self.delta = delta
        self.gamma = gamma
        self.theta = theta
        self.vega = vega


class FakeOptionTicker:
    def __init__(self, contract, bid: float = math.nan, ask: float = math.nan, last: float = math.nan, model_greeks=None) -> None:
        self.contract = contract
        self.bid = bid
        self.ask = ask
        self.last = last
        self.modelGreeks = model_greeks


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


class FakeQuoteIB:
    def qualifyContracts(self, *contracts):
        return list(contracts)

    def reqTickers(self, *contracts):
        return [
            FakeOptionTicker(contract=contract)
            for contract in contracts
        ]

    def sleep(self, _seconds: float) -> None:
        return None


class FakeContract:
    def __init__(
        self,
        *,
        symbol: str = "SIVE",
        sec_type: str = "STK",
        currency: str = "SEK",
        con_id: int = 123,
        right: str = "",
        strike: float = 0.0,
        expiry: str = "",
    ) -> None:
        self.symbol = symbol
        self.secType = sec_type
        self.currency = currency
        self.conId = con_id
        self.right = right
        self.strike = strike
        self.lastTradeDateOrContractMonth = expiry


class FakePortfolioItem:
    def __init__(
        self,
        *,
        contract: FakeContract,
        position: int,
        average_cost: float,
        market_price: float,
        market_value: float,
        unrealized_pnl: float,
        realized_pnl: float,
    ) -> None:
        self.contract = contract
        self.position = position
        self.averageCost = average_cost
        self.marketPrice = market_price
        self.marketValue = market_value
        self.unrealizedPNL = unrealized_pnl
        self.realizedPNL = realized_pnl


class FakePortfolioIB:
    def __init__(self, items) -> None:
        self._items = list(items)

    def portfolio(self):
        return list(self._items)


class IbkrSpotTests(unittest.TestCase):
    def test_get_spot_raises_without_explicit_close_fallback(self) -> None:
        ib = FakeIB(FakeTicker(market_price=math.nan, close=123.45))
        with self.assertRaises(ValueError):
            get_spot(ib, "EWY")

    def test_get_spot_can_use_explicit_close_fallback(self) -> None:
        ib = FakeIB(FakeTicker(market_price=math.nan, close=123.45))
        self.assertEqual(get_spot(ib, "EWY", allow_close_fallback=True), 123.45)


class IbkrOptionQuoteTests(unittest.TestCase):
    def test_get_option_quotes_returns_zeroed_quote_when_market_data_is_missing(self) -> None:
        ib = FakeQuoteIB()

        quotes = get_option_quotes(ib, "EWY", [(220.0, "20280121", "C")])

        self.assertEqual(len(quotes), 1)
        quote = quotes[0]
        self.assertFalse(quote.has_market)
        self.assertEqual(quote.bid, 0.0)
        self.assertEqual(quote.ask, 0.0)
        self.assertEqual(quote.last, 0.0)
        self.assertEqual(quote.mid, 0.0)
        self.assertEqual(quote.iv, 0.0)
        self.assertEqual(quote.delta, 0.0)
        self.assertEqual(quote.gamma, 0.0)
        self.assertEqual(quote.theta, 0.0)
        self.assertEqual(quote.vega, 0.0)


class IbkrPortfolioTests(unittest.TestCase):
    def test_get_portfolio_populates_explicit_base_currency_fields(self) -> None:
        item = FakePortfolioItem(
            contract=FakeContract(),
            position=100,
            average_cost=10.0,
            market_price=12.0,
            market_value=1200.0,
            unrealized_pnl=200.0,
            realized_pnl=50.0,
        )
        ib = FakePortfolioIB([item])

        with patch("ibkr._get_base_currency", return_value="USD"), patch("ibkr._get_fx_rate", return_value=0.1):
            [position] = get_portfolio(ib)

        self.assertEqual(position.currency, "SEK")
        self.assertEqual(position.base_currency, "USD")
        self.assertEqual(position.fx_rate_to_base, 0.1)
        self.assertEqual(position.local_market_price, 12.0)
        self.assertEqual(position.base_market_price, 1.2)
        self.assertEqual(position.market_price, 1.2)
        self.assertEqual(position.local_market_value, 1200.0)
        self.assertEqual(position.base_market_value, 120.0)
        self.assertEqual(position.market_value, 120.0)
        self.assertEqual(position.local_unrealized_pnl, 200.0)
        self.assertEqual(position.base_unrealized_pnl, 20.0)
        self.assertEqual(position.unrealized_pnl, 20.0)
        self.assertEqual(position.base_cost_basis, 100.0)
        self.assertEqual(position.cost_basis, 100.0)
