from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibkr import connect, get_option_quotes
from stock_tooling.portfolio_scenario_ev import analyze, refresh_market_snapshot


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def dte(expiry: str, as_of: date) -> int:
    return max((parse_date(expiry) - as_of).days, 1)


def strike_range(min_strike: int, max_strike: int, step: int) -> list[float]:
    return [float(k) for k in range(min_strike, max_strike + 1, step)]


def ibkr_expiry(expiry: str) -> str:
    return expiry.replace("-", "")


def scanner_client_id() -> int:
    return 2800 + (os.getpid() % 7000)


def fetch_put_quotes_ibkr(
    symbol: str,
    expiry: str,
    strikes: list[float],
    *,
    market_data_type: int,
    debug: bool,
) -> dict[float, dict[str, float]]:
    contract_expiry = ibkr_expiry(expiry)
    specs = [(float(strike), contract_expiry, "P") for strike in strikes]
    with connect(client_id=scanner_client_id(), market_data_type=market_data_type, debug=debug) as ib:
        quotes = get_option_quotes(ib, symbol, specs, debug=debug)
    payload: dict[float, dict[str, float]] = {}
    for spec, quote in zip(specs, quotes, strict=True):
        strike = spec[0]
        price = quote.mid if quote.has_market else quote.last
        payload[strike] = {
            "price": float(price),
            "bid": float(quote.bid),
            "ask": float(quote.ask),
            "iv": float(quote.iv) if quote.iv > 0 else 0.0,
            "source": "ibkr",
        }
    return payload


def suspicious_strikes(
    quotes: dict[float, dict[str, float]],
    *,
    allowed_strikes: set[float],
    tolerance_pct: float = 0.05,
) -> set[float]:
    strikes = sorted(strike for strike in quotes if strike in allowed_strikes)
    bad: set[float] = set()
    prev_price: float | None = None
    for strike in strikes:
        price = quotes[strike]["price"]
        if price <= 0:
            bad.add(strike)
            continue
        if prev_price is not None and price < prev_price * (1.0 - tolerance_pct):
            bad.add(strike)
        prev_price = price
    return bad


def require_quote_iv(*, iv: float, symbol: str, expiry: str, strike: float) -> float:
    if iv <= 0:
        raise ValueError(
            f"Missing or invalid IBKR IV for {symbol} {expiry} {strike:.0f}P; "
            "scanner is strict and will not backfill IV."
        )
    return iv


def build_vertical_candidates(
    *,
    expiry: str,
    quotes: dict[float, dict[str, float]],
    long_strikes: list[float],
    short_strikes: list[float],
    as_of: date,
    target_budget: float,
    baseline_name: str,
    baseline_legs: list[dict],
    baseline_entry_cost: float,
    excluded_strikes: set[float],
    symbol: str,
) -> list[dict]:
    candidates: list[dict] = []
    expiry_dte = dte(expiry, as_of)
    for long_strike in long_strikes:
        if long_strike not in quotes:
            continue
        if long_strike in excluded_strikes:
            continue
        for short_strike in short_strikes:
            if short_strike >= long_strike or short_strike not in quotes:
                continue
            if short_strike in excluded_strikes:
                continue
            long_price = quotes[long_strike]["price"]
            short_price = quotes[short_strike]["price"]
            debit = long_price - short_price
            if debit <= 0:
                continue
            qty = max(1, int(round(target_budget / (debit * 100.0))))
            long_iv = require_quote_iv(
                iv=quotes[long_strike]["iv"],
                symbol=symbol,
                expiry=expiry,
                strike=long_strike,
            )
            short_iv = require_quote_iv(
                iv=quotes[short_strike]["iv"],
                symbol=symbol,
                expiry=expiry,
                strike=short_strike,
            )
            candidates.append({
                "name": f"{baseline_name} + {expiry} {int(long_strike)}/{int(short_strike)} x{qty}",
                "vehicle_type": "put_spread_overlay",
                "entry_cost": round(baseline_entry_cost + debit * 100.0 * qty, 2),
                "legs": baseline_legs + [
                    {
                        "label": f"Long {expiry} {int(long_strike)}P",
                        "right": "P",
                        "strike": long_strike,
                        "dte": expiry_dte,
                        "qty": qty,
                        "mark": long_price,
                        "iv": long_iv,
                    },
                    {
                        "label": f"Short {expiry} {int(short_strike)}P",
                        "right": "P",
                        "strike": short_strike,
                        "dte": expiry_dte,
                        "qty": -qty,
                        "mark": short_price,
                        "iv": short_iv,
                    },
                ],
            })
    return candidates


def build_calendar_candidates(
    *,
    short_expiry: str,
    long_expiry: str,
    short_quotes: dict[float, dict[str, float]],
    long_quotes: dict[float, dict[str, float]],
    strikes: list[float],
    as_of: date,
    target_budget: float,
    baseline_name: str,
    baseline_legs: list[dict],
    baseline_entry_cost: float,
    excluded_strikes: set[float],
    symbol: str,
) -> list[dict]:
    candidates: list[dict] = []
    short_dte = dte(short_expiry, as_of)
    long_dte = dte(long_expiry, as_of)
    for strike in strikes:
        if strike not in short_quotes or strike not in long_quotes:
            continue
        if strike in excluded_strikes:
            continue
        short_price = short_quotes[strike]["price"]
        long_price = long_quotes[strike]["price"]
        debit = long_price - short_price
        if debit <= 0:
            continue
        qty = max(1, int(round(target_budget / (debit * 100.0))))
        short_iv = require_quote_iv(
            iv=short_quotes[strike]["iv"],
            symbol=symbol,
            expiry=short_expiry,
            strike=strike,
        )
        long_iv = require_quote_iv(
            iv=long_quotes[strike]["iv"],
            symbol=symbol,
            expiry=long_expiry,
            strike=strike,
        )
        candidates.append({
            "name": f"{baseline_name} + {short_expiry}/{long_expiry} {int(strike)}P cal x{qty}",
            "vehicle_type": "put_calendar_overlay",
            "entry_cost": round(baseline_entry_cost + debit * 100.0 * qty, 2),
            "legs": baseline_legs + [
                {
                    "label": f"Long {long_expiry} {int(strike)}P",
                    "right": "P",
                    "strike": strike,
                    "dte": long_dte,
                    "qty": qty,
                    "mark": long_price,
                    "iv": long_iv,
                },
                {
                    "label": f"Short {short_expiry} {int(strike)}P",
                    "right": "P",
                    "strike": strike,
                    "dte": short_dte,
                    "qty": -qty,
                    "mark": short_price,
                    "iv": short_iv,
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
            "vehicle_type": meta.get(name, {}).get("vehicle_type"),
            "entry_cost": meta.get(name, {}).get("entry_cost"),
            "expected_combined_pnl": summary["expected_combined_pnl"],
            "expected_overlay_pnl": summary["expected_overlay_pnl"],
            "weighted_downside_coverage_pct": summary["weighted_downside_coverage_pct"],
            "avg_combined_pnl_when_downside": summary["avg_combined_pnl_when_downside"],
        }
        ranked.append(item)
    ranked.sort(key=lambda item: item["expected_combined_pnl"], reverse=True)
    return ranked


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch scan EWY put overlay candidates")
    parser.add_argument("--symbol", default="EWY")
    parser.add_argument("--as-of", default="2026-03-11")
    parser.add_argument("--vertical-expiry", default="2026-04-10")
    parser.add_argument("--calendar-short-expiry", default="2026-04-02")
    parser.add_argument("--calendar-long-expiry", default="2026-04-10")
    parser.add_argument("--long-min", type=int, default=125)
    parser.add_argument("--long-max", type=int, default=150)
    parser.add_argument("--short-min", type=int, default=110)
    parser.add_argument("--short-max", type=int, default=130)
    parser.add_argument("--calendar-min", type=int, default=110)
    parser.add_argument("--calendar-max", type=int, default=150)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--target-budget", type=float, default=30000.0)
    parser.add_argument("--risk-free-rate", type=float, default=0.045)
    parser.add_argument("--market-data-type", type=int, default=3, help="1=live, 3=delayed, 4=delayed-frozen")
    parser.add_argument(
        "--strict-refresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require IBKR refresh success before running the scan.",
    )
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable verbose IBKR logging.",
    )
    parser.add_argument("--include-suspicious", action="store_true")
    parser.add_argument(
        "--base-input",
        default="analysis/2026-03-11/ewy_layered_user_regime_input.json",
    )
    parser.add_argument(
        "--output",
        default="analysis/2026-03-11/ewy_put_overlay_batch_scan.json",
    )
    parser.add_argument(
        "--summary-output",
        default="analysis/2026-03-11/ewy_put_overlay_batch_scan.md",
    )
    args = parser.parse_args()

    as_of = parse_date(args.as_of)
    base = json.loads(Path(args.base_input).read_text())
    base = refresh_market_snapshot(
        base,
        symbol=args.symbol,
        mode="overlay",
        market_data_type=args.market_data_type,
        debug=bool(args.debug),
        fallback_to_disk=not bool(args.strict_refresh),
    )
    spot = float(base["spot"])
    baseline = next(candidate for candidate in base["hedges"] if candidate["name"] == "Planned call sales only")

    scenarios = [
        {
            "label": "Bottom Apr02 then rebound by earnings",
            "probability": 0.35,
            "days": dte(args.calendar_short_expiry, as_of),
            "spot": round(spot * 0.94, 2),
            "vol_shift": 0.03,
        },
        {
            "label": "Bottom Apr10 then rebound by earnings",
            "probability": 0.40,
            "days": dte(args.vertical_expiry, as_of),
            "spot": round(spot * 0.93, 2),
            "vol_shift": 0.02,
        },
        {
            "label": "Choppy hold into earnings window",
            "probability": 0.15,
            "days": dte(args.vertical_expiry, as_of),
            "spot": round(spot, 2),
            "vol_shift": 0.01,
        },
        {
            "label": "Early squeeze higher before earnings",
            "probability": 0.10,
            "days": dte(args.vertical_expiry, as_of),
            "spot": round(spot * 1.08, 2),
            "vol_shift": -0.05,
        },
    ]

    long_grid = set(strike_range(args.long_min, args.long_max, args.step))
    short_grid = set(strike_range(args.short_min, args.short_max, args.step))
    calendar_grid = set(strike_range(args.calendar_min, args.calendar_max, args.step))
    relevant_grid = long_grid | short_grid | calendar_grid
    vertical_quotes = fetch_put_quotes_ibkr(
        args.symbol,
        args.vertical_expiry,
        sorted(long_grid | short_grid),
        market_data_type=args.market_data_type,
        debug=bool(args.debug),
    )
    cal_short_quotes = fetch_put_quotes_ibkr(
        args.symbol,
        args.calendar_short_expiry,
        sorted(calendar_grid),
        market_data_type=args.market_data_type,
        debug=bool(args.debug),
    )
    cal_long_quotes = fetch_put_quotes_ibkr(
        args.symbol,
        args.calendar_long_expiry,
        sorted(calendar_grid),
        market_data_type=args.market_data_type,
        debug=bool(args.debug),
    )
    excluded_strikes = set()
    if not args.include_suspicious:
        excluded_strikes |= suspicious_strikes(vertical_quotes, allowed_strikes=relevant_grid)
        excluded_strikes |= suspicious_strikes(cal_short_quotes, allowed_strikes=relevant_grid)
        excluded_strikes |= suspicious_strikes(cal_long_quotes, allowed_strikes=relevant_grid)

    candidates: list[dict] = [baseline]
    candidates.extend(build_vertical_candidates(
        expiry=args.vertical_expiry,
        quotes=vertical_quotes,
        long_strikes=strike_range(args.long_min, args.long_max, args.step),
        short_strikes=strike_range(args.short_min, args.short_max, args.step),
        as_of=as_of,
        target_budget=args.target_budget,
        baseline_name="Calls",
        baseline_legs=baseline["legs"],
        baseline_entry_cost=baseline["entry_cost"],
        excluded_strikes=excluded_strikes,
        symbol=args.symbol,
    ))
    candidates.extend(build_calendar_candidates(
        short_expiry=args.calendar_short_expiry,
        long_expiry=args.calendar_long_expiry,
        short_quotes=cal_short_quotes,
        long_quotes=cal_long_quotes,
        strikes=strike_range(args.calendar_min, args.calendar_max, args.step),
        as_of=as_of,
        target_budget=args.target_budget,
        baseline_name="Calls",
        baseline_legs=baseline["legs"],
        baseline_entry_cost=baseline["entry_cost"],
        excluded_strikes=excluded_strikes,
        symbol=args.symbol,
    ))

    config = {
        "analysis_type": "put_overlay_batch_scan",
        "macro": {
            "notes": "Bottom-window overlay scan for current EWY book plus planned call sales.",
        },
        "spot": spot,
        "risk_free_rate": args.risk_free_rate,
        "book": base["book"],
        "scenarios": scenarios,
        "hedges": candidates,
    }
    output = analyze(config)
    output["candidate_count"] = len(candidates) - 1
    output["excluded_strikes"] = sorted(excluded_strikes)
    output["ranked_candidates"] = summarize_rankings(output, candidates)
    output["candidate_metadata"] = candidates[1:]
    output["market_refresh"] = base.get("market_refresh", {})

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2))

    lines = [
        f"# {args.symbol} Put Overlay Batch Scan",
        "",
        f"Spot: `{spot:.2f}`",
        f"Vertical expiry: `{args.vertical_expiry}`",
        f"Calendar pair: `{args.calendar_short_expiry}/{args.calendar_long_expiry}`",
        f"Candidates: `{len(candidates) - 1}`",
        "",
        "## Top Candidates",
        "",
    ]
    for idx, item in enumerate(output["ranked_candidates"][:15], start=1):
        lines.append(
            f"{idx}. `{item['name']}` | type `{item['vehicle_type']}` | "
            f"EV `{item['expected_combined_pnl']:.0f}` | "
            f"downside avg `{item['avg_combined_pnl_when_downside']:.0f}` | "
            f"cover `{item['weighted_downside_coverage_pct']:.1f}%` | "
            f"entry `{item['entry_cost']:.0f}`"
        )
    Path(args.summary_output).write_text("\n".join(lines) + "\n")

    print(f"Saved {output_path}")
    print(f"Saved {args.summary_output}")
    for item in output["ranked_candidates"][:10]:
        print(
            f"{item['name']:<42} "
            f"EV={item['expected_combined_pnl']:>+10.0f} "
            f"down={item['avg_combined_pnl_when_downside']:>+10.0f} "
            f"cover={item['weighted_downside_coverage_pct']:>5.1f}% "
            f"entry={item['entry_cost']:>8.0f}"
        )


if __name__ == "__main__":
    main()
