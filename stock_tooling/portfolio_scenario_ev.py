"""
Portfolio scenario EV analyzer.

Models a current options book plus optional hedge candidates under a set of
user-defined macro scenarios with probabilities.

Usage:
    uv run python portfolio_scenario_ev.py --input ewy_2w_ev_input.json
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibkr import connect, get_option_quotes, get_portfolio, get_spot
from helpers.urgent_hedge import load_macro_scenarios
from helpers.scenario_pricing import ScenarioOptionLine, option_lines_future_value
@dataclass(frozen=True)
class Scenario:
    label: str
    days: int
    spot: float
    vol_shift: float
    probability: float


@dataclass(frozen=True)
class OptionLine:
    label: str
    right: str
    strike: float
    dte: int
    qty: int
    mark: float
    iv: float


MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def _load_option_lines(raw_lines: list[dict], spot: float, r: float) -> list[OptionLine]:
    lines: list[OptionLine] = []
    for raw in raw_lines:
        iv = raw.get("iv")
        if iv is None:
            raise ValueError(
                f"Missing IV for option line {raw.get('label', raw)}; "
                "portfolio_scenario_ev now requires explicit IV."
            )
        lines.append(OptionLine(
            label=str(raw["label"]),
            right=str(raw["right"]),
            strike=float(raw["strike"]),
            dte=int(raw["dte"]),
            qty=int(raw["qty"]),
            mark=float(raw["mark"]),
            iv=float(iv),
        ))
    return lines


def _as_of_date(config: dict[str, Any]) -> date:
    macro = config.get("macro") or {}
    raw = macro.get("as_of")
    if raw:
        return datetime.strptime(str(raw), "%Y-%m-%d").date()
    return date.today()


def _infer_symbol_from_text(text: str) -> str | None:
    match = re.match(r"^\s*([A-Z]{1,6})\b", text or "")
    return match.group(1).upper() if match else None


def _infer_expiry_from_text(text: str, *, default_year: int) -> str | None:
    if not text:
        return None
    direct = re.search(r"\b(20\d{6})\b", text)
    if direct:
        return direct.group(1)
    month_day = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*[- ]?(\d{1,2})\b", text, re.IGNORECASE)
    if not month_day:
        return None
    month = MONTHS[month_day.group(1).upper()]
    day = int(month_day.group(2))
    return f"{default_year:04d}{month:02d}{day:02d}"


def _dte_from_expiry(expiry: str, *, as_of: date) -> int:
    expiry_dt = datetime.strptime(expiry, "%Y%m%d").date()
    return max((expiry_dt - as_of).days, 0)


def _normalize_line_metadata(
    raw: dict[str, Any],
    *,
    default_symbol: str | None,
    fallback_expiry_text: str | None,
    as_of: date,
) -> dict[str, Any]:
    line = copy.deepcopy(raw)
    label = str(line.get("label", ""))
    symbol = line.get("symbol") or default_symbol or _infer_symbol_from_text(label)
    if symbol:
        line["symbol"] = str(symbol).upper()
    expiry = line.get("expiry")
    if not expiry:
        expiry = _infer_expiry_from_text(label, default_year=as_of.year)
    if not expiry and fallback_expiry_text:
        expiry = _infer_expiry_from_text(fallback_expiry_text, default_year=as_of.year)
    if expiry:
        line["expiry"] = str(expiry)
        line["dte"] = _dte_from_expiry(str(expiry), as_of=as_of)
    return line


def _analysis_symbol(config: dict[str, Any], explicit_symbol: str | None = None) -> str:
    if explicit_symbol:
        return explicit_symbol.upper()
    for candidate in (
        config.get("symbol"),
        (config.get("book") or {}).get("symbol"),
        (config.get("macro") or {}).get("symbol"),
    ):
        if candidate:
            return str(candidate).upper()
    for position in (config.get("book") or {}).get("positions", []):
        symbol = position.get("symbol") or _infer_symbol_from_text(str(position.get("label", "")))
        if symbol:
            return str(symbol).upper()
    for hedge in config.get("hedges", []):
        for leg in hedge.get("legs", []):
            symbol = leg.get("symbol") or _infer_symbol_from_text(str(leg.get("label", "")))
            if symbol:
                return str(symbol).upper()
    raise ValueError("Unable to infer analysis symbol. Provide --symbol or include symbol in the input.")


def _normalize_refreshable_config(config: dict[str, Any], *, symbol: str) -> dict[str, Any]:
    payload = copy.deepcopy(config)
    payload["symbol"] = symbol.upper()
    payload.setdefault("book", {})
    payload["book"]["symbol"] = symbol.upper()
    as_of = _as_of_date(payload)
    payload["book"]["positions"] = [
        _normalize_line_metadata(raw, default_symbol=symbol, fallback_expiry_text=None, as_of=as_of)
        for raw in payload["book"].get("positions", [])
    ]
    for hedge in payload.get("hedges", []):
        hedge_name = str(hedge.get("name", ""))
        hedge["legs"] = [
            _normalize_line_metadata(raw, default_symbol=symbol, fallback_expiry_text=hedge_name, as_of=as_of)
            for raw in hedge.get("legs", [])
        ]
    return payload


def _rescale_scenarios_to_spot(payload: dict[str, Any], *, old_spot: float, new_spot: float) -> None:
    if old_spot <= 0:
        return
    for scenario in payload.get("scenarios", []):
        base_scenario_spot = float(scenario["spot"])
        move_ratio = base_scenario_spot / old_spot
        scenario["spot"] = round(new_spot * move_ratio, 4)


def _require_quote_mark(quote, *, symbol: str, expiry: str, strike: float, right: str) -> float:
    if getattr(quote, "has_market", False):
        return float(quote.mid)
    if getattr(quote, "last", 0.0) > 0:
        return float(quote.last)
    raise ValueError(
        f"Missing quote mark for {symbol} {expiry} {strike:.1f}{right}; "
        "refresh is strict and will not keep stale marks."
    )


def _require_quote_iv(quote, *, symbol: str, expiry: str, strike: float, right: str) -> float:
    iv = float(getattr(quote, "iv", 0.0) or 0.0)
    if iv > 0:
        return iv
    raise ValueError(
        f"Missing quote IV for {symbol} {expiry} {strike:.1f}{right}; "
        "refresh is strict and will not keep stale IVs."
    )


def _signed_entry_cost(legs: list[dict[str, Any]]) -> float:
    return round(sum(float(leg["mark"]) * 100.0 * int(leg["qty"]) for leg in legs), 2)


def _refresh_client_id() -> int:
    return 1800 + (os.getpid() % 7000)


def refresh_market_snapshot(
    config: dict[str, Any],
    *,
    symbol: str | None = None,
    mode: str = "overlay",
    market_data_type: int = 3,
    debug: bool = False,
    fallback_to_disk: bool = False,
) -> dict[str, Any]:
    payload = _normalize_refreshable_config(config, symbol=_analysis_symbol(config, explicit_symbol=symbol))
    old_spot = float(payload["spot"])
    result = copy.deepcopy(payload)
    result["market_refresh"] = {
        "attempted": True,
        "succeeded": False,
        "fallback_to_disk": False,
        "source": "ibkr",
        "market_data_type": market_data_type,
        "old_spot": old_spot,
    }

    try:
        with connect(client_id=_refresh_client_id(), market_data_type=market_data_type, debug=debug) as ib:
            live_spot = float(get_spot(ib, payload["symbol"], debug=debug))
            result["spot"] = live_spot
            result["book"]["symbol"] = payload["symbol"]

            if mode != "pure-hedge":
                live_positions = get_portfolio(ib, symbols=[payload["symbol"]])
                live_option_positions = []
                for position in live_positions:
                    if position.sec_type != "OPT":
                        continue
                    live_option_positions.append({
                        "label": f"{position.symbol} {position.strike:.1f}{position.right} {position.expiry}",
                        "symbol": position.symbol,
                        "right": position.right,
                        "strike": float(position.strike),
                        "expiry": position.expiry,
                        "dte": int(position.dte or 0),
                        "qty": int(position.qty),
                        "mark": float(position.market_price),
                    })
                if live_option_positions:
                    result["book"]["positions"] = live_option_positions

            specs_by_symbol: dict[str, list[tuple[float, str, str]]] = {}
            book_lookup: dict[tuple[str, float, str, str], dict[str, Any]] = {}
            for position in result["book"].get("positions", []):
                if "symbol" not in position or "expiry" not in position:
                    continue
                key = (str(position["symbol"]).upper(), float(position["strike"]), str(position["expiry"]), str(position["right"]).upper())
                book_lookup[key] = position
                specs_by_symbol.setdefault(key[0], []).append((key[1], key[2], key[3]))

            hedge_lookups: dict[str, dict[tuple[str, float, str, str], dict[str, Any]]] = {}
            for hedge in result.get("hedges", []):
                hedge_lookup: dict[tuple[str, float, str, str], dict[str, Any]] = {}
                for leg in hedge.get("legs", []):
                    if "symbol" not in leg or "expiry" not in leg:
                        continue
                    key = (str(leg["symbol"]).upper(), float(leg["strike"]), str(leg["expiry"]), str(leg["right"]).upper())
                    hedge_lookup[key] = leg
                    specs_by_symbol.setdefault(key[0], []).append((key[1], key[2], key[3]))
                hedge_lookups[str(hedge["name"])] = hedge_lookup

            for symbol_key, raw_specs in specs_by_symbol.items():
                unique_specs = list(dict.fromkeys(raw_specs))
                quotes = get_option_quotes(ib, symbol_key, unique_specs, debug=debug)
                quote_map = {
                    (symbol_key, float(quote.strike), str(quote.expiry), str(quote.right).upper()): quote
                    for quote in quotes
                }
                for key, line in book_lookup.items():
                    if key[0] != symbol_key:
                        continue
                    if key not in quote_map:
                        raise ValueError(
                            f"Missing refreshed quote for {key[0]} {key[2]} {key[1]:.1f}{key[3]}"
                        )
                    quote = quote_map[key]
                    line["mark"] = _require_quote_mark(
                        quote,
                        symbol=key[0],
                        expiry=key[2],
                        strike=key[1],
                        right=key[3],
                    )
                    line["iv"] = _require_quote_iv(
                        quote,
                        symbol=key[0],
                        expiry=key[2],
                        strike=key[1],
                        right=key[3],
                    )
                for hedge in result.get("hedges", []):
                    hedge_lookup = hedge_lookups[str(hedge["name"])]
                    for key, line in hedge_lookup.items():
                        if key[0] != symbol_key:
                            continue
                        if key not in quote_map:
                            raise ValueError(
                                f"Missing refreshed quote for {key[0]} {key[2]} {key[1]:.1f}{key[3]}"
                            )
                        quote = quote_map[key]
                        line["mark"] = _require_quote_mark(
                            quote,
                            symbol=key[0],
                            expiry=key[2],
                            strike=key[1],
                            right=key[3],
                        )
                        line["iv"] = _require_quote_iv(
                            quote,
                            symbol=key[0],
                            expiry=key[2],
                            strike=key[1],
                            right=key[3],
                        )
                    hedge["entry_cost"] = _signed_entry_cost(hedge["legs"])

            _rescale_scenarios_to_spot(result, old_spot=old_spot, new_spot=live_spot)
            result["market_refresh"].update({
                "succeeded": True,
                "fallback_to_disk": False,
                "refreshed_spot": live_spot,
            })
            return result
    except Exception as exc:
        if not fallback_to_disk:
            raise
        result["market_refresh"].update({
            "succeeded": False,
            "fallback_to_disk": True,
            "error": f"{type(exc).__name__}: {exc}",
        })
        return result


def apply_macro_scenario_set(config: dict[str, Any], macro_path: str) -> dict[str, Any]:
    macro = load_macro_scenarios(macro_path)
    payload = copy.deepcopy(config)
    if macro.reference_spot is not None and payload.get("spot") is None:
        payload["spot"] = float(macro.reference_spot)
    payload["risk_free_rate"] = float(macro.risk_free_rate)
    base_spot = float(payload["spot"])
    payload["scenarios"] = [
        {
            "label": scenario.label,
            "days": scenario.horizon_days,
            "spot": round(base_spot * (1.0 + scenario.spot_move_pct), 4),
            "vol_shift": scenario.vol_shift,
            "probability": scenario.probability,
        }
        for scenario in macro.scenarios
    ]
    payload["macro"] = {
        "name": macro.name,
        "symbol": macro.symbol,
        "as_of": macro.as_of,
        "thesis": macro.thesis,
    }
    return payload


def pure_hedge_config(config: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(config)
    payload.setdefault("book", {})
    payload["book"]["positions"] = []
    return payload


def _future_value(lines: list[OptionLine], spot: float, days: int, vol_shift: float, r: float) -> float:
    raise NotImplementedError("Use _future_value_from_spot_now with an explicit starting spot.")


def _future_value_from_spot_now(
    lines: list[OptionLine],
    *,
    spot_now: float,
    scenario_spot: float,
    days: int,
    vol_shift: float,
    r: float,
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
        risk_free_rate=r,
        min_sigma=0.15,
    )


def analyze(config: dict) -> dict:
    spot = float(config["spot"])
    r = float(config.get("risk_free_rate", 0.045))
    scenarios = [Scenario(**raw) for raw in config["scenarios"]]

    total_prob = sum(s.probability for s in scenarios)
    if abs(total_prob - 1.0) > 0.01:
        scenarios = [
            Scenario(s.label, s.days, s.spot, s.vol_shift, s.probability / total_prob)
            for s in scenarios
        ]

    book_lines = _load_option_lines(config["book"]["positions"], spot, r)
    current_book_value = sum(line.mark * 100 * line.qty for line in book_lines)

    candidates = []
    for raw in config.get("hedges", []):
        legs = _load_option_lines(raw["legs"], spot, r)
        entry_cost = float(raw["entry_cost"])
        candidates.append({
            "name": raw["name"],
            "entry_cost": entry_cost,
            "legs": legs,
        })

    scenario_rows = []
    candidate_summaries = {
        "No hedge": {
            "expected_book_pnl": 0.0,
            "expected_combined_pnl": 0.0,
            "expected_hedge_pnl": 0.0,
            "weighted_downside_coverage": 0.0,
            "downside_probability": 0.0,
            "downside_book_pnl_weighted": 0.0,
            "downside_combined_pnl_weighted": 0.0,
        }
    }
    for candidate in candidates:
        candidate_summaries[candidate["name"]] = {
            "expected_book_pnl": 0.0,
            "expected_combined_pnl": 0.0,
            "expected_hedge_pnl": 0.0,
            "weighted_downside_coverage": 0.0,
            "downside_probability": 0.0,
            "downside_book_pnl_weighted": 0.0,
            "downside_combined_pnl_weighted": 0.0,
        }

    for scenario in scenarios:
        book_future = _future_value_from_spot_now(
            book_lines,
            spot_now=spot,
            scenario_spot=scenario.spot,
            days=scenario.days,
            vol_shift=scenario.vol_shift,
            r=r,
        )
        book_pnl = book_future - current_book_value

        row = {
            "label": scenario.label,
            "probability": scenario.probability,
            "days": scenario.days,
            "spot": scenario.spot,
            "vol_shift": scenario.vol_shift,
            "book": {
                "pnl": round(book_pnl, 2),
            },
            "book_pnl": round(book_pnl, 2),
            "hedges": {},
        }

        candidate_summaries["No hedge"]["expected_book_pnl"] += book_pnl * scenario.probability
        candidate_summaries["No hedge"]["expected_combined_pnl"] += book_pnl * scenario.probability
        if book_pnl < 0:
            candidate_summaries["No hedge"]["downside_probability"] += scenario.probability
            candidate_summaries["No hedge"]["downside_book_pnl_weighted"] += book_pnl * scenario.probability
            candidate_summaries["No hedge"]["downside_combined_pnl_weighted"] += book_pnl * scenario.probability

        for candidate in candidates:
            hedge_future = _future_value_from_spot_now(
                candidate["legs"],
                spot_now=spot,
                scenario_spot=scenario.spot,
                days=scenario.days,
                vol_shift=scenario.vol_shift,
                r=r,
            )
            hedge_pnl = hedge_future - candidate["entry_cost"]
            combined_pnl = book_pnl + hedge_pnl
            coverage = 0.0
            if book_pnl < 0 and hedge_pnl > 0:
                coverage = hedge_pnl / abs(book_pnl)

            row["hedges"][candidate["name"]] = {
                "book": {
                    "pnl": round(book_pnl, 2),
                },
                "overlay": {
                    "pnl": round(hedge_pnl, 2),
                },
                "combined": {
                    "pnl": round(combined_pnl, 2),
                },
                "overlay_pnl": round(hedge_pnl, 2),
                "hedge_pnl": round(hedge_pnl, 2),
                "combined_pnl": round(combined_pnl, 2),
                "coverage_pct": round(coverage * 100, 1),
            }

            summary = candidate_summaries[candidate["name"]]
            summary["expected_book_pnl"] += book_pnl * scenario.probability
            summary["expected_hedge_pnl"] += hedge_pnl * scenario.probability
            summary["expected_combined_pnl"] += combined_pnl * scenario.probability
            if book_pnl < 0:
                summary["downside_probability"] += scenario.probability
                summary["weighted_downside_coverage"] += coverage * scenario.probability
                summary["downside_book_pnl_weighted"] += book_pnl * scenario.probability
                summary["downside_combined_pnl_weighted"] += combined_pnl * scenario.probability

        scenario_rows.append(row)

    summaries = {}
    for name, values in candidate_summaries.items():
        downside_probability = values["downside_probability"]
        conditional_downside_coverage = 0.0
        avg_book_pnl_when_downside = 0.0
        avg_combined_pnl_when_downside = 0.0
        if downside_probability > 0:
            conditional_downside_coverage = values["weighted_downside_coverage"] / downside_probability
            avg_book_pnl_when_downside = values["downside_book_pnl_weighted"] / downside_probability
            avg_combined_pnl_when_downside = values["downside_combined_pnl_weighted"] / downside_probability

        summaries[name] = {
            "book": {
                "expected_pnl": round(values["expected_book_pnl"], 2),
                "avg_pnl_when_downside": round(avg_book_pnl_when_downside, 2),
            },
            "overlay": {
                "expected_pnl": round(values["expected_hedge_pnl"], 2),
            },
            "combined": {
                "expected_pnl": round(values["expected_combined_pnl"], 2),
                "avg_pnl_when_downside": round(avg_combined_pnl_when_downside, 2),
            },
            "expected_book_pnl": round(values["expected_book_pnl"], 2),
            "expected_overlay_pnl": round(values["expected_hedge_pnl"], 2),
            "expected_hedge_pnl": round(values["expected_hedge_pnl"], 2),
            "expected_combined_pnl": round(values["expected_combined_pnl"], 2),
            "weighted_downside_coverage_pct": round(values["weighted_downside_coverage"] * 100, 1),
            "conditional_downside_coverage_pct": round(conditional_downside_coverage * 100, 1),
            "downside_probability_pct": round(downside_probability * 100, 1),
            "avg_book_pnl_when_downside": round(avg_book_pnl_when_downside, 2),
            "avg_combined_pnl_when_downside": round(avg_combined_pnl_when_downside, 2),
        }

    output = {
        "schema_version": "2.0",
        "analysis_type": config.get("analysis_type", "portfolio_overlay_ev"),
        "macro": config.get("macro"),
        "market_refresh": config.get("market_refresh"),
        "spot": spot,
        "risk_free_rate": r,
        "current_book_value": round(current_book_value, 2),
        "scenarios": scenario_rows,
        "summaries": summaries,
    }

    return output


def run_cli(default_mode: str = "overlay") -> None:
    parser = argparse.ArgumentParser(description="Portfolio scenario EV analyzer")
    parser.add_argument("--input", default="portfolio_scenario_input.json", help="Input config JSON")
    parser.add_argument("--output", default="portfolio_scenario_ev.json", help="Output JSON path")
    parser.add_argument("--macro", default=None, help="Macro thesis JSON in urgent-hedge scenario format")
    parser.add_argument("--symbol", default=None, help="Underlying symbol override for live refresh")
    parser.add_argument("--market-data-type", type=int, default=3, help="1=live, 3=delayed, 4=delayed-frozen")
    parser.add_argument(
        "--refresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Refresh book/legs/spot from IBKR before analysis; falls back to disk unless --strict-refresh is set.",
    )
    parser.add_argument(
        "--strict-refresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail instead of falling back to disk when IBKR refresh is unavailable.",
    )
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Print detailed IBKR diagnostics during refresh.",
    )
    parser.add_argument(
        "--mode",
        choices=("overlay", "pure-hedge"),
        default=default_mode,
        help="overlay = current book plus overlay candidates, pure-hedge = ignore book and score hedges alone",
    )
    parser.add_argument(
        "--print-scenarios",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Print scenario-level book / overlay / combined PnL after writing the JSON output.",
    )
    args = parser.parse_args()

    with open(args.input) as f:
        config = json.load(f)

    symbol_override = args.symbol
    if args.macro:
        macro = load_macro_scenarios(args.macro)
        symbol_override = symbol_override or macro.symbol
    if args.refresh:
        symbol_override = _analysis_symbol(config, explicit_symbol=symbol_override)

    if args.mode == "pure-hedge":
        config = pure_hedge_config(config)
    if args.refresh:
        config = refresh_market_snapshot(
            config,
            symbol=symbol_override,
            mode=args.mode,
            market_data_type=args.market_data_type,
            debug=args.debug,
            fallback_to_disk=not bool(args.strict_refresh),
        )
    if args.macro:
        config = apply_macro_scenario_set(config, args.macro)
    if args.mode == "pure-hedge":
        config["analysis_type"] = "pure_hedge_ev"
    else:
        config["analysis_type"] = "portfolio_overlay_ev"

    output = analyze(config)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(output, f, indent=2)

    print(f"Saved to {args.output}")
    for name, summary in output["summaries"].items():
        print(
            f"{name:>24}  "
            f"EV book={summary['book']['expected_pnl']:>+10.0f}  "
            f"EV overlay={summary['overlay']['expected_pnl']:>+10.0f}  "
            f"EV combined={summary['expected_combined_pnl']:>+10.0f}  "
            f"cover={summary['weighted_downside_coverage_pct']:>5.1f}%  "
            f"cond_cover={summary['conditional_downside_coverage_pct']:>5.1f}%  "
            f"downP={summary['downside_probability_pct']:>5.1f}%"
        )

    if args.print_scenarios:
        print("\nScenario rows:")
        for row in output["scenarios"]:
            label = row["label"]
            probability = row["probability"]
            print(f"\n[{label}] prob={probability:.2%} spot={row['spot']:.2f} days={row['days']} vol_shift={row['vol_shift']:+.2f}")
            print(
                f"  {'No hedge':>24}  "
                f"book={row['book']['pnl']:>+10.2f}  "
                f"overlay={0.0:>+10.2f}  "
                f"combined={row['book']['pnl']:>+10.2f}"
            )
            for name, values in row["hedges"].items():
                print(
                    f"  {name:>24}  "
                    f"book={values['book']['pnl']:>+10.2f}  "
                    f"overlay={values['overlay']['pnl']:>+10.2f}  "
                    f"combined={values['combined']['pnl']:>+10.2f}"
                )


if __name__ == "__main__":
    run_cli()
