from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from ib_insync import Stock

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibkr import connect, get_option_quotes, get_portfolio
from stock_tooling.portfolio_scenario_ev import analyze
from stock_tooling.scan_put_overlays import (
    build_calendar_candidates,
    build_vertical_candidates,
    suspicious_strikes,
)


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def dte(expiry: str, *, as_of: date) -> int:
    return max((parse_date(expiry) - as_of).days, 1)


def strike_range(min_strike: int, max_strike: int, step: int) -> list[float]:
    return [float(k) for k in range(min_strike, max_strike + 1, step)]


def parse_csv_dates(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_csv_pairs(value: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        short_expiry, long_expiry = item.split("/")
        pairs.append((short_expiry.strip(), long_expiry.strip()))
    return pairs


def fetch_spot_from_history(*, symbol: str, market_data_type: int, debug: bool) -> float:
    with connect(client_id=2911, market_data_type=market_data_type, readonly=True, debug=debug) as ib:
        contract = Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="3 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
        )
        if not bars:
            raise RuntimeError(f"No IBKR historical bars for {symbol}")
        return float(bars[-1].close)


def fetch_live_book(
    *,
    symbol: str,
    market_data_type: int,
    debug: bool,
    excluded_hedge_expiry: str,
    excluded_put_strikes: set[float],
) -> list[dict]:
    with connect(client_id=2912, market_data_type=market_data_type, readonly=True, debug=debug) as ib:
        positions = [p for p in get_portfolio(ib, symbols=[symbol]) if p.sec_type == "OPT"]
        core_positions = [
            p for p in positions
            if not (
                p.expiry == excluded_hedge_expiry.replace("-", "")
                and p.right == "P"
                and p.strike in excluded_put_strikes
            )
        ]
        specs = [(p.strike, p.expiry, p.right) for p in core_positions]
        quotes = get_option_quotes(ib, symbol, specs, debug=debug)

    payload: list[dict] = []
    for position, quote in zip(core_positions, quotes, strict=True):
        mark = quote.mid if quote.has_market else (position.market_price if position.market_price > 0 else quote.last)
        if mark <= 0 or quote.iv <= 0:
            raise RuntimeError(
                f"Missing usable broker mark/iv for live book line "
                f"{position.symbol} {position.expiry} {position.strike:.0f}{position.right}"
            )
        payload.append({
            "label": f"{position.symbol} {position.expiry} {int(position.strike)}{position.right}",
            "symbol": position.symbol,
            "right": position.right,
            "strike": float(position.strike),
            "expiry": position.expiry,
            "dte": int(position.dte or 0),
            "qty": int(position.qty),
            "mark": float(mark),
            "iv": float(quote.iv),
        })
    return payload


def fetch_put_quotes_by_expiry(
    *,
    symbol: str,
    expiries: list[str],
    strikes: list[float],
    market_data_type: int,
    debug: bool,
) -> dict[str, dict[float, dict[str, float]]]:
    payload: dict[str, dict[float, dict[str, float]]] = {}
    with connect(client_id=2913, market_data_type=market_data_type, readonly=True, debug=debug) as ib:
        for expiry in expiries:
            specs = [(float(strike), expiry.replace("-", ""), "P") for strike in strikes]
            quotes = get_option_quotes(ib, symbol, specs, debug=debug)
            payload[expiry] = {
                float(strike): {
                    "price": float(quote.mid),
                    "bid": float(quote.bid),
                    "ask": float(quote.ask),
                    "iv": float(quote.iv),
                }
                for strike, quote in zip(strikes, quotes, strict=True)
            }
    return payload


def build_long_put_candidates(
    *,
    expiries: list[str],
    quotes_by_expiry: dict[str, dict[float, dict[str, float]]],
    strikes: list[float],
    as_of: date,
    target_budget: float,
    symbol: str,
    excluded_by_expiry: dict[str, set[float]],
) -> list[dict]:
    candidates: list[dict] = []
    for expiry in expiries:
        expiry_dte = dte(expiry, as_of=as_of)
        for strike in strikes:
            if strike in excluded_by_expiry[expiry]:
                continue
            quote = quotes_by_expiry[expiry][strike]
            if quote["bid"] <= 0 or quote["ask"] <= 0 or quote["iv"] <= 0 or quote["price"] <= 0:
                continue
            qty = max(1, int(round(target_budget / (quote["price"] * 100.0))))
            candidates.append({
                "name": f"Add + {expiry} {int(strike)}P x{qty}",
                "vehicle_type": "long_put_overlay",
                "entry_cost": round(quote["price"] * 100.0 * qty, 2),
                "legs": [
                    {
                        "label": f"Long {expiry} {int(strike)}P",
                        "symbol": symbol,
                        "right": "P",
                        "strike": strike,
                        "expiry": expiry.replace("-", ""),
                        "dte": expiry_dte,
                        "qty": qty,
                        "mark": quote["price"],
                        "iv": quote["iv"],
                    }
                ],
            })
    return candidates


def build_diagonal_candidates(
    *,
    pairs: list[tuple[str, str]],
    quotes_by_expiry: dict[str, dict[float, dict[str, float]]],
    short_strikes: list[float],
    long_strikes: list[float],
    as_of: date,
    target_budget: float,
    symbol: str,
    excluded_by_expiry: dict[str, set[float]],
    max_width: float,
) -> list[dict]:
    candidates: list[dict] = []
    for short_expiry, long_expiry in pairs:
        short_dte = dte(short_expiry, as_of=as_of)
        long_dte = dte(long_expiry, as_of=as_of)
        short_quotes = quotes_by_expiry[short_expiry]
        long_quotes = quotes_by_expiry[long_expiry]
        excluded = excluded_by_expiry[short_expiry] | excluded_by_expiry[long_expiry]
        for short_strike in short_strikes:
            if short_strike in excluded:
                continue
            short_quote = short_quotes[short_strike]
            if short_quote["bid"] <= 0 or short_quote["ask"] <= 0 or short_quote["iv"] <= 0 or short_quote["price"] <= 0:
                continue
            for long_strike in long_strikes:
                if long_strike in excluded:
                    continue
                if long_strike < short_strike:
                    continue
                if long_strike - short_strike > max_width:
                    continue
                if long_strike == short_strike:
                    continue
                long_quote = long_quotes[long_strike]
                if long_quote["bid"] <= 0 or long_quote["ask"] <= 0 or long_quote["iv"] <= 0 or long_quote["price"] <= 0:
                    continue
                debit = long_quote["price"] - short_quote["price"]
                if debit <= 0:
                    continue
                qty = max(1, int(round(target_budget / (debit * 100.0))))
                candidates.append({
                    "name": f"Add + {short_expiry}/{long_expiry} {int(short_strike)}/{int(long_strike)} put diag x{qty}",
                    "vehicle_type": "put_diagonal_overlay",
                    "entry_cost": round(debit * 100.0 * qty, 2),
                    "legs": [
                        {
                            "label": f"Short {short_expiry} {int(short_strike)}P",
                            "symbol": symbol,
                            "right": "P",
                            "strike": short_strike,
                            "expiry": short_expiry.replace("-", ""),
                            "dte": short_dte,
                            "qty": -qty,
                            "mark": short_quote["price"],
                            "iv": short_quote["iv"],
                        },
                        {
                            "label": f"Long {long_expiry} {int(long_strike)}P",
                            "symbol": symbol,
                            "right": "P",
                            "strike": long_strike,
                            "expiry": long_expiry.replace("-", ""),
                            "dte": long_dte,
                            "qty": qty,
                            "mark": long_quote["price"],
                            "iv": long_quote["iv"],
                        },
                    ],
                })
    return candidates


def summarize_rankings(output: dict, candidates: list[dict]) -> list[dict]:
    ranked: list[dict] = []
    meta = {candidate["name"]: candidate for candidate in candidates}
    for name, summary in output["summaries"].items():
        if name == "No hedge":
            continue
        item = {
            "name": name,
            "vehicle_type": meta[name]["vehicle_type"],
            "entry_cost": meta[name]["entry_cost"],
            "expected_book_pnl": summary["expected_book_pnl"],
            "expected_overlay_pnl": summary["expected_hedge_pnl"],
            "expected_combined_pnl": summary["expected_combined_pnl"],
            "weighted_downside_coverage_pct": summary["weighted_downside_coverage_pct"],
            "avg_combined_pnl_when_downside": summary["avg_combined_pnl_when_downside"],
        }
        ranked.append(item)
    ranked.sort(key=lambda item: item["expected_combined_pnl"], reverse=True)
    return ranked


def write_report(
    *,
    output_path: Path,
    summary_path: Path,
    analysis_type: str,
    symbol: str,
    as_of: date,
    spot: float,
    target_budget: float,
    base_book_definition: str,
    scenarios: list[dict],
    ranked: list[dict],
    candidate_count: int,
    excluded_by_expiry: dict[str, set[float]],
) -> None:
    payload = {
        "schema_version": "1.0",
        "analysis_type": analysis_type,
        "as_of": as_of.isoformat(),
        "symbol": symbol,
        "quote_source": "IBKR historical close + delayed-frozen options",
        "target_budget": target_budget,
        "base_book_definition": base_book_definition,
        "scenarios": scenarios,
        "candidate_count": candidate_count,
        "excluded_strikes_by_expiry": {key: sorted(value) for key, value in excluded_by_expiry.items()},
        "top_ranked": ranked[:30],
        "all_ranked": ranked,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))

    lines = [
        f"# {analysis_type}",
        "",
        f"Spot: `{spot:.2f}`",
        f"Candidates: `{candidate_count}`",
        f"Budget target: `{target_budget:.0f}`",
        f"Base book: {base_book_definition}",
        "",
        "## Scenarios",
        "",
    ]
    for scenario in scenarios:
        lines.append(
            f"- `{scenario['probability'] * 100:.0f}%` {scenario['label']} | "
            f"days `{scenario['days']}` | spot `{scenario['spot']}` | vol `{scenario['vol_shift']:+.2f}`"
        )
    lines += ["", "## Top 15", ""]
    for idx, item in enumerate(ranked[:15], start=1):
        lines.append(
            f"{idx}. `{item['name']}` | type `{item['vehicle_type']}` | entry `{item['entry_cost']:.0f}` | "
            f"overlay EV `{item['expected_overlay_pnl']:.0f}` | combined EV `{item['expected_combined_pnl']:.0f}` | "
            f"downside cover `{item['weighted_downside_coverage_pct']:.1f}%`"
        )
    summary_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Broad EWY put hedge universe scanner")
    parser.add_argument("--symbol", default="EWY")
    parser.add_argument("--as-of", default="2026-03-12")
    parser.add_argument("--market-data-type", type=int, default=4)
    parser.add_argument("--target-budget", type=float, default=25000.0)
    parser.add_argument("--risk-free-rate", type=float, default=0.045)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--exclude-live-apr10-hedge", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--excluded-hedge-expiry", default="2026-04-10")
    parser.add_argument("--excluded-hedge-strikes", default="120,135")
    parser.add_argument("--put-expiries", default="2026-03-27,2026-04-02,2026-04-10,2026-04-17,2026-04-24,2026-05-15")
    parser.add_argument("--vertical-expiries", default="2026-03-27,2026-04-02,2026-04-10,2026-04-17,2026-04-24,2026-05-15")
    parser.add_argument("--calendar-pairs", default="2026-03-27/2026-04-02,2026-04-02/2026-04-10,2026-04-02/2026-04-17,2026-04-10/2026-04-17,2026-04-10/2026-04-24,2026-04-10/2026-05-15")
    parser.add_argument("--diagonal-pairs", default="2026-03-27/2026-04-02,2026-04-02/2026-04-10,2026-04-02/2026-04-17,2026-04-10/2026-04-17,2026-04-10/2026-04-24,2026-04-10/2026-05-15")
    parser.add_argument("--long-min", type=int, default=125)
    parser.add_argument("--long-max", type=int, default=150)
    parser.add_argument("--short-min", type=int, default=110)
    parser.add_argument("--short-max", type=int, default=135)
    parser.add_argument("--calendar-min", type=int, default=110)
    parser.add_argument("--calendar-max", type=int, default=150)
    parser.add_argument("--diagonal-short-min", type=int, default=115)
    parser.add_argument("--diagonal-short-max", type=int, default=135)
    parser.add_argument("--diagonal-long-min", type=int, default=125)
    parser.add_argument("--diagonal-long-max", type=int, default=145)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--max-diagonal-width", type=float, default=20.0)
    parser.add_argument("--weekly-output", default="analysis/2026-03-12/ewy_broad_put_hedge_universe_weekly_35_40_15_10.json")
    parser.add_argument("--weekly-summary", default="analysis/2026-03-12/ewy_broad_put_hedge_universe_weekly_35_40_15_10.md")
    parser.add_argument("--monthly-output", default="analysis/2026-03-12/ewy_broad_put_hedge_universe_monthly_50_40_10.json")
    parser.add_argument("--monthly-summary", default="analysis/2026-03-12/ewy_broad_put_hedge_universe_monthly_50_40_10.md")
    args = parser.parse_args()

    as_of = parse_date(args.as_of)
    symbol = args.symbol.upper()
    excluded_put_strikes = {float(item) for item in args.excluded_hedge_strikes.split(",") if item.strip()}

    put_expiries = parse_csv_dates(args.put_expiries)
    vertical_expiries = parse_csv_dates(args.vertical_expiries)
    calendar_pairs = parse_csv_pairs(args.calendar_pairs)
    diagonal_pairs = parse_csv_pairs(args.diagonal_pairs)

    long_strikes = strike_range(args.long_min, args.long_max, args.step)
    short_strikes = strike_range(args.short_min, args.short_max, args.step)
    calendar_strikes = strike_range(args.calendar_min, args.calendar_max, args.step)
    diagonal_short_strikes = strike_range(args.diagonal_short_min, args.diagonal_short_max, args.step)
    diagonal_long_strikes = strike_range(args.diagonal_long_min, args.diagonal_long_max, args.step)
    all_strikes = sorted(set(long_strikes) | set(short_strikes) | set(calendar_strikes) | set(diagonal_short_strikes) | set(diagonal_long_strikes))

    spot = fetch_spot_from_history(symbol=symbol, market_data_type=args.market_data_type, debug=bool(args.debug))
    book_positions = fetch_live_book(
        symbol=symbol,
        market_data_type=args.market_data_type,
        debug=bool(args.debug),
        excluded_hedge_expiry=args.excluded_hedge_expiry if args.exclude_live_apr10_hedge else "1900-01-01",
        excluded_put_strikes=excluded_put_strikes if args.exclude_live_apr10_hedge else set(),
    )

    expiries_needed = sorted(
        set(put_expiries)
        | set(vertical_expiries)
        | {short for short, _ in calendar_pairs}
        | {long for _, long in calendar_pairs}
        | {short for short, _ in diagonal_pairs}
        | {long for _, long in diagonal_pairs}
    )
    quotes_by_expiry = fetch_put_quotes_by_expiry(
        symbol=symbol,
        expiries=expiries_needed,
        strikes=all_strikes,
        market_data_type=args.market_data_type,
        debug=bool(args.debug),
    )

    allowed = set(all_strikes)
    excluded_by_expiry: dict[str, set[float]] = {}
    for expiry, quotes in quotes_by_expiry.items():
        excluded = suspicious_strikes(quotes, allowed_strikes=allowed)
        for strike, quote in quotes.items():
            if strike not in allowed:
                continue
            if quote["bid"] <= 0 or quote["ask"] <= 0 or quote["iv"] <= 0 or quote["price"] <= 0:
                excluded.add(float(strike))
        excluded_by_expiry[expiry] = excluded

    candidates: list[dict] = []
    candidates.extend(build_long_put_candidates(
        expiries=put_expiries,
        quotes_by_expiry=quotes_by_expiry,
        strikes=calendar_strikes,
        as_of=as_of,
        target_budget=args.target_budget,
        symbol=symbol,
        excluded_by_expiry=excluded_by_expiry,
    ))
    for expiry in vertical_expiries:
        candidates.extend(build_vertical_candidates(
            expiry=expiry,
            quotes=quotes_by_expiry[expiry],
            long_strikes=long_strikes,
            short_strikes=short_strikes,
            as_of=as_of,
            target_budget=args.target_budget,
            baseline_name="Add",
            baseline_legs=[],
            baseline_entry_cost=0.0,
            excluded_strikes=excluded_by_expiry[expiry],
            symbol=symbol,
        ))
    for short_expiry, long_expiry in calendar_pairs:
        candidates.extend(build_calendar_candidates(
            short_expiry=short_expiry,
            long_expiry=long_expiry,
            short_quotes=quotes_by_expiry[short_expiry],
            long_quotes=quotes_by_expiry[long_expiry],
            strikes=calendar_strikes,
            as_of=as_of,
            target_budget=args.target_budget,
            baseline_name="Add",
            baseline_legs=[],
            baseline_entry_cost=0.0,
            excluded_strikes=excluded_by_expiry[short_expiry] | excluded_by_expiry[long_expiry],
            symbol=symbol,
        ))
    candidates.extend(build_diagonal_candidates(
        pairs=diagonal_pairs,
        quotes_by_expiry=quotes_by_expiry,
        short_strikes=diagonal_short_strikes,
        long_strikes=diagonal_long_strikes,
        as_of=as_of,
        target_budget=args.target_budget,
        symbol=symbol,
        excluded_by_expiry=excluded_by_expiry,
        max_width=args.max_diagonal_width,
    ))

    weekly_scenarios = [
        {"label": "Bottom Apr02 then rebound by earnings", "probability": 0.35, "days": max((date(2026, 4, 2) - as_of).days, 1), "spot": round(spot * 0.94, 2), "vol_shift": 0.03},
        {"label": "Bottom Apr10 then rebound by earnings", "probability": 0.40, "days": max((date(2026, 4, 10) - as_of).days, 1), "spot": round(spot * 0.93, 2), "vol_shift": 0.02},
        {"label": "Choppy hold into earnings window", "probability": 0.15, "days": max((date(2026, 4, 10) - as_of).days, 1), "spot": round(spot, 2), "vol_shift": 0.01},
        {"label": "Early squeeze higher before earnings", "probability": 0.10, "days": max((date(2026, 4, 10) - as_of).days, 1), "spot": round(spot * 1.08, 2), "vol_shift": -0.05},
    ]
    monthly_scenarios = [
        {"label": "Choppy month flat", "probability": 0.50, "days": 31, "spot": round(spot, 2), "vol_shift": 0.0},
        {"label": "Down 8% over month", "probability": 0.40, "days": 31, "spot": round(spot * 0.92, 2), "vol_shift": 0.01},
        {"label": "Rally 8% over month", "probability": 0.10, "days": 31, "spot": round(spot * 1.08, 2), "vol_shift": -0.05},
    ]

    base_book_definition = (
        "Current live EWY option book excluding the existing Apr10 135/120 put hedge; "
        "includes current short-call sleeve."
    )

    for analysis_type, scenarios, output_path, summary_path in [
        ("ewy_broad_put_hedge_universe_weekly_35_40_15_10", weekly_scenarios, Path(args.weekly_output), Path(args.weekly_summary)),
        ("ewy_broad_put_hedge_universe_monthly_50_40_10", monthly_scenarios, Path(args.monthly_output), Path(args.monthly_summary)),
    ]:
        output = analyze({
            "analysis_type": analysis_type,
            "spot": spot,
            "risk_free_rate": args.risk_free_rate,
            "book": {"symbol": symbol, "positions": book_positions},
            "scenarios": scenarios,
            "hedges": candidates,
        })
        ranked = summarize_rankings(output, candidates)
        write_report(
            output_path=output_path,
            summary_path=summary_path,
            analysis_type=analysis_type,
            symbol=symbol,
            as_of=as_of,
            spot=spot,
            target_budget=args.target_budget,
            base_book_definition=base_book_definition,
            scenarios=scenarios,
            ranked=ranked,
            candidate_count=len(candidates),
            excluded_by_expiry=excluded_by_expiry,
        )
        print(output_path)
        print(summary_path)
        for item in ranked[:5]:
            print(json.dumps(item))


if __name__ == "__main__":
    main()
