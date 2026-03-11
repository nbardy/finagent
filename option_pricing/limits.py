from __future__ import annotations

import math
from dataclasses import dataclass

from .black_scholes import option_price


TICK_SIZE = 0.05


def round_up_to_tick(value: float, tick: float = TICK_SIZE) -> float:
    return round(math.ceil(value / tick) * tick, 2)


def split_quantity(total_qty: int, n_tranches: int) -> list[int]:
    if total_qty <= 0:
        return []
    tranche_count = max(1, n_tranches)
    base = total_qty // tranche_count
    remainder = total_qty % tranche_count
    return [base + (1 if idx < remainder else 0) for idx in range(tranche_count)]


@dataclass(frozen=True)
class LimitPriceResult:
    theoretical_value: float
    mid_price: float
    bid: float
    ask: float
    suggested_limit: float
    edge_vs_mid: float
    spread: float
    spread_pct: float

    def __str__(self) -> str:
        return (
            f"TV=${self.theoretical_value:.2f}  Mid=${self.mid_price:.2f}  "
            f"Edge=${self.edge_vs_mid:+.2f}  "
            f"Limit=${self.suggested_limit:.2f}  "
            f"Spread={self.spread_pct*100:.1f}%  "
            f"[{self.bid:.2f} x {self.ask:.2f}]"
        )


def recommend_limit(
    theoretical_value: float,
    bid: float,
    ask: float,
    action: str = "BUY",
    tick: float = TICK_SIZE,
) -> LimitPriceResult:
    mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else max(bid, ask, 0.0)
    spread = ask - bid if bid > 0 and ask > 0 else 0.0
    spread_pct = spread / mid if mid > 0 else float("inf")
    edge = mid - theoretical_value

    if action.upper() == "BUY":
        raw = min(theoretical_value, mid) if mid > 0 else theoretical_value
        suggested = round_up_to_tick(raw, tick)
        if bid > 0:
            suggested = max(suggested, round(bid, 2))
    else:
        raw = max(theoretical_value, mid) if mid > 0 else theoretical_value
        suggested = round_up_to_tick(raw, tick)
        if ask > 0:
            suggested = min(suggested, round(ask, 2))
        suggested = max(suggested, round_up_to_tick(theoretical_value, tick))

    return LimitPriceResult(
        theoretical_value=round(theoretical_value, 4),
        mid_price=round(mid, 4),
        bid=round(bid, 4),
        ask=round(ask, 4),
        suggested_limit=round(suggested, 2),
        edge_vs_mid=round(edge, 4),
        spread=round(spread, 4),
        spread_pct=round(spread_pct, 4),
    )


def limit_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    bid: float,
    ask: float,
    action: str = "BUY",
    tick: float = TICK_SIZE,
    right: str = "C",
    dividend_yield: float = 0.0,
) -> LimitPriceResult:
    theoretical_value = option_price(
        spot=S,
        strike=K,
        time_to_expiry=T,
        risk_free_rate=r,
        volatility=sigma,
        right=right,
        dividend_yield=dividend_yield,
    )
    return recommend_limit(theoretical_value, bid, ask, action=action, tick=tick)


def limit_price_put(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    bid: float,
    ask: float,
    action: str = "BUY",
    tick: float = TICK_SIZE,
    dividend_yield: float = 0.0,
) -> LimitPriceResult:
    return limit_price(
        S=S,
        K=K,
        T=T,
        r=r,
        sigma=sigma,
        bid=bid,
        ask=ask,
        action=action,
        tick=tick,
        right="P",
        dividend_yield=dividend_yield,
    )


def build_exit_tranches(
    suggested_limit: float,
    theoretical_value: float,
    bid: float,
    ask: float,
    total_qty: int,
    n_tranches: int,
    tick: float = TICK_SIZE,
) -> list[dict]:
    quantities = split_quantity(total_qty, n_tranches)
    floor = max(round_up_to_tick(theoretical_value, tick), round(bid, 2) if bid > 0 else 0.0)
    anchor = max(round_up_to_tick(suggested_limit, tick), floor)
    start = max(round_up_to_tick(ask, tick), anchor) if ask > 0 else anchor

    tranches = []
    current_price = start
    for idx, quantity in enumerate(quantities, start=1):
        price = max(round(current_price, 2), floor)
        tranches.append({
            "tranche": idx,
            "quantity": quantity,
            "lmtPrice": price,
        })
        if current_price > anchor:
            current_price = max(current_price - tick, anchor)
        else:
            current_price = max(current_price - tick, floor)
    return tranches


def model_tranches(
    tv: float,
    total_qty: int,
    n_tranches: int = 5,
    tick: float = TICK_SIZE,
    spread_pct: float = 0.05,
    action: str = "SELL",
) -> list[dict]:
    """
    Build tranches purely from theoretical value — no market quotes needed.

    Spreads tranches across a band around TV:
      SELL: from TV + spread_pct*TV (optimistic) down to TV (floor)
      BUY:  from TV - spread_pct*TV (optimistic) up to TV (ceiling)

    spread_pct: how wide to spread tranches around TV (default 5%).
      On illiquid LEAPs use 0.08-0.10. On liquid options use 0.02-0.03.

    Weights: small qty at edges (lottery fills), bulk at TV (fair value).
    """
    half_spread = tv * spread_pct
    weights = [0.10, 0.15, 0.35, 0.25, 0.15]
    # Adjust weights list to match n_tranches
    if n_tranches != 5:
        weights = [1.0 / n_tranches] * n_tranches

    qtys = [max(1, round(total_qty * w)) for w in weights]
    qtys[len(qtys) // 2] += total_qty - sum(qtys)  # fix rounding on bulk tranche

    if action.upper() == "SELL":
        top = tv + half_spread
        bottom = tv
    else:
        top = tv
        bottom = tv - half_spread

    n = max(n_tranches - 1, 1)
    tranches = []
    for i, qty in enumerate(qtys):
        raw_price = top - (top - bottom) * (i / n)
        price = round(round(raw_price / tick) * tick, 2)
        price = max(price, tick)  # never zero
        tranches.append({
            "tranche": i + 1,
            "quantity": qty,
            "lmtPrice": price,
        })

    return tranches


def tranche_ladder(
    tv: float,
    bid: float,
    ask: float,
    total_qty: int,
    action: str = "BUY",
    n_tranches: int = 3,
    tick: float = TICK_SIZE,
) -> list[dict]:
    mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else max(bid, ask, 0.0)
    if action.upper() == "SELL":
        executor_tranches = build_exit_tranches(
            suggested_limit=max(tv, mid),
            theoretical_value=tv,
            bid=bid,
            ask=ask,
            total_qty=total_qty,
            n_tranches=n_tranches,
            tick=tick,
        )
        return [
            {
                "tranche": tranche["tranche"],
                "quantity": tranche["quantity"],
                "limit_price": tranche["lmtPrice"],
            }
            for tranche in executor_tranches
        ]

    start = round_up_to_tick(min(tv, mid) if mid > 0 else tv, tick)
    if bid > 0:
        start = max(start, bid)

    quantities = split_quantity(total_qty, n_tranches)
    tranches = []
    current_price = start
    for idx, quantity in enumerate(quantities, start=1):
        tranches.append({
            "tranche": idx,
            "quantity": quantity,
            "limit_price": round(max(current_price, 0.05), 2),
        })
        current_price = max(current_price - tick, 0.05)
    return tranches
