"""
Poll IBKR for open orders, fills, positions, and optional live quote context.

Examples:
    uv run python watch_orders.py EWY --expiry 20280121 --strike 145 --right C
    uv run python watch_orders.py EWY --changes-only --show-positions --include-quote
    uv run python watch_orders.py EWY --exit-when-done --json --output analysis/2026-03-12/ewy_watch.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibkr import (
    connect,
    get_open_orders,
    get_option_quotes,
    get_portfolio,
    get_recent_fills,
    get_spot,
)
from stock_tooling.reporting import print_open_orders, print_portfolio, print_recent_fills
from stock_tooling.watch_rules import assess_watch_state, load_watch_rules


def _matches_contract(
    item,
    expiry: str | None,
    strike: float | None,
    right: str | None,
) -> bool:
    if expiry and getattr(item, "expiry", "") != expiry:
        return False
    if strike is not None and float(getattr(item, "strike", 0.0)) != float(strike):
        return False
    if right and getattr(item, "right", "").upper() != right.upper():
        return False
    return True


def _orders_signature(orders) -> tuple:
    return tuple(
        (
            order.order_id,
            order.status,
            order.filled,
            order.remaining,
            order.limit_price,
            order.quantity,
        )
        for order in orders
    )


def _positions_signature(positions) -> tuple:
    return tuple(
        (
            pos.symbol,
            pos.expiry,
            pos.strike,
            pos.right,
            pos.qty,
            pos.market_price,
            pos.market_value,
        )
        for pos in positions
    )


def _quote_signature(quote: dict | None) -> tuple | None:
    if not quote:
        return None
    option_quote = quote.get("option_quote")
    if not option_quote:
        return (quote.get("spot"), quote.get("quote_error"))
    return (
        quote.get("spot"),
        option_quote.get("bid"),
        option_quote.get("ask"),
        option_quote.get("last"),
        option_quote.get("mid"),
        option_quote.get("iv"),
        option_quote.get("delta"),
    )


def _sum_fill_qty(fills) -> float:
    return round(sum(float(fill.shares) for fill in fills), 4)


def _render_quote(symbol: str, quote: dict) -> None:
    if quote.get("quote_error"):
        print(f"Quote: {symbol} error={quote['quote_error']}")
        return

    parts = [f"Quote: {symbol} spot={quote['spot']:.4f}"]
    option_quote = quote.get("option_quote")
    if option_quote:
        parts.append(
            f"[{option_quote['bid']:.2f} x {option_quote['ask']:.2f}]"
            f" mid={option_quote['mid']:.4f}"
            f" last={option_quote['last']:.4f}"
            f" iv={option_quote['iv']:.4f}"
            f" delta={option_quote['delta']:.4f}"
        )
    print(" ".join(parts))


def _render_assessment(assessment: dict | None) -> None:
    if not assessment:
        return
    print(
        "Watch:"
        f" regime={assessment['liquidity_regime']}"
        f" confidence={assessment['confidence']:.2f}"
        f" poll={assessment['recommended_poll_seconds']:.0f}s"
        f" observe={assessment['recommended_observation_seconds']:.0f}s"
        f" action={assessment['suggested_action']}"
    )
    print(f"Signals: {', '.join(assessment['signals'])}")


def _build_quote_snapshot(
    ib,
    *,
    symbol: str | None,
    expiry: str | None,
    strike: float | None,
    right: str | None,
    settle_secs: float,
    debug: bool,
) -> dict | None:
    if not symbol:
        return None

    quote_snapshot = {
        "symbol": symbol,
        "spot": None,
        "quote_error": None,
    }

    try:
        quote_snapshot["spot"] = get_spot(ib, symbol, debug=debug, allow_close_fallback=True)
    except Exception as exc:
        quote_snapshot["quote_error"] = f"{type(exc).__name__}: {exc}"
        return quote_snapshot

    if expiry and strike is not None and right:
        try:
            [option_quote] = get_option_quotes(
                ib,
                symbol,
                [(strike, expiry, right)],
                settle_secs=settle_secs,
                debug=debug,
            )
            quote_snapshot["option_quote"] = {
                "symbol": option_quote.symbol,
                "expiry": option_quote.expiry,
                "strike": option_quote.strike,
                "right": option_quote.right,
                "bid": option_quote.bid,
                "ask": option_quote.ask,
                "mid": option_quote.mid,
                "last": option_quote.last,
                "iv": option_quote.iv,
                "delta": option_quote.delta,
                "gamma": option_quote.gamma,
                "theta": option_quote.theta,
                "vega": option_quote.vega,
            }
        except Exception as exc:
            quote_snapshot["quote_error"] = f"{type(exc).__name__}: {exc}"

    return quote_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll IBKR for order/fill status")
    parser.add_argument("symbols", nargs="*", help="Optional symbol filters.")
    parser.add_argument("--expiry", default=None, help="Filter options by expiry YYYYMMDD")
    parser.add_argument("--strike", type=float, default=None, help="Filter options by strike")
    parser.add_argument("--right", default=None, help="Filter options by right, e.g. C or P")
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--iterations", type=int, default=0, help="0 means run until interrupted")
    parser.add_argument("--once", action="store_true", help="Run a single poll and exit")
    parser.add_argument("--market-data-type", type=int, default=3, help="1=live, 3=delayed, 4=delayed-frozen")
    parser.add_argument("--show-positions", action="store_true", help="Print filtered positions on each change")
    parser.add_argument("--changes-only", action="store_true", help="Print only when orders/fills/positions/quotes change")
    parser.add_argument("--exit-when-done", action="store_true", help="Stop once there are no matching open orders")
    parser.add_argument("--include-quote", action="store_true", help="Include live spot/option quote context in each poll")
    parser.add_argument("--quote-settle-seconds", type=float, default=1.0, help="Extra settle time after quote requests")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON snapshots instead of text")
    parser.add_argument("--output", default=None, help="Optional path to write the full watch history JSON")
    parser.add_argument("--rules-config", default=None, help="Optional watch rules JSON path")
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print detailed IBKR connection diagnostics.",
    )
    args = parser.parse_args()

    if args.once:
        args.iterations = 1

    symbols = [symbol.upper() for symbol in args.symbols] or None
    expiry = args.expiry.replace("-", "") if args.expiry else None
    right = args.right.upper() if args.right else None
    primary_symbol = symbols[0] if symbols and len(symbols) == 1 else None

    rules = load_watch_rules(args.rules_config)
    seen_fill_ids: set[str] = set()
    prev_orders_sig = None
    prev_positions_sig = None
    prev_quote_sig = None
    poll_count = 0
    watch_started_at: datetime | None = None
    snapshots: list[dict] = []

    with connect(client_id=15, market_data_type=args.market_data_type, debug=args.debug) as ib:
        while True:
            if watch_started_at is None:
                watch_started_at = datetime.now()
            poll_count += 1

            orders = [
                order
                for order in get_open_orders(ib, symbols=symbols)
                if _matches_contract(order, expiry=expiry, strike=args.strike, right=right)
            ]
            fills = [
                fill
                for fill in get_recent_fills(ib, symbols=symbols)
                if _matches_contract(fill, expiry=expiry, strike=args.strike, right=right)
            ]
            new_fills = [fill for fill in fills if fill.exec_id not in seen_fill_ids]
            for fill in new_fills:
                seen_fill_ids.add(fill.exec_id)

            positions = []
            if args.show_positions:
                positions = [
                    pos
                    for pos in get_portfolio(ib, symbols=symbols)
                    if _matches_contract(pos, expiry=expiry, strike=args.strike, right=right)
                ]

            quote = None
            assessment = None
            if args.include_quote:
                quote = _build_quote_snapshot(
                    ib,
                    symbol=primary_symbol,
                    expiry=expiry,
                    strike=args.strike,
                    right=right,
                    settle_secs=args.quote_settle_seconds,
                    debug=args.debug,
                )
                option_quote = (quote or {}).get("option_quote")
                if option_quote:
                    elapsed = (datetime.now() - watch_started_at).total_seconds()
                    assessment = assess_watch_state(
                        bid=float(option_quote["bid"]),
                        ask=float(option_quote["ask"]),
                        last=float(option_quote["last"]),
                        open_order_count=len(orders),
                        new_fill_count=len(new_fills),
                        new_fill_qty=_sum_fill_qty(new_fills),
                        total_target_qty=sum(float(order.remaining) for order in orders) or None,
                        observed_seconds=elapsed,
                        rules=rules,
                    )

            orders_sig = _orders_signature(orders)
            positions_sig = _positions_signature(positions) if args.show_positions else None
            quote_sig = _quote_signature(quote)
            changed = (
                poll_count == 1
                or orders_sig != prev_orders_sig
                or bool(new_fills)
                or (args.show_positions and positions_sig != prev_positions_sig)
                or quote_sig != prev_quote_sig
            )

            snapshot = {
                "captured_at": datetime.now().isoformat(timespec="seconds"),
                "poll": poll_count,
                "filters": {
                    "symbols": symbols,
                    "expiry": expiry,
                    "strike": args.strike,
                    "right": right,
                },
                "open_orders": [asdict(order) for order in orders],
                "new_fills": [asdict(fill) for fill in new_fills],
                "positions": [asdict(position) for position in positions] if args.show_positions else [],
                "quote": quote,
                "assessment": assessment,
            }
            snapshots.append(snapshot)

            if changed or not args.changes_only:
                if args.json:
                    print(json.dumps(snapshot, indent=2))
                else:
                    print(f"\n[{snapshot['captured_at']}] poll={poll_count}")
                    print_open_orders(orders)
                    if new_fills or not args.changes_only:
                        print_recent_fills(new_fills)
                    if args.show_positions:
                        print_portfolio(positions)
                    if quote:
                        _render_quote(primary_symbol or "n/a", quote)
                    _render_assessment(assessment)

            prev_orders_sig = orders_sig
            prev_positions_sig = positions_sig
            prev_quote_sig = quote_sig

            if args.exit_when_done and poll_count > 1 and not orders:
                if not args.json:
                    print(f"\n[{datetime.now().isoformat(timespec='seconds')}] no matching open orders remain")
                break

            if args.iterations and poll_count >= args.iterations:
                break

            ib.sleep(args.poll_seconds)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rules_config": args.rules_config,
            "latest": snapshots[-1] if snapshots else None,
            "snapshots": snapshots,
        }
        with output_path.open("w") as handle:
            json.dump(payload, handle, indent=2)
        if not args.json:
            print(f"\nSaved watch history to {output_path}")


if __name__ == "__main__":
    main()
