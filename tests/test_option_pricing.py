import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ibkr import QuoteHealth
from stratoforge.pricing import (
    OptionContractSpec,
    OptionMarketSnapshot,
    bs_call,
    build_exit_tranches,
    build_probe_trades,
    implied_volatility_from_price,
    price_option_probe,
    price_option_exit,
    recommend_limit,
)
from stock_tooling.price_probe import ProbePricingError, _require_implied_volatility, price_probe


class BlackScholesTests(unittest.TestCase):
    def test_dividend_yield_reduces_call_value(self) -> None:
        no_dividend = bs_call(spot=100, strike=100, time_to_expiry=1.0, risk_free_rate=0.04, volatility=0.25)
        with_dividend = bs_call(
            spot=100,
            strike=100,
            time_to_expiry=1.0,
            risk_free_rate=0.04,
            volatility=0.25,
            dividend_yield=0.03,
        )
        self.assertLess(with_dividend, no_dividend)

    def test_implied_volatility_round_trip(self) -> None:
        expected_sigma = 0.32
        market_price = bs_call(
            spot=128.79,
            strike=165.0,
            time_to_expiry=311 / 365,
            risk_free_rate=0.035,
            volatility=expected_sigma,
            dividend_yield=0.01,
        )
        solved_sigma = implied_volatility_from_price(
            spot=128.79,
            strike=165.0,
            time_to_expiry=311 / 365,
            risk_free_rate=0.035,
            market_price=market_price,
            right="C",
            dividend_yield=0.01,
        )
        self.assertIsNotNone(solved_sigma)
        self.assertAlmostEqual(solved_sigma, expected_sigma, places=6)


class ExitPricingTests(unittest.TestCase):
    def test_sell_limit_respects_theoretical_floor(self) -> None:
        result = recommend_limit(theoretical_value=13.4288, bid=12.2, ask=14.0, action="SELL")
        self.assertGreaterEqual(result.suggested_limit, 13.45)
        self.assertLessEqual(result.suggested_limit, 14.0)

    def test_exit_tranches_sum_and_hold_floor(self) -> None:
        tranches = build_exit_tranches(
            suggested_limit=13.45,
            theoretical_value=13.4288,
            bid=12.2,
            ask=14.0,
            total_qty=100,
            n_tranches=5,
        )
        self.assertEqual(sum(t["quantity"] for t in tranches), 100)
        self.assertEqual(tranches[0]["lmtPrice"], 14.0)
        self.assertGreaterEqual(tranches[-1]["lmtPrice"], 13.45)

    def test_price_option_exit_returns_executor_shape(self) -> None:
        contract = OptionContractSpec(symbol="EWY", expiry="20270115", strike=165, right="C")
        market = OptionMarketSnapshot(
            spot=128.79,
            bid=12.2,
            ask=14.0,
            last=11.0,
            implied_volatility=0.5133,
            risk_free_rate=0.03588,
            dividend_yield=0.0,
            source="ibkr",
            market_data_type=3,
            model_underlying_price=128.2487,
            pv_dividend=1.9764,
        )
        proposal = price_option_exit(contract=contract, market=market, total_qty=100, action="SELL", n_tranches=5)

        self.assertEqual(proposal["contract"]["symbol"], "EWY")
        self.assertEqual(proposal["contract"]["lastTradeDateOrContractMonth"], "20270115")
        self.assertEqual(proposal["action"], "SELL")
        self.assertEqual(proposal["total_quantity"], 100)
        self.assertTrue(proposal["quote_status"]["is_delayed"])
        self.assertEqual(sum(t["quantity"] for t in proposal["tranches"]), 100)

    def test_probe_trades_hold_back_remainder(self) -> None:
        contract = OptionContractSpec(symbol="EWY", expiry="20280121", strike=145, right="C")
        payload = build_probe_trades(
            contract=contract,
            action="SELL",
            total_qty=22,
            anchor_price=29.80,
            probe_qty=1,
            steps=(6, 4, 2, 0),
        )

        self.assertEqual(payload["held_back_quantity"], 18)
        self.assertEqual(sum(t["quantity"] for t in payload["trades"]), 4)
        self.assertEqual([t["lmtPrice"] for t in payload["trades"]], [30.10, 30.0, 29.9, 29.8])

    def test_price_option_probe_returns_executor_shape(self) -> None:
        contract = OptionContractSpec(symbol="EWY", expiry="20280121", strike=145, right="C")
        market = OptionMarketSnapshot(
            spot=127.45,
            bid=28.0,
            ask=29.8,
            last=30.21,
            implied_volatility=0.5017,
            risk_free_rate=0.045,
            dividend_yield=0.0,
            source="ibkr",
            market_data_type=3,
        )
        payload = price_option_probe(
            contract=contract,
            market=market,
            total_qty=22,
            action="SELL",
            probe_qty=1,
            steps=(6, 4, 2, 0),
        )

        self.assertEqual(payload["contract"]["symbol"], "EWY")
        self.assertEqual(payload["total_quantity"], 22)
        self.assertEqual(payload["held_back_quantity"], 18)
        self.assertEqual(payload["spot_at_pricing"], 127.45)
        self.assertEqual(payload["market"]["ask"], 29.8)
        self.assertEqual(sum(t["quantity"] for t in payload["trades"]), 4)

    def test_zero_bid_ask_market_uses_real_ask_as_probe_anchor(self) -> None:
        contract = OptionContractSpec(symbol="EWY", expiry="20260313", strike=152, right="C")
        market = OptionMarketSnapshot(
            spot=133.89,
            bid=0.0,
            ask=0.60,
            last=0.40,
            implied_volatility=0.55,
            risk_free_rate=0.03593,
            dividend_yield=0.0,
            source="yfinance",
        )
        payload = price_option_probe(
            contract=contract,
            market=market,
            total_qty=108,
            action="SELL",
            probe_qty=1,
            steps=(2, 1, 0),
        )

        self.assertEqual(payload["anchor_price"], 0.60)
        self.assertEqual([t["lmtPrice"] for t in payload["trades"]], [0.7, 0.65, 0.6])

    def test_probe_trades_accept_generic_contract_dict(self) -> None:
        payload = build_probe_trades(
            contract={
                "symbol": "EWY",
                "secType": "STK",
                "exchange": "SMART",
                "currency": "USD",
            },
            action="SELL",
            total_qty=10,
            anchor_price=127.50,
            probe_qty=1,
            steps=(2, 0),
        )

        self.assertEqual(payload["contract"]["secType"], "STK")
        self.assertEqual(payload["held_back_quantity"], 8)
        self.assertEqual([t["lmtPrice"] for t in payload["trades"]], [127.6, 127.5])


class QuoteAvailabilityGuardTests(unittest.TestCase):
    def test_probe_requires_ibkr_iv_or_manual_override(self) -> None:
        quote = SimpleNamespace(iv=0.0)

        with self.assertRaises(ValueError):
            _require_implied_volatility(
                quote=quote,
                symbol="EWY",
                expiry="20280121",
                strike=220.0,
                right="C",
                iv_override=None,
            )

    def test_probe_accepts_manual_iv_override_when_ibkr_iv_missing(self) -> None:
        quote = SimpleNamespace(iv=0.0)

        self.assertEqual(
            _require_implied_volatility(
                quote=quote,
                symbol="EWY",
                expiry="20280121",
                strike=220.0,
                right="C",
                iv_override=0.42,
            ),
            0.42,
        )


class _DummyConnection:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


class ProbePreflightTests(unittest.TestCase):
    @patch("stock_tooling.price_probe.connect", return_value=_DummyConnection())
    @patch("stock_tooling.price_probe.load_smart_chain_or_raise")
    @patch("stock_tooling.price_probe.inspect_contract_market_data")
    def test_price_probe_fails_cleanly_when_two_sided_quote_missing(self, inspect_health, load_chain, _connect) -> None:
        load_chain.return_value = SimpleNamespace(
            expirations=("20280121",),
            strikes=(220.0,),
        )
        inspect_health.return_value = QuoteHealth(
            symbol="EWY",
            sec_type="OPT",
            expiry="20280121",
            strike=220.0,
            right="C",
            exchange="SMART",
            market_data_type=3,
            qualified=True,
            bid=0.0,
            ask=0.0,
            last=0.0,
            close=0.0,
            market_price=0.0,
            mid=0.0,
            spot=0.0,
            iv=0.0,
            delta=0.0,
            gamma=0.0,
            theta=0.0,
            vega=0.0,
            has_spot=False,
            has_two_sided_quote=False,
            has_greeks=False,
            status="unavailable",
            reason="empty_quote_and_greeks",
            contract_summary="EWY 20280121 220.0C SMART",
        )

        with self.assertRaises(ProbePricingError):
            price_probe(
                symbol="EWY",
                expiry="20280121",
                strike=220.0,
                right="C",
                qty=1,
                debug=False,
            )


if __name__ == "__main__":
    unittest.main()
