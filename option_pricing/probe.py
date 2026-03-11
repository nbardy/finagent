from __future__ import annotations

from datetime import datetime

from .black_scholes import option_price
from .limits import TICK_SIZE, recommend_limit
from .models import OptionContractSpec, OptionMarketSnapshot, dte_and_time_to_expiry


DEFAULT_SELL_PROBE_STEPS = (6, 4, 2, 0)
DEFAULT_BUY_PROBE_STEPS = (0, 2, 4, 6)


def _as_executor_contract(contract: OptionContractSpec | dict) -> dict:
    if isinstance(contract, dict):
        return dict(contract)
    return contract.as_executor_contract()


def build_probe_trades(
    contract: OptionContractSpec | dict,
    action: str,
    total_qty: int,
    anchor_price: float,
    probe_qty: int = 1,
    steps: tuple[int, ...] | None = None,
    tick: float = TICK_SIZE,
    tif: str = "DAY",
) -> dict:
    """
    Build small discovery orders around an anchor price while holding back the
    rest of the position.

    For SELL probes, prices are placed at anchor + step*tick, descending toward
    the anchor. For BUY probes, prices are placed at anchor - step*tick,
    ascending toward the anchor.
    """
    if total_qty <= 0:
        raise ValueError("total_qty must be positive")
    if probe_qty <= 0:
        raise ValueError("probe_qty must be positive")

    normalized_action = action.upper()
    default_steps = DEFAULT_SELL_PROBE_STEPS if normalized_action == "SELL" else DEFAULT_BUY_PROBE_STEPS
    steps = steps or default_steps
    if not steps:
        raise ValueError("steps must not be empty")

    required_qty = probe_qty * len(steps)
    if required_qty > total_qty:
        raise ValueError(
            f"probe ladder requires {required_qty} contracts but only {total_qty} available"
        )

    prices = []
    for idx, step in enumerate(steps, start=1):
        raw_price = anchor_price + step * tick if normalized_action == "SELL" else anchor_price - step * tick
        price = round(max(raw_price, tick), 2)
        prices.append({
            "probe": idx,
            "quantity": probe_qty,
            "lmtPrice": price,
            "ticks_from_anchor": step,
            "offset": round(abs(price - anchor_price), 2),
        })

    if normalized_action == "SELL":
        prices.sort(key=lambda probe: probe["lmtPrice"], reverse=True)
    else:
        prices.sort(key=lambda probe: probe["lmtPrice"])

    held_back_qty = total_qty - required_qty
    executor_contract = _as_executor_contract(contract)
    trades = [
        {
            "action": normalized_action,
            "contract": executor_contract,
            "order_type": "LMT",
            "quantity": probe["quantity"],
            "lmtPrice": probe["lmtPrice"],
            "tif": tif,
            "probe": {
                "level": probe["probe"],
                "ticks_from_anchor": probe["ticks_from_anchor"],
                "offset": probe["offset"],
            },
        }
        for probe in prices
    ]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "action": normalized_action,
        "contract": executor_contract,
        "anchor_price": round(anchor_price, 2),
        "probe_qty": probe_qty,
        "probe_count": len(prices),
        "total_quantity": total_qty,
        "held_back_quantity": held_back_qty,
        "tif": tif,
        "probes": prices,
        "trades": trades,
    }


def price_option_probe(
    contract: OptionContractSpec,
    market: OptionMarketSnapshot,
    total_qty: int,
    action: str = "SELL",
    probe_qty: int = 1,
    steps: tuple[int, ...] | None = None,
    tick: float = TICK_SIZE,
    tif: str = "DAY",
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

    if market.has_market:
        bid = market.bid
        ask = market.ask
        market_note = market.source or "market"
    else:
        spread_estimate = max(theoretical_value * 0.05, 0.10)
        bid = max(theoretical_value - spread_estimate / 2.0, 0.05)
        ask = bid + spread_estimate
        market_note = f"{market.source or 'model'}-synthetic"

    limit = recommend_limit(theoretical_value, bid=bid, ask=ask, action=action, tick=tick)
    normalized_action = action.upper()
    anchor_price = ask if normalized_action == "SELL" else bid
    if anchor_price <= 0:
        anchor_price = limit.suggested_limit

    payload = build_probe_trades(
        contract=contract,
        action=normalized_action,
        total_qty=total_qty,
        anchor_price=anchor_price,
        probe_qty=probe_qty,
        steps=steps,
        tick=tick,
        tif=tif,
    )
    payload.update({
        "quote_source": market.source,
        "quote_warning": market.quote_warning,
        "spot_at_pricing": round(market.spot, 4),
        "market": {
            "bid": round(bid, 4),
            "ask": round(ask, 4),
            "mid": round((bid + ask) / 2.0, 4),
            "last_price": round(market.last, 4),
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
        },
        "quote_status": {
            "market_data_type": market.market_data_type,
            "is_delayed": market.is_delayed,
            "quote_time": market.quote_time,
            "model_underlying_price": market.model_underlying_price,
            "pv_dividend": market.pv_dividend,
        },
    })
    return payload
