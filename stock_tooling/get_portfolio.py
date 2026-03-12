"""
Portfolio viewer — shows positions, open orders, recent fills, and account totals from IBKR.

It enriches broker truth with the local thesis registry so current holdings and
working orders always show the saved rationale by default.

Usage:
    uv run python get_portfolio.py
    uv run python get_portfolio.py EWY
    uv run python get_portfolio.py EWY MRVL --no-debug
"""

from __future__ import annotations

import argparse
from itertools import groupby

from helpers.thesis_db import find_thesis_for_order, find_thesis_for_position
from ibkr import (
    FillEvent,
    OpenOrder,
    Position,
    connect,
    get_account_summary,
    get_open_orders,
    get_portfolio,
    get_recent_fills,
)


RED = "\033[91m"
GREEN = "\033[92m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
CYAN = "\033[96m"
WHITE = "\033[97m"


def _color_pnl(value: float, formatted: str) -> str:
    if value > 0:
        return f"{GREEN}{formatted}{RESET}"
    if value < 0:
        return f"{RED}{formatted}{RESET}"
    return f"{DIM}{formatted}{RESET}"


def _pct_bar(pct: float, width: int = 20) -> str:
    clamped = max(-100, min(100, pct))
    mid = width // 2
    fill = int(abs(clamped) / 100 * mid)
    if clamped >= 0:
        bar = " " * mid + "█" * fill + " " * (mid - fill)
    else:
        bar = " " * (mid - fill) + "█" * fill + " " * mid
    color = GREEN if clamped >= 0 else RED
    return f"{DIM}│{RESET}{color}{bar}{RESET}{DIM}│{RESET}"


def _fmt_money(v: float) -> str:
    return f"${v:>+,.0f}" if v != 0 else "$0"


def _fmt_pct(v: float) -> str:
    return f"{v:+.1f}%"


def _describe_position(position: Position) -> str:
    if position.sec_type == "STK":
        return "stock"
    dte_str = f" ({position.dte}d)" if position.dte is not None else ""
    return f"{position.strike:.0f}{position.right} {position.expiry}{dte_str}"


def _describe_order(order: OpenOrder) -> str:
    if order.sec_type == "STK":
        return "stock"
    return f"{order.strike:.0f}{order.right} {order.expiry}"


def _describe_fill(fill: FillEvent) -> str:
    if fill.sec_type == "STK":
        return "stock"
    return f"{fill.strike:.0f}{fill.right} {fill.expiry}"


def _thesis_summary(thesis: dict | None) -> str:
    if not thesis:
        return "n/a"
    reason = thesis["reason"]
    return reason if len(reason) <= 88 else reason[:85] + "..."


def print_account_header(account: dict[str, float]) -> None:
    net_liq = account.get("NetLiquidation", 0)
    cash = account.get("TotalCashBalance", 0)
    stock_mv = account.get("StockMarketValue", 0)
    option_mv = account.get("OptionMarketValue", 0)
    unrealized = account.get("UnrealizedPnL", 0)
    realized = account.get("RealizedPnL", 0)
    buying_power = account.get("BuyingPower", 0)
    margin_used = account.get("InitMarginReq", 0)
    width = 132

    print(f"\n{BOLD}{WHITE}{'═' * width}{RESET}")
    print(f"{BOLD}{WHITE}  PORTFOLIO OVERVIEW{RESET}")
    print(f"{BOLD}{WHITE}{'═' * width}{RESET}")
    print(f"  {BOLD}Net Liquidation:{RESET}  {CYAN}${net_liq:>14,.2f}{RESET}")
    print(f"  {BOLD}Cash:{RESET}             ${cash:>14,.2f}")
    print(f"  {BOLD}Stock Value:{RESET}      ${stock_mv:>14,.2f}")
    print(f"  {BOLD}Option Value:{RESET}     ${option_mv:>14,.2f}")
    print(f"  {BOLD}Unrealized P&L:{RESET}   {_color_pnl(unrealized, f'${unrealized:>+14,.2f}')}")
    print(f"  {BOLD}Realized P&L:{RESET}     {_color_pnl(realized, f'${realized:>+14,.2f}')}")
    print(f"  {BOLD}Buying Power:{RESET}     ${buying_power:>14,.2f}")
    print(f"  {BOLD}Margin Used:{RESET}      ${margin_used:>14,.2f}")


def print_positions(positions: list[Position]) -> None:
    width = 132
    print(f"\n{BOLD}{WHITE}{'═' * width}{RESET}")
    print(f"{BOLD}{WHITE}  POSITIONS{RESET}")
    print(f"  {'─' * (width - 4)}")
    print(
        f"  {BOLD}{'Symbol':<8} {'Description':<28} {'Qty':>5} {'Mkt Price':>10} "
        f"{'Mkt Value':>12} {'P&L':>10} {'Return':>8} {'Thesis ID':<28} {'Reason':<0}{RESET}"
    )
    print(f"  {'─' * (width - 4)}")

    if not positions:
        print("  No positions.")
        return

    sorted_positions = sorted(positions, key=lambda p: (p.symbol, p.sec_type, p.expiry, p.strike))
    for symbol, group in groupby(sorted_positions, key=lambda p: p.symbol):
        for index, position in enumerate(group):
            thesis = find_thesis_for_position(
                symbol=position.symbol,
                sec_type=position.sec_type,
                expiry=position.expiry,
                strike=position.strike,
                right=position.right,
            )
            pnl_s = _color_pnl(position.unrealized_pnl, _fmt_money(position.unrealized_pnl))
            pct_s = _color_pnl(position.pct_return, _fmt_pct(position.pct_return))
            symbol_label = f"{BOLD}{CYAN}{symbol:<8}{RESET}" if index == 0 else f"{DIM}{'':8}{RESET}"
            print(
                f"  {symbol_label}"
                f"{_describe_position(position):<28} {position.qty:>+5d} "
                f"${position.market_price:>9.2f} "
                f"${position.market_value:>11,.2f} "
                f"{pnl_s:>20} {pct_s:>16} "
                f"{(thesis['thesis_id'] if thesis else 'n/a'):<28} "
                f"{_thesis_summary(thesis)}"
            )


def print_open_orders(orders: list[OpenOrder]) -> None:
    width = 132
    print(f"\n{BOLD}{WHITE}{'═' * width}{RESET}")
    print(f"{BOLD}{WHITE}  OPEN ORDERS{RESET}")
    print(f"  {'─' * (width - 4)}")
    print(
        f"  {BOLD}{'Symbol':<8} {'Description':<22} {'Side':<6} {'Qty':>5} "
        f"{'Limit':>8} {'Status':<14} {'OrderRef':<24} {'Thesis ID':<28} {'Reason':<0}{RESET}"
    )
    print(f"  {'─' * (width - 4)}")

    if not orders:
        print("  No open orders.")
        return

    for order in orders:
        thesis = find_thesis_for_order(
            perm_id=order.perm_id,
            order_ref=order.order_ref,
            symbol=order.symbol,
            sec_type=order.sec_type,
            expiry=order.expiry,
            strike=order.strike,
            right=order.right,
        )
        print(
            f"  {order.symbol:<8} {_describe_order(order):<22} {order.action:<6} "
            f"{order.quantity:>5d} {order.limit_price:>8.2f} {order.status:<14} "
            f"{(order.order_ref or 'n/a'):<24} "
            f"{(thesis['thesis_id'] if thesis else 'n/a'):<28} "
            f"{_thesis_summary(thesis)}"
        )


def print_recent_fills(fills: list[FillEvent]) -> None:
    width = 132
    print(f"\n{BOLD}{WHITE}{'═' * width}{RESET}")
    print(f"{BOLD}{WHITE}  RECENT FILLS{RESET}")
    print(f"  {'─' * (width - 4)}")
    print(
        f"  {BOLD}{'Time':<20} {'Symbol':<8} {'Description':<20} {'Side':<6} {'Qty':>6} "
        f"{'Price':>8} {'OrderRef':<24} {'Thesis ID':<28} {'Reason':<0}{RESET}"
    )
    print(f"  {'─' * (width - 4)}")

    if not fills:
        print("  No recent fills.")
        return

    for fill in fills:
        thesis = find_thesis_for_order(
            perm_id=fill.perm_id,
            order_ref=fill.order_ref,
            symbol=fill.symbol,
            sec_type=fill.sec_type,
            expiry=fill.expiry,
            strike=fill.strike,
            right=fill.right,
        )
        print(
            f"  {fill.time:<20} {fill.symbol:<8} {_describe_fill(fill):<20} "
            f"{fill.side:<6} {int(fill.shares):>6d} {fill.price:>8.2f} "
            f"{(fill.order_ref or 'n/a'):<24} "
            f"{(thesis['thesis_id'] if thesis else 'n/a'):<28} "
            f"{_thesis_summary(thesis)}"
        )


def print_symbol_ranking(positions: list[Position]) -> None:
    width = 132
    rows: list[tuple[str, float, float, float, float]] = []
    for symbol, group in groupby(sorted(positions, key=lambda p: p.symbol), key=lambda p: p.symbol):
        group_list = list(group)
        market_value = sum(position.market_value for position in group_list)
        unrealized = sum(position.unrealized_pnl for position in group_list)
        net_cost = market_value - unrealized
        pct = (unrealized / net_cost * 100.0) if net_cost != 0 else 0.0
        rows.append((symbol, net_cost, market_value, unrealized, pct))

    rows.sort(key=lambda row: row[3])
    print(f"\n{BOLD}{WHITE}{'═' * width}{RESET}")
    print(f"{BOLD}{WHITE}  SYMBOL RANKING (by P&L){RESET}")
    print(f"  {'─' * (width - 4)}")
    print(
        f"  {BOLD}{'Symbol':<8} {'Net Cost':>12} {'Mkt Value':>12} "
        f"{'P&L':>10} {'Return':>8}  {'':>20}{RESET}"
    )
    print(f"  {'─' * (width - 4)}")
    for symbol, net_cost, market_value, unrealized, pct in rows:
        pnl_s = _color_pnl(unrealized, _fmt_money(unrealized))
        pct_s = _color_pnl(pct, _fmt_pct(pct))
        bar = _pct_bar(pct)
        print(
            f"  {symbol:<8} ${net_cost:>11,.0f} ${market_value:>11,.2f} "
            f"{pnl_s:>20} {pct_s:>16}  {bar}"
        )
    print(f"{BOLD}{WHITE}{'═' * width}{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="IBKR portfolio viewer with thesis enrichment")
    parser.add_argument("symbols", nargs="*", help="Optional symbol filters.")
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Print detailed IBKR connection diagnostics.",
    )
    args = parser.parse_args()

    symbols = [symbol.upper() for symbol in args.symbols] or None

    with connect(client_id=11, debug=args.debug) as ib:
        positions = get_portfolio(ib, symbols=symbols)
        open_orders = get_open_orders(ib, symbols=symbols)
        recent_fills = get_recent_fills(ib, symbols=symbols)

        account_tags = {
            "NetLiquidation",
            "TotalCashBalance",
            "TotalCashValue",
            "StockMarketValue",
            "OptionMarketValue",
            "UnrealizedPnL",
            "RealizedPnL",
            "BuyingPower",
            "InitMarginReq",
            "GrossPositionValue",
        }
        metrics = get_account_summary(ib, tags=account_tags, currencies={"USD"})
        account: dict[str, float] = {}
        for metric in metrics:
            try:
                account[metric.tag] = float(metric.value)
            except ValueError:
                continue

    print_account_header(account)
    print_positions(positions)
    print_open_orders(open_orders)
    print_recent_fills(recent_fills)
    if positions:
        print_symbol_ranking(positions)


if __name__ == "__main__":
    main()
