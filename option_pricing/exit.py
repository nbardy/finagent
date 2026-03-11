from __future__ import annotations

from datetime import datetime

from .black_scholes import bs_gamma, option_delta, option_price
from .limits import build_exit_tranches, recommend_limit, tranche_ladder
from .models import OptionContractSpec, OptionMarketSnapshot, dte_and_time_to_expiry


def price_option_exit(
    contract: OptionContractSpec,
    market: OptionMarketSnapshot,
    total_qty: int,
    action: str = "SELL",
    n_tranches: int = 5,
) -> dict:
    dte, time_to_expiry = dte_and_time_to_expiry(contract.expiry)
    volatility = market.implied_volatility if market.implied_volatility > 0 else 0.25
    right = contract.right.upper()

    theoretical_value = option_price(
        spot=market.spot,
        strike=contract.strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=market.risk_free_rate,
        volatility=volatility,
        right=right,
        dividend_yield=market.dividend_yield,
    )
    delta = option_delta(
        spot=market.spot,
        strike=contract.strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=market.risk_free_rate,
        volatility=volatility,
        right=right,
        dividend_yield=market.dividend_yield,
    )
    gamma = bs_gamma(
        spot=market.spot,
        strike=contract.strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=market.risk_free_rate,
        volatility=volatility,
        dividend_yield=market.dividend_yield,
    )

    if market.has_market:
        bid = market.bid
        ask = market.ask
        market_note = market.source or "market"
    else:
        spread_estimate = max(theoretical_value * 0.05, 0.10)
        bid = max(theoretical_value - spread_estimate / 2.0, 0.05)
        ask = bid + spread_estimate
        market_note = f"{market.source or 'model'}-synthetic"

    limit = recommend_limit(theoretical_value, bid=bid, ask=ask, action=action)
    if action.upper() == "SELL":
        tranches = build_exit_tranches(
            suggested_limit=limit.suggested_limit,
            theoretical_value=theoretical_value,
            bid=bid,
            ask=ask,
            total_qty=total_qty,
            n_tranches=n_tranches,
        )
    else:
        tranches = [
            {
                "tranche": tranche["tranche"],
                "quantity": tranche["quantity"],
                "lmtPrice": tranche["limit_price"],
            }
            for tranche in tranche_ladder(
                tv=theoretical_value,
                bid=bid,
                ask=ask,
                total_qty=total_qty,
                action=action,
                n_tranches=n_tranches,
            )
        ]

    return {
        "quote_source": market.source,
        "quote_warning": market.quote_warning,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "action": action.upper(),
        "contract": contract.as_executor_contract(),
        "order_type": "LMT",
        "total_quantity": total_qty,
        "spot_at_pricing": round(market.spot, 4),
        "market": {
            "bid": round(bid, 4),
            "ask": round(ask, 4),
            "mid": round((bid + ask) / 2.0, 4),
            "last_price": round(market.last, 4),
            "volume": market.volume,
            "open_interest": market.open_interest,
            "source_note": market_note,
        },
        "metrics": {
            "pricing_model": "Black-Scholes-Merton",
            "dte": dte,
            "time_to_expiry_years": round(time_to_expiry, 6),
            "risk_free_rate": round(market.risk_free_rate, 6),
            "dividend_yield": round(market.dividend_yield, 6),
            "implied_volatility": round(volatility, 6),
            "theoretical_value": round(theoretical_value, 4),
            "suggested_limit": limit.suggested_limit,
            "edge_vs_mid": limit.edge_vs_mid,
            "spread_pct": limit.spread_pct,
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
        },
        "quote_status": {
            "market_data_type": market.market_data_type,
            "is_delayed": market.is_delayed,
            "quote_time": market.quote_time,
            "model_underlying_price": market.model_underlying_price,
            "pv_dividend": market.pv_dividend,
        },
        "tranches": tranches,
    }
