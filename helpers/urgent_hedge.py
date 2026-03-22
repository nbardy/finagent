from __future__ import annotations

import json
import math
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from option_pricing.black_scholes import option_price
from option_pricing.limits import TICK_SIZE, split_quantity
from option_pricing.models import display_expiry, normalize_expiry
from option_pricing.probe import build_probe_trades
from option_pricing.yahoo import fetch_spot
from helpers.scenario_pricing import ScenarioOptionLine, option_lines_future_value, option_value_under_linear_path
from helpers.urgent_hedge_types import (
    ChasePolicy,
    ComboLegSpec,
    ComboQuoteSnapshot,
    HedgeCandidate,
    HedgeExecutionPlan,
    HedgeStructureSpec,
    LegQuoteSnapshot,
    MacroScenario,
    MacroScenarioSet,
    MarketSessionState,
    PortfolioBook,
    PortfolioOptionLine,
    ProbePolicy,
    ScenarioOutcome,
)


US_EASTERN = ZoneInfo("America/New_York")


def _round_price(value: float, tick: float = TICK_SIZE) -> float:
    return round(max(math.ceil(value / tick) * tick, tick), 2)


def _as_of_dt(as_of: str | None = None) -> datetime:
    if as_of:
        parsed = datetime.fromisoformat(as_of)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=US_EASTERN)
        return parsed.astimezone(US_EASTERN)
    return datetime.now(US_EASTERN)


def _infer_symbol(payload: dict[str, Any]) -> str:
    if payload.get("symbol"):
        return str(payload["symbol"]).upper()
    positions = payload.get("book", {}).get("positions", [])
    if positions:
        label = str(positions[0].get("label", "")).strip()
        if label:
            return label.split()[0].upper()
    raise ValueError("Unable to infer symbol from payload; provide `symbol`.")


def validate_probabilities(data: MacroScenarioSet) -> None:
    if not data.scenarios:
        raise ValueError("Macro scenario set must contain at least one scenario.")
    total_probability = sum(scenario.probability for scenario in data.scenarios)
    if total_probability <= 0:
        raise ValueError("Scenario probabilities must sum to a positive number.")
    for scenario in data.scenarios:
        if scenario.probability < 0:
            raise ValueError(f"Scenario {scenario.label!r} has negative probability.")


def normalize_probabilities(data: MacroScenarioSet) -> MacroScenarioSet:
    validate_probabilities(data)
    total_probability = sum(scenario.probability for scenario in data.scenarios)
    if math.isclose(total_probability, 1.0, abs_tol=1e-6):
        return data
    normalized = tuple(
        replace(scenario, probability=scenario.probability / total_probability)
        for scenario in data.scenarios
    )
    return replace(data, scenarios=normalized)


def macro_scenario_set_from_dict(payload: dict[str, Any], path_label: str = "macro") -> MacroScenarioSet:
    if "scenarios" not in payload:
        raise ValueError("Macro payload must include `scenarios`.")

    if "spot" in payload:
        reference_spot = float(payload["spot"])
        scenarios = tuple(
            MacroScenario(
                label=str(raw["label"]),
                horizon_days=int(raw.get("horizon_days", raw.get("days", 0))),
                spot_move_pct=float(raw["spot_move_pct"]) if "spot_move_pct" in raw else (float(raw["spot"]) / reference_spot) - 1.0,
                vol_shift=float(raw.get("vol_shift", 0.0)),
                probability=float(raw["probability"]),
                notes=str(raw.get("notes", "")),
            )
            for raw in payload["scenarios"]
        )
        data = MacroScenarioSet(
            name=str(payload.get("name", path_label)),
            symbol=_infer_symbol(payload),
            as_of=str(payload.get("as_of", datetime.now(US_EASTERN).isoformat(timespec="seconds"))),
            thesis=str(payload.get("thesis", "")),
            reference_spot=reference_spot,
            risk_free_rate=float(payload.get("risk_free_rate", 0.045)),
            scenarios=scenarios,
        )
        return normalize_probabilities(data)

    reference_spot = payload.get("reference_spot")
    scenarios = tuple(
        MacroScenario(
            label=str(raw["label"]),
            horizon_days=int(raw["horizon_days"]),
            spot_move_pct=float(raw["spot_move_pct"]),
            vol_shift=float(raw.get("vol_shift", 0.0)),
            probability=float(raw["probability"]),
            notes=str(raw.get("notes", "")),
        )
        for raw in payload["scenarios"]
    )
    data = MacroScenarioSet(
        name=str(payload.get("name", path_label)),
        symbol=str(payload["symbol"]).upper(),
        as_of=str(payload.get("as_of", datetime.now(US_EASTERN).isoformat(timespec="seconds"))),
        thesis=str(payload.get("thesis", "")),
        reference_spot=float(reference_spot) if reference_spot is not None else None,
        risk_free_rate=float(payload.get("risk_free_rate", 0.045)),
        scenarios=scenarios,
    )
    return normalize_probabilities(data)


def load_macro_scenarios(path: str) -> MacroScenarioSet:
    with open(path) as handle:
        payload = json.load(handle)
    return macro_scenario_set_from_dict(payload, path_label=Path(path).stem)


def portfolio_book_from_dict(payload: dict[str, Any], default_symbol: str | None = None) -> PortfolioBook:
    if "book" in payload:
        book_payload = payload["book"]
        spot = float(payload["spot"])
        risk_free_rate = float(payload.get("risk_free_rate", 0.045))
        symbol = default_symbol or _infer_symbol(payload)
    else:
        book_payload = payload
        spot = float(book_payload["spot"])
        risk_free_rate = float(book_payload.get("risk_free_rate", 0.045))
        symbol = default_symbol or str(book_payload.get("symbol", "")).upper()
        if not symbol:
            raise ValueError("Portfolio book payload requires `symbol`.")

    positions: list[PortfolioOptionLine] = []
    for raw in book_payload.get("positions", []):
        dte = int(raw["dte"])
        iv = raw.get("iv")
        if iv is None:
            raise ValueError(
                f"Missing IV for portfolio position {raw.get('label', raw)}; "
                "urgent_hedge inputs now require explicit IV."
            )
        positions.append(PortfolioOptionLine(
            label=str(raw["label"]),
            right=str(raw["right"]).upper(),
            strike=float(raw["strike"]),
            dte=dte,
            qty=int(raw["qty"]),
            mark=float(raw["mark"]),
            iv=float(iv),
        ))

    return PortfolioBook(
        symbol=symbol,
        spot=spot,
        risk_free_rate=risk_free_rate,
        positions=tuple(positions),
    )


def load_portfolio_book(path: str, default_symbol: str | None = None) -> PortfolioBook:
    with open(path) as handle:
        payload = json.load(handle)
    return portfolio_book_from_dict(payload, default_symbol=default_symbol)


def _future_value(
    lines: tuple[PortfolioOptionLine, ...],
    *,
    spot_now: float,
    scenario_spot: float,
    days: int,
    vol_shift: float,
    risk_free_rate: float,
) -> float:
    scenario_lines = [
        ScenarioOptionLine(
            right=line.right,
            strike=line.strike,
            dte=line.dte,
            qty=line.qty,
            iv=line.iv,
        )
        for line in lines
    ]
    return option_lines_future_value(
        lines=scenario_lines,
        spot_now=spot_now,
        scenario_spot=scenario_spot,
        scenario_days=days,
        vol_shift=vol_shift,
        risk_free_rate=risk_free_rate,
    )


def portfolio_current_value(book: PortfolioBook) -> float:
    return sum(line.mark * 100.0 * line.qty for line in book.positions)


def portfolio_book_pnl(book: PortfolioBook, spot: float, days: int, vol_shift: float) -> float:
    future_value = _future_value(
        book.positions,
        spot_now=book.spot,
        scenario_spot=spot,
        days=days,
        vol_shift=vol_shift,
        risk_free_rate=book.risk_free_rate,
    )
    return future_value - portfolio_current_value(book)


def get_us_equity_option_session_state(
    now: datetime | None = None,
    close_buffer_minutes: int = 15,
) -> MarketSessionState:
    current = now.astimezone(US_EASTERN) if now else datetime.now(US_EASTERN)
    weekday = current.weekday()
    market_open = current.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = current.replace(hour=16, minute=0, second=0, microsecond=0)

    is_trading_day = weekday < 5
    is_open = is_trading_day and market_open <= current < market_close
    minutes_to_close = None
    if is_open:
        minutes_to_close = max(int((market_close - current).total_seconds() // 60), 0)

    if is_open and minutes_to_close is not None and minutes_to_close > close_buffer_minutes:
        mode = "regular"
    elif is_open:
        mode = "near_close"
    else:
        mode = "closed"

    next_open = market_open
    if current >= market_close or weekday >= 5:
        next_open = market_open
        while next_open <= current or next_open.weekday() >= 5:
            next_open = (next_open + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)

    return MarketSessionState(
        as_of=current.isoformat(timespec="seconds"),
        market_tz="America/New_York",
        mode=mode,
        is_trading_day=is_trading_day,
        is_open=is_open,
        minutes_to_close=minutes_to_close,
        next_open=next_open.isoformat(timespec="seconds"),
    )


def _choose_expiry(expiries: list[str], min_days: int, as_of: datetime) -> str:
    viable: list[tuple[int, str]] = []
    for expiry in expiries:
        expiry_dt = datetime.strptime(normalize_expiry(expiry), "%Y%m%d").replace(tzinfo=US_EASTERN)
        dte = (expiry_dt.date() - as_of.date()).days
        if dte >= min_days:
            viable.append((dte, normalize_expiry(expiry)))
    if not viable:
        raise RuntimeError(f"No option expiry available beyond {min_days} DTE.")
    viable.sort()
    return viable[0][1]


def select_default_expiries(expiries: list[str], as_of: datetime | None = None) -> dict[str, str]:
    current = as_of or datetime.now(US_EASTERN)
    normalized = sorted({normalize_expiry(expiry) for expiry in expiries})
    return {
        "crash": _choose_expiry(normalized, min_days=7, as_of=current),
        "swing": _choose_expiry(normalized, min_days=14, as_of=current),
        "core": _choose_expiry(normalized, min_days=30, as_of=current),
    }


def _target_strike(spot: float, multiplier: float) -> float:
    return round(spot * multiplier)


def default_ewy_hedge_universe(spot: float, expiries: dict[str, str]) -> list[HedgeStructureSpec]:
    crash = expiries["crash"]
    swing = expiries["swing"]
    core = expiries["core"]
    return [
        HedgeStructureSpec(
            name=f"{crash} crash 102/91 put spread",
            expiry=crash,
            structure="put_spread",
            long_strike=_target_strike(spot, 1.02),
            short_strike=_target_strike(spot, 0.91),
            notes="Short-dated wide crash spread.",
        ),
        HedgeStructureSpec(
            name=f"{crash} crash 100/90 put spread",
            expiry=crash,
            structure="put_spread",
            long_strike=_target_strike(spot, 1.00),
            short_strike=_target_strike(spot, 0.90),
            notes="Short-dated symmetric crash spread.",
        ),
        HedgeStructureSpec(
            name=f"{swing} swing 102/94 put spread",
            expiry=swing,
            structure="put_spread",
            long_strike=_target_strike(spot, 1.02),
            short_strike=_target_strike(spot, 0.94),
            notes="Two-week orderly drawdown hedge.",
        ),
        HedgeStructureSpec(
            name=f"{swing} swing ATM put",
            expiry=swing,
            structure="put",
            long_strike=_target_strike(spot, 1.00),
            notes="Short dated convex hedge.",
        ),
        HedgeStructureSpec(
            name=f"{core} core 102/94 put spread",
            expiry=core,
            structure="put_spread",
            long_strike=_target_strike(spot, 1.02),
            short_strike=_target_strike(spot, 0.94),
            notes="Lower-bleed monthly core hedge.",
        ),
        HedgeStructureSpec(
            name=f"{core} core ATM put",
            expiry=core,
            structure="put",
            long_strike=_target_strike(spot, 1.00),
            notes="Monthly convex hedge.",
        ),
    ]


def _nearest_row(frame: pd.DataFrame, target_strike: float) -> pd.Series:
    valid = frame.copy()
    valid = valid[valid["strike"].notna()]
    valid = valid[valid["bid"].notna() & valid["ask"].notna()]
    valid = valid[(valid["bid"] > 0) & (valid["ask"] > 0)]
    if valid.empty:
        raise RuntimeError("No options with usable bid/ask quotes were returned.")
    return valid.iloc[(valid["strike"] - target_strike).abs().argsort().iloc[0]]


def _chain_rows_for_spec(frame: pd.DataFrame, spec: HedgeStructureSpec) -> tuple[pd.Series, pd.Series | None]:
    long_row = _nearest_row(frame, spec.long_strike)
    if spec.structure == "put":
        return long_row, None

    lower = frame.copy()
    lower = lower[lower["strike"] < float(long_row["strike"])]
    if lower.empty:
        raise RuntimeError(f"No lower strike available below {float(long_row['strike']):.2f} for {spec.name}.")
    target_short = spec.short_strike if spec.short_strike is not None else float(long_row["strike"]) * 0.92
    short_row = _nearest_row(lower, target_short)
    return long_row, short_row


def _leg_quote_from_row(row: pd.Series, expiry: str, right: str) -> LegQuoteSnapshot:
    bid = float(row["bid"])
    ask = float(row["ask"])
    last = float(row["lastPrice"]) if not pd.isna(row.get("lastPrice")) else 0.0
    mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else max(last, ask, bid)
    iv = float(row["impliedVolatility"]) if not pd.isna(row.get("impliedVolatility")) and float(row["impliedVolatility"]) > 0 else 0.25
    return LegQuoteSnapshot(
        strike=float(row["strike"]),
        right=right,
        expiry=expiry,
        bid=bid,
        ask=ask,
        mid=mid,
        iv=iv,
        last=last,
        volume=int(row["volume"]) if not pd.isna(row.get("volume")) else None,
        open_interest=int(row["openInterest"]) if not pd.isna(row.get("openInterest")) else None,
    )


def _resolve_structure(spec: HedgeStructureSpec, frame: pd.DataFrame) -> tuple[HedgeStructureSpec, tuple[LegQuoteSnapshot, ...], tuple[ComboLegSpec, ...]]:
    long_row, short_row = _chain_rows_for_spec(frame, spec)
    expiry = spec.expiry
    long_quote = _leg_quote_from_row(long_row, expiry=expiry, right="P")
    if spec.structure == "put":
        resolved = replace(spec, long_strike=long_quote.strike, short_strike=None)
        legs = (ComboLegSpec(action="BUY", strike=long_quote.strike, right="P", expiry=expiry),)
        return resolved, (long_quote,), legs

    assert short_row is not None
    short_quote = _leg_quote_from_row(short_row, expiry=expiry, right="P")
    resolved = replace(spec, long_strike=long_quote.strike, short_strike=short_quote.strike)
    legs = (
        ComboLegSpec(action="BUY", strike=long_quote.strike, right="P", expiry=expiry),
        ComboLegSpec(action="SELL", strike=short_quote.strike, right="P", expiry=expiry),
    )
    return resolved, (long_quote, short_quote), legs


def quote_structure(symbol: str, spec: HedgeStructureSpec, spot: float, frame: pd.DataFrame) -> tuple[HedgeStructureSpec, ComboQuoteSnapshot, float]:
    resolved_spec, leg_quotes, legs = _resolve_structure(spec, frame)
    if resolved_spec.structure == "put":
        combo_bid = leg_quotes[0].bid
        combo_ask = leg_quotes[0].ask
        max_value = resolved_spec.long_strike
    else:
        combo_bid = max(leg_quotes[0].bid - leg_quotes[1].ask, TICK_SIZE)
        combo_ask = max(leg_quotes[0].ask - leg_quotes[1].bid, combo_bid)
        max_value = resolved_spec.long_strike - float(resolved_spec.short_strike or 0.0)
    combo_mid = (combo_bid + combo_ask) / 2.0
    combo = ComboQuoteSnapshot(
        symbol=symbol,
        spot=spot,
        legs=legs,
        leg_quotes=leg_quotes,
        combo_bid=round(combo_bid, 4),
        combo_ask=round(combo_ask, 4),
        combo_mid=round(combo_mid, 4),
        source="yfinance",
    )
    return resolved_spec, combo, max_value


def _days_to_expiry(expiry: str, as_of: datetime) -> int:
    expiry_dt = datetime.strptime(normalize_expiry(expiry), "%Y%m%d").replace(tzinfo=US_EASTERN)
    return max((expiry_dt.date() - as_of.date()).days, 0)


def _hedge_future_value_per_unit(
    combo: ComboQuoteSnapshot,
    structure: str,
    scenario_spot: float,
    horizon_days: int,
    vol_shift: float,
    risk_free_rate: float,
    as_of: datetime,
) -> float:
    total = 0.0
    for leg, quote in zip(combo.legs, combo.leg_quotes, strict=True):
        dte = _days_to_expiry(quote.expiry, as_of=as_of)
        price = option_value_under_linear_path(
            spot_now=combo.spot,
            scenario_spot=scenario_spot,
            scenario_days=horizon_days,
            strike=quote.strike,
            right=quote.right,
            dte=dte,
            iv=quote.iv,
            vol_shift=vol_shift,
            risk_free_rate=risk_free_rate,
        )
        sign = 1.0 if leg.action == "BUY" else -1.0
        total += price * sign
    return total


def _carry_loss_pct(entry_debit: float, outcomes: tuple[ScenarioOutcome, ...]) -> float:
    bleed = sum(abs(outcome.hedge_pnl) * outcome.probability for outcome in outcomes if outcome.hedge_pnl < 0)
    if entry_debit <= 0:
        return 0.0
    return round((bleed / entry_debit) * 100.0, 1)


def _candidate_score(
    conditional_downside_coverage_pct: float,
    expected_pnl: float,
    carry_loss_pct: float,
    expected_combined_pnl: float | None,
) -> float:
    score = conditional_downside_coverage_pct * 0.6
    score += (expected_pnl / 1000.0) * 0.25
    score -= carry_loss_pct * 0.15
    if expected_combined_pnl is not None:
        score += expected_combined_pnl / 10000.0
    return round(score, 4)


def evaluate_candidate(
    spec: HedgeStructureSpec,
    combo: ComboQuoteSnapshot,
    max_value: float,
    scenario_set: MacroScenarioSet,
    budget: float,
    book: PortfolioBook | None = None,
) -> HedgeCandidate:
    worst_case_unit_debit = combo.combo_ask + (2 * TICK_SIZE)
    quantity_from_budget = int(budget // (worst_case_unit_debit * 100.0))
    if spec.quantity_hint > 0:
        quantity = min(spec.quantity_hint, quantity_from_budget) if quantity_from_budget > 0 else spec.quantity_hint
    else:
        quantity = quantity_from_budget
    if quantity <= 0:
        raise RuntimeError(f"Budget ${budget:,.0f} is too small for {spec.name} at ${combo.combo_ask:.2f}.")

    entry_debit = round(combo.combo_ask * quantity * 100.0, 2)
    scenario_outcomes: list[ScenarioOutcome] = []
    expected_pnl = 0.0
    expected_combined_pnl = 0.0 if book is not None else None
    downside_probability = 0.0
    weighted_downside_coverage = 0.0
    as_of = _as_of_dt(scenario_set.as_of)

    for scenario in scenario_set.scenarios:
        scenario_spot = combo.spot * (1.0 + scenario.spot_move_pct)
        per_unit_future = _hedge_future_value_per_unit(
            combo=combo,
            structure=spec.structure,
            scenario_spot=scenario_spot,
            horizon_days=scenario.horizon_days,
            vol_shift=scenario.vol_shift,
            risk_free_rate=scenario_set.risk_free_rate,
            as_of=as_of,
        )
        hedge_pnl = round((per_unit_future * quantity * 100.0) - entry_debit, 2)
        book_pnl = None
        combined_pnl = None
        coverage_pct = 0.0
        if book is not None:
            book_pnl = round(portfolio_book_pnl(book, scenario_spot, scenario.horizon_days, scenario.vol_shift), 2)
            combined_pnl = round(book_pnl + hedge_pnl, 2)
            if book_pnl < 0 and hedge_pnl > 0:
                coverage_pct = round((hedge_pnl / abs(book_pnl)) * 100.0, 1)
                weighted_downside_coverage += (coverage_pct / 100.0) * scenario.probability
            if book_pnl < 0:
                downside_probability += scenario.probability

        expected_pnl += hedge_pnl * scenario.probability
        if expected_combined_pnl is not None and combined_pnl is not None:
            expected_combined_pnl += combined_pnl * scenario.probability
        scenario_outcomes.append(ScenarioOutcome(
            label=scenario.label,
            probability=scenario.probability,
            hedge_pnl=hedge_pnl,
            book_pnl=book_pnl,
            combined_pnl=combined_pnl,
            coverage_pct=coverage_pct,
        ))

    conditional_downside_coverage_pct = 0.0
    if downside_probability > 0:
        conditional_downside_coverage_pct = round((weighted_downside_coverage / downside_probability) * 100.0, 1)
    carry_loss_pct = _carry_loss_pct(entry_debit=entry_debit, outcomes=tuple(scenario_outcomes))
    score = _candidate_score(
        conditional_downside_coverage_pct=conditional_downside_coverage_pct,
        expected_pnl=expected_pnl,
        carry_loss_pct=carry_loss_pct,
        expected_combined_pnl=expected_combined_pnl,
    )
    return HedgeCandidate(
        spec=spec,
        combo=combo,
        target_quantity=quantity,
        entry_debit=entry_debit,
        max_value=round(max_value * quantity * 100.0, 2),
        scenario_outcomes=tuple(scenario_outcomes),
        expected_pnl=round(expected_pnl, 2),
        expected_combined_pnl=round(expected_combined_pnl, 2) if expected_combined_pnl is not None else None,
        conditional_downside_coverage_pct=conditional_downside_coverage_pct,
        downside_probability_pct=round(downside_probability * 100.0, 1),
        carry_loss_pct=carry_loss_pct,
        score=score,
    )


def rank_candidates(candidates: list[HedgeCandidate]) -> list[HedgeCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.conditional_downside_coverage_pct,
            candidate.expected_combined_pnl if candidate.expected_combined_pnl is not None else candidate.expected_pnl,
            -candidate.entry_debit,
            candidate.score,
        ),
        reverse=True,
    )


def get_yahoo_expiries(symbol: str) -> list[str]:
    ticker = yf.Ticker(symbol)
    return [normalize_expiry(expiry) for expiry in ticker.options]


def get_option_chain_frame(symbol: str, expiry: str, right: str = "P") -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    chain = ticker.option_chain(display_expiry(expiry))
    frame = chain.puts if right.upper() == "P" else chain.calls
    return frame.copy()


def build_candidate_universe(
    symbol: str,
    scenario_set: MacroScenarioSet,
    budget: float,
    book: PortfolioBook | None = None,
) -> list[HedgeCandidate]:
    ticker = yf.Ticker(symbol)
    spot = scenario_set.reference_spot or fetch_spot(ticker)
    expiries = select_default_expiries(get_yahoo_expiries(symbol), as_of=_as_of_dt(scenario_set.as_of))
    specs = default_ewy_hedge_universe(spot=spot, expiries=expiries)
    by_expiry: dict[str, pd.DataFrame] = {}
    for spec in specs:
        if spec.expiry not in by_expiry:
            by_expiry[spec.expiry] = get_option_chain_frame(symbol, spec.expiry, right="P")

    candidates: list[HedgeCandidate] = []
    for spec in specs:
        try:
            resolved_spec, combo, max_value = quote_structure(
                symbol=symbol,
                spec=spec,
                spot=spot,
                frame=by_expiry[spec.expiry],
            )
            candidate = evaluate_candidate(
                spec=resolved_spec,
                combo=combo,
                max_value=max_value,
                scenario_set=scenario_set,
                budget=budget,
                book=book,
            )
            candidates.append(candidate)
        except Exception:
            continue
    return rank_candidates(candidates)


def _executor_contract(candidate: HedgeCandidate) -> dict[str, Any]:
    if candidate.spec.structure == "put":
        leg = candidate.combo.legs[0]
        return {
            "symbol": candidate.combo.symbol,
            "secType": "OPT",
            "exchange": "SMART",
            "currency": "USD",
            "lastTradeDateOrContractMonth": leg.expiry,
            "strike": leg.strike,
            "right": leg.right,
        }
    return {
        "secType": "BAG",
        "symbol": candidate.combo.symbol,
        "exchange": "SMART",
        "currency": "USD",
        "legs": [
            {
                "action": leg.action,
                "strike": leg.strike,
                "right": leg.right,
                "expiry": leg.expiry,
                "ratio": leg.ratio,
            }
            for leg in candidate.combo.legs
        ],
    }


def _probe_steps(total_qty: int, probe_qty: int, steps: tuple[int, ...]) -> tuple[int, ...]:
    if total_qty <= probe_qty:
        return (0,)
    max_levels = max(total_qty // max(probe_qty, 1), 1)
    return tuple(steps[:max_levels]) or (0,)


def _buy_ladder(
    quantity: int,
    bid: float,
    ask: float,
    tif: str,
    aggressive: bool,
    note_prefix: str,
    max_price: float | None = None,
    tick: float = TICK_SIZE,
) -> list[dict[str, Any]]:
    if quantity <= 0:
        return []
    tranche_qtys = split_quantity(quantity, 3)
    spread = max(ask - bid, tick)
    if aggressive:
        raw_prices = (
            ask + tick,
            ask + (2 * tick),
            ask + (3 * tick),
        )
    else:
        raw_prices = (
            max(bid, ask - spread * 0.5),
            max(bid, ask - spread * 0.25),
            ask,
        )
    prices = []
    for raw_price in raw_prices:
        rounded = _round_price(raw_price, tick)
        if max_price is not None:
            rounded = min(rounded, _round_price(max_price, tick))
        prices.append(rounded)
    return [
        {
            "tranche": index + 1,
            "quantity": tranche_qtys[index],
            "lmtPrice": prices[index],
            "note": f"{note_prefix} {index + 1}",
            "tif": tif,
        }
        for index in range(len(tranche_qtys))
    ]


def build_order_artifact(
    candidate: HedgeCandidate,
    description: str,
    notes: str,
    tif: str,
    tranches: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "description": description,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "notes": notes,
        "trades": [
            {
                "contract": _executor_contract(candidate),
                "action": "BUY",
                "tif": tif,
                "tranches": tranches,
            }
        ],
        "pricing": {
            "spot_reference": round(candidate.combo.spot, 4),
            "combo_bid": round(candidate.combo.combo_bid, 4),
            "combo_ask": round(candidate.combo.combo_ask, 4),
            "combo_mid": round(candidate.combo.combo_mid, 4),
            "target_quantity": candidate.target_quantity,
            "entry_debit_estimate": round(sum(tranche["quantity"] * tranche["lmtPrice"] * 100.0 for tranche in tranches), 2),
            "max_value_at_expiry": candidate.max_value,
            "expected_pnl": candidate.expected_pnl,
            "conditional_downside_coverage_pct": candidate.conditional_downside_coverage_pct,
        },
    }


def build_execution_bundle(
    candidate: HedgeCandidate,
    scenario_set: MacroScenarioSet,
    budget: float,
    output_prefix: str,
    output_dir: str | Path = ".",
    probe_policy: ProbePolicy | None = None,
    chase_policy: ChasePolicy | None = None,
    session: MarketSessionState | None = None,
) -> tuple[HedgeExecutionPlan, dict[str, dict[str, Any]]]:
    session = session or get_us_equity_option_session_state()
    probe_policy = probe_policy or ProbePolicy(
        probe_qty=min(5, max(1, candidate.target_quantity // 10 or 1)),
        max_wait_seconds=25,
        poll_interval_seconds=5,
        escalation_ticks=(2, 1, 0),
    )
    chase_policy = chase_policy or ChasePolicy(
        max_rounds=3,
        tick_up_per_round=TICK_SIZE,
        max_unit_debit=round(candidate.combo.combo_ask + (3 * TICK_SIZE), 2),
    )

    contract = _executor_contract(candidate)
    active_probe_steps = _probe_steps(candidate.target_quantity, probe_policy.probe_qty, probe_policy.escalation_ticks)
    probe_payload = build_probe_trades(
        contract=contract,
        action="BUY",
        total_qty=candidate.target_quantity,
        anchor_price=max(candidate.combo.combo_ask, TICK_SIZE),
        probe_qty=min(probe_policy.probe_qty, candidate.target_quantity),
        steps=active_probe_steps,
        tif="DAY" if session.mode == "regular" else "GTC",
    )
    probe_tranches = [
        {
            "tranche": index + 1,
            "quantity": trade["quantity"],
            "lmtPrice": trade["lmtPrice"],
            "note": f"Probe {index + 1}",
        }
        for index, trade in enumerate(probe_payload["trades"])
    ]
    remaining_qty = probe_payload["held_back_quantity"]
    full_tranches = _buy_ladder(
        quantity=remaining_qty,
        bid=candidate.combo.combo_bid,
        ask=candidate.combo.combo_ask,
        tif="DAY",
        aggressive=False,
        note_prefix="Full ladder",
    )
    open_ready_tranches = _buy_ladder(
        quantity=candidate.target_quantity,
        bid=candidate.combo.combo_bid,
        ask=max(candidate.combo.combo_ask, chase_policy.max_unit_debit - (2 * TICK_SIZE)),
        tif="GTC",
        aggressive=True,
        note_prefix="Open-ready",
        max_price=chase_policy.max_unit_debit,
    )

    probe_artifact = build_order_artifact(
        candidate=candidate,
        description=f"{candidate.combo.symbol} urgent hedge probe - {candidate.spec.name}",
        notes="Fast price-discovery probe for the selected urgent hedge.",
        tif="DAY" if session.mode == "regular" else "GTC",
        tranches=probe_tranches,
    )
    full_artifact = build_order_artifact(
        candidate=candidate,
        description=f"{candidate.combo.symbol} urgent hedge full - {candidate.spec.name}",
        notes="Remaining quantity after the probe. Use during the live session.",
        tif="DAY",
        tranches=full_tranches,
    )
    open_ready_artifact = build_order_artifact(
        candidate=candidate,
        description=f"{candidate.combo.symbol} urgent hedge open-ready - {candidate.spec.name}",
        notes="Aggressive GTC ladder for the next regular options session.",
        tif="GTC",
        tranches=open_ready_tranches,
    )

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    probe_file = str(output_root / f"{output_prefix}_probe.json")
    full_file = str(output_root / f"{output_prefix}_full.json")
    open_ready_file = str(output_root / f"{output_prefix}_open_ready.json")
    plan = HedgeExecutionPlan(
        symbol=candidate.combo.symbol,
        thesis=scenario_set.thesis,
        candidate_name=candidate.spec.name,
        target_quantity=candidate.target_quantity,
        budget=budget,
        recommended_artifact="probe" if session.mode == "regular" else "open_ready",
        combo=candidate.combo,
        probe_policy=probe_policy,
        chase_policy=chase_policy,
        session=session,
        probe_file=probe_file,
        full_file=full_file,
        open_ready_file=open_ready_file,
    )
    return plan, {
        "probe": probe_artifact,
        "full": full_artifact,
        "open_ready": open_ready_artifact,
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2)


def write_execution_bundle(
    plan: HedgeExecutionPlan,
    artifacts: dict[str, dict[str, Any]],
    ranked_candidates: list[HedgeCandidate],
    output_prefix: str,
    output_dir: str | Path = ".",
) -> dict[str, str]:
    output_root = Path(output_dir)
    ranked_file = output_root / f"{output_prefix}_ranked.json"
    selected_file = output_root / f"{output_prefix}_selected_plan.json"

    for key, path in (("probe", plan.probe_file), ("full", plan.full_file), ("open_ready", plan.open_ready_file)):
        write_json(path, artifacts[key])

    ranked_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "candidates": [asdict(candidate) for candidate in ranked_candidates],
    }
    write_json(ranked_file, ranked_payload)
    selected_payload = asdict(plan)
    selected_payload["top_candidates"] = [
        {
            "name": candidate.spec.name,
            "entry_debit": candidate.entry_debit,
            "target_quantity": candidate.target_quantity,
            "expected_pnl": candidate.expected_pnl,
            "expected_combined_pnl": candidate.expected_combined_pnl,
            "conditional_downside_coverage_pct": candidate.conditional_downside_coverage_pct,
            "carry_loss_pct": candidate.carry_loss_pct,
            "score": candidate.score,
        }
        for candidate in ranked_candidates[:5]
    ]
    write_json(selected_file, selected_payload)
    return {
        "ranked": str(ranked_file),
        "selected": str(selected_file),
        "probe": plan.probe_file,
        "full": plan.full_file,
        "open_ready": plan.open_ready_file,
    }


def scenario_set_to_legacy_ev_payload(
    scenario_set: MacroScenarioSet,
    book: PortfolioBook,
    hedges: list[HedgeCandidate] | None = None,
) -> dict[str, Any]:
    payload = {
        "spot": book.spot,
        "risk_free_rate": book.risk_free_rate,
        "book": {
            "positions": [asdict(position) for position in book.positions],
        },
        "scenarios": [
            {
                "label": scenario.label,
                "days": scenario.horizon_days,
                "spot": round(book.spot * (1.0 + scenario.spot_move_pct), 4),
                "vol_shift": scenario.vol_shift,
                "probability": scenario.probability,
            }
            for scenario in scenario_set.scenarios
        ],
        "hedges": [],
    }
    for candidate in hedges or []:
        legs = []
        for leg, quote in zip(candidate.combo.legs, candidate.combo.leg_quotes, strict=True):
            sign = 1 if leg.action == "BUY" else -1
            legs.append({
                "label": f"{leg.action} {quote.strike:.1f}{quote.right}",
                "right": quote.right,
                "strike": quote.strike,
                "dte": max(_days_to_expiry(quote.expiry, _as_of_dt(scenario_set.as_of)), 1),
                "qty": sign * candidate.target_quantity,
                "mark": quote.mid,
                "iv": quote.iv,
            })
        payload["hedges"].append({
            "name": candidate.spec.name,
            "entry_cost": candidate.entry_debit,
            "legs": legs,
        })
    return payload
