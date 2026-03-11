"""
Portfolio viewer — shows all positions, cash, and account totals from IBKR.

Groups spread legs by symbol, nets cost basis properly for spreads,
and includes cash + net liquidation value.

Usage:
    uv run python get_portfolio.py
    uv run python get_portfolio.py EWY
    uv run python get_portfolio.py EWY MRVL --no-debug
"""

import argparse
from itertools import groupby

from ibkr import connect, get_portfolio, get_account_summary, Position


# ── Colors ────────────────────────────────────────────────────────────────────

RED = "\033[91m"
GREEN = "\033[92m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
WHITE = "\033[97m"


def _color_pnl(value: float, formatted: str) -> str:
    if value > 0:
        return f"{GREEN}{formatted}{RESET}"
    elif value < 0:
        return f"{RED}{formatted}{RESET}"
    return f"{DIM}{formatted}{RESET}"


def _pct_bar(pct: float, width: int = 20) -> str:
    """Render a small inline bar for gain/loss %."""
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


# ── Display ───────────────────────────────────────────────────────────────────

def print_nice_portfolio(positions: list[Position], account: dict[str, float]) -> None:
    net_liq = account.get("NetLiquidation", 0)
    cash = account.get("TotalCashBalance", 0)
    stock_mv = account.get("StockMarketValue", 0)
    option_mv = account.get("OptionMarketValue", 0)
    unrealized = account.get("UnrealizedPnL", 0)
    realized = account.get("RealizedPnL", 0)
    buying_power = account.get("BuyingPower", 0)
    margin_used = account.get("InitMarginReq", 0)

    W = 100

    # ── Account header ────────────────────────────────────────────────
    print(f"\n{BOLD}{WHITE}{'═' * W}{RESET}")
    print(f"{BOLD}{WHITE}  PORTFOLIO OVERVIEW{RESET}")
    print(f"{BOLD}{WHITE}{'═' * W}{RESET}")

    print(f"  {BOLD}Net Liquidation:{RESET}  {CYAN}${net_liq:>14,.2f}{RESET}")
    print(f"  {BOLD}Cash:{RESET}             ${cash:>14,.2f}")
    print(f"  {BOLD}Stock Value:{RESET}      ${stock_mv:>14,.2f}")
    print(f"  {BOLD}Option Value:{RESET}     ${option_mv:>14,.2f}")
    print(f"  {BOLD}Unrealized P&L:{RESET}   {_color_pnl(unrealized, f'${unrealized:>+14,.2f}')}")
    print(f"  {BOLD}Realized P&L:{RESET}     {_color_pnl(realized, f'${realized:>+14,.2f}')}")
    print(f"  {BOLD}Buying Power:{RESET}     ${buying_power:>14,.2f}")
    print(f"  {BOLD}Margin Used:{RESET}      ${margin_used:>14,.2f}")

    if not positions:
        print(f"\n  No positions.\n{'═' * W}")
        return

    # ── Positions by symbol ───────────────────────────────────────────
    print(f"\n{BOLD}{WHITE}{'═' * W}{RESET}")
    print(
        f"  {BOLD}{'Symbol':<8} {'Description':<30} {'Qty':>5} "
        f"{'Mkt Price':>10} {'Mkt Value':>12} {'P&L':>10} {'Return':>8}  {'':>20}{RESET}"
    )
    print(f"  {'─' * (W - 4)}")

    sorted_positions = sorted(positions, key=lambda p: (p.symbol, p.sec_type, p.expiry, p.strike))
    sym_rows: list[tuple[str, float, float, float, float]] = []

    for symbol, group in groupby(sorted_positions, key=lambda p: p.symbol):
        group_list = list(group)
        sym_mkt_value = sum(p.market_value for p in group_list)
        # Net cost basis: sum market_value - unrealized_pnl to get true cost paid.
        # This correctly nets spread legs.
        sym_unrealized = sum(p.unrealized_pnl for p in group_list)
        sym_net_cost = sym_mkt_value - sym_unrealized
        sym_pct = (sym_unrealized / sym_net_cost * 100) if sym_net_cost != 0 else 0.0

        sym_rows.append((symbol, sym_net_cost, sym_mkt_value, sym_unrealized, sym_pct))

        # Symbol header
        print(f"  {BOLD}{CYAN}{symbol:<8}{RESET}", end="")

        if len(group_list) == 1:
            p = group_list[0]
            desc = _describe(p)
            pnl_s = _color_pnl(p.unrealized_pnl, _fmt_money(p.unrealized_pnl))
            pct_s = _color_pnl(p.pct_return, _fmt_pct(p.pct_return))
            bar = _pct_bar(p.pct_return)
            print(
                f"{desc:<30} {p.qty:>+5d} "
                f"${p.market_price:>9.2f} "
                f"${p.market_value:>11,.2f} "
                f"{pnl_s:>20} {pct_s:>16}  {bar}"
            )
        else:
            # Multi-leg: print symbol line with subtotal, then each leg
            pnl_s = _color_pnl(sym_unrealized, _fmt_money(sym_unrealized))
            pct_s = _color_pnl(sym_pct, _fmt_pct(sym_pct))
            bar = _pct_bar(sym_pct)
            cost_label = f"net cost ${sym_net_cost:,.0f}" if sym_net_cost != 0 else ""
            print(
                f"{cost_label:<30} {'':>5} "
                f"{'':>10} "
                f"${sym_mkt_value:>11,.2f} "
                f"{pnl_s:>20} {pct_s:>16}  {bar}"
            )
            for p in group_list:
                desc = _describe(p)
                pnl_s2 = _color_pnl(p.unrealized_pnl, _fmt_money(p.unrealized_pnl))
                pct_s2 = _color_pnl(p.pct_return, _fmt_pct(p.pct_return))
                print(
                    f"  {DIM}{'':8}{desc:<30} {p.qty:>+5d} "
                    f"${p.market_price:>9.2f} "
                    f"${p.market_value:>11,.2f} "
                    f"{pnl_s2:>20} {pct_s2:>16}{RESET}"
                )

    # ── Sorted summary ────────────────────────────────────────────────
    sym_rows.sort(key=lambda r: r[3])  # sort by unrealized P&L

    print(f"\n{BOLD}{WHITE}{'═' * W}{RESET}")
    print(f"{BOLD}{WHITE}  SYMBOL RANKING  (by P&L){RESET}")
    print(f"  {'─' * (W - 4)}")
    print(
        f"  {BOLD}{'Symbol':<8} {'Net Cost':>12} {'Mkt Value':>12} "
        f"{'P&L':>10} {'Return':>8}  {'':>20}{RESET}"
    )
    print(f"  {'─' * (W - 4)}")

    for symbol, net_cost, mkt_val, unrealized_pnl, pct in sym_rows:
        pnl_s = _color_pnl(unrealized_pnl, _fmt_money(unrealized_pnl))
        pct_s = _color_pnl(pct, _fmt_pct(pct))
        bar = _pct_bar(pct)
        print(
            f"  {symbol:<8} ${net_cost:>11,.0f} ${mkt_val:>11,.2f} "
            f"{pnl_s:>20} {pct_s:>16}  {bar}"
        )

    print(f"{BOLD}{WHITE}{'═' * W}{RESET}\n")


def _describe(p: Position) -> str:
    if p.sec_type == "STK":
        return "stock"
    dte_str = f" ({p.dte}d)" if p.dte is not None else ""
    return f"{p.strike:.0f}{p.right} {p.expiry}{dte_str}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="IBKR portfolio viewer")
    parser.add_argument("symbols", nargs="*", help="Optional symbol filters.")
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Print detailed IBKR connection diagnostics.",
    )
    args = parser.parse_args()

    symbols = [s.upper() for s in args.symbols] or None

    with connect(client_id=11, debug=args.debug) as ib:
        positions = get_portfolio(ib, symbols=symbols)

        # Fetch key account metrics
        acct_tags = {
            "NetLiquidation", "TotalCashBalance", "TotalCashValue",
            "StockMarketValue", "OptionMarketValue",
            "UnrealizedPnL", "RealizedPnL",
            "BuyingPower", "InitMarginReq",
            "GrossPositionValue",
        }
        metrics = get_account_summary(ib, tags=acct_tags, currencies={"USD"})
        account = {}
        for m in metrics:
            try:
                account[m.tag] = float(m.value)
            except ValueError:
                pass

        print_nice_portfolio(positions, account)


if __name__ == "__main__":
    main()
