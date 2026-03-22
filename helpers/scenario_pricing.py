from __future__ import annotations

from dataclasses import dataclass

from stratoforge.pricing.black_scholes import option_price


@dataclass(frozen=True)
class ScenarioOptionLine:
    right: str
    strike: float
    dte: int
    qty: int
    iv: float


def _intrinsic_value(spot: float, strike: float, right: str) -> float:
    if right.upper() == "C":
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def _linear_path_value(start: float, end: float, step_days: int, total_days: int) -> float:
    if total_days <= 0:
        return end
    fraction = min(max(step_days / total_days, 0.0), 1.0)
    return start + ((end - start) * fraction)


def option_value_under_linear_path(
    *,
    spot_now: float,
    scenario_spot: float,
    scenario_days: int,
    strike: float,
    right: str,
    dte: int,
    iv: float,
    vol_shift: float,
    risk_free_rate: float,
    min_sigma: float = 0.05,
) -> float:
    if dte <= 0:
        return _intrinsic_value(spot_now, strike, right)

    if scenario_days <= dte:
        remaining_years = max((dte - scenario_days) / 365.0, 1 / 365.0)
        sigma = max(min_sigma, iv + vol_shift)
        return option_price(
            spot=scenario_spot,
            strike=strike,
            time_to_expiry=remaining_years,
            risk_free_rate=risk_free_rate,
            volatility=sigma,
            right=right,
        )

    expiry_spot = _linear_path_value(
        start=spot_now,
        end=scenario_spot,
        step_days=dte,
        total_days=max(scenario_days, 1),
    )
    return _intrinsic_value(expiry_spot, strike, right)


def option_lines_future_value(
    *,
    lines: list[ScenarioOptionLine] | tuple[ScenarioOptionLine, ...],
    spot_now: float,
    scenario_spot: float,
    scenario_days: int,
    vol_shift: float,
    risk_free_rate: float,
    min_sigma: float = 0.05,
) -> float:
    total = 0.0
    for line in lines:
        total += option_value_under_linear_path(
            spot_now=spot_now,
            scenario_spot=scenario_spot,
            scenario_days=scenario_days,
            strike=line.strike,
            right=line.right,
            dte=line.dte,
            iv=line.iv,
            vol_shift=vol_shift,
            risk_free_rate=risk_free_rate,
            min_sigma=min_sigma,
        ) * 100.0 * line.qty
    return total
