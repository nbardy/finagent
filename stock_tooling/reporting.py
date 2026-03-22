"""
Shared console reporting helpers for stock tooling CLIs.

`ibkr.py` is the broker/data layer. Console rendering lives here so execution
and portfolio tools can share text views without pulling presentation helpers
into the broker utility module.
"""

from __future__ import annotations

from ibkr import AccountMetric, FillEvent, OpenOrder, Position


def format_contract_label(
    symbol: str,
    sec_type: str,
    expiry: str = "",
    strike: float = 0.0,
    right: str = "",
    *,
    strike_digits: int = 1,
) -> str:
    """Return a single-line contract label suitable for console output."""
    if sec_type == "STK":
        return symbol
    return f"{symbol} {expiry} {strike:.{strike_digits}f}{right}".strip()


def describe_position(position: Position) -> str:
    """Return a compact position description without the symbol."""
    if position.sec_type == "STK":
        return "stock"
    dte_str = f" ({position.dte}d)" if position.dte is not None else ""
    return f"{position.strike:.0f}{position.right} {position.expiry}{dte_str}"


def describe_order(order: OpenOrder) -> str:
    """Return a compact order description without the symbol."""
    if order.sec_type == "STK":
        return "stock"
    return f"{order.strike:.0f}{order.right} {order.expiry}"


def describe_fill(fill: FillEvent) -> str:
    """Return a compact fill description without the symbol."""
    if fill.sec_type == "STK":
        return "stock"
    return f"{fill.strike:.0f}{fill.right} {fill.expiry}"


def format_position_market_price(position: Position) -> str:
    """Return a market-price string with local-currency context when applicable."""
    mkt_str = f"${position.base_market_price:.2f}" if position.base_market_price else "N/A"
    if getattr(position, "currency", "USD") != "USD":
        mkt_str += f" ({position.local_market_price:.2f} {position.currency})"
    return mkt_str


def format_position_avg_cost(position: Position) -> str:
    """Return an average-cost string with local-currency context when applicable."""
    avg_str = f"${position.base_avg_cost:.2f}"
    if getattr(position, "currency", "USD") != "USD":
        avg_str += f" ({position.local_avg_cost:.2f} {position.currency})"
    return avg_str


def print_portfolio(positions: list[Position]) -> None:
    """Pretty-print a list of positions with P&L."""
    total_market_value = sum(p.base_market_value for p in positions)
    total_cost = sum(p.base_cost_basis for p in positions)
    total_unrealized = sum(p.base_unrealized_pnl for p in positions)
    total_pct = (total_unrealized / total_cost * 100) if total_cost > 0 else 0.0

    print(f"\n{'='*95}")
    print(f"  PORTFOLIO — {len(positions)} positions")
    print(f"{'='*95}")

    current_sym = None
    sym_pnl = 0.0
    sym_cost = 0.0

    def print_sym_subtotal() -> None:
        if current_sym and sym_cost > 0:
            sym_pct = sym_pnl / sym_cost * 100
            print(f"  {'':>8}  subtotal: ${sym_pnl:+,.0f}  ({sym_pct:+.1f}%)  cost=${sym_cost:,.0f}")

    for pos in positions:
        if pos.symbol != current_sym:
            print_sym_subtotal()
            current_sym = pos.symbol
            sym_pnl = 0.0
            sym_cost = 0.0
            print(f"\n  {current_sym}")
            print(f"  {'─'*85}")

        sym_pnl += pos.base_unrealized_pnl
        sym_cost += pos.base_cost_basis
        pnl_str = f"${pos.base_unrealized_pnl:+,.0f}"
        pct_str = f"{pos.pct_return:+.1f}%"
        mkt_str = format_position_market_price(pos)

        if pos.sec_type == "STK":
            print(
                f"    STOCK  {pos.qty:+d} shares  "
                f"avg={format_position_avg_cost(pos)}  mkt={mkt_str}  "
                f"P&L={pnl_str} ({pct_str})"
            )
        else:
            dte_str = f"DTE={pos.dte}" if pos.dte is not None else ""
            print(
                f"    {pos.strike:>8.1f}{pos.right}  "
                f"{pos.expiry}  {pos.qty:+4d}  "
                f"avg=${pos.base_avg_cost:.2f}  mkt={mkt_str}  "
                f"P&L={pnl_str} ({pct_str})  {dte_str}"
            )

    print_sym_subtotal()

    print(f"\n{'='*95}")
    print(f"  Cost Basis:     ${total_cost:>14,.2f}")
    print(f"  Market Value:   ${total_market_value:>14,.2f}")
    print(f"  Unrealized P&L: ${total_unrealized:>+14,.2f}  ({total_pct:+.1f}%)")
    print(f"{'='*95}")


def print_open_orders(orders: list[OpenOrder]) -> None:
    """Pretty-print current open orders."""
    print(f"\n{'='*95}")
    print(f"  OPEN ORDERS — {len(orders)}")
    print(f"{'='*95}")

    if not orders:
        print("  none")
        print(f"{'='*95}")
        return

    for order in orders:
        contract_label = format_contract_label(
            order.symbol,
            order.sec_type,
            order.expiry,
            order.strike,
            order.right,
        )
        limit_str = f"${order.limit_price:.2f}" if order.limit_price else "MKT"
        print(
            f"  id={order.order_id:<4d} {contract_label:<28}"
            f" {order.action:<4} {order.quantity:>4d}"
            f" {order.order_type:<3} {limit_str:<8}"
            f" tif={order.tif:<3} status={order.status:<12}"
            f" filled={order.filled:g} remaining={order.remaining:g}"
        )

    print(f"{'='*95}")


def print_account_summary(metrics: list[AccountMetric]) -> None:
    """Pretty-print selected account summary metrics."""
    print(f"\n{'='*95}")
    print(f"  ACCOUNT SUMMARY — {len(metrics)} metrics")
    print(f"{'='*95}")

    if not metrics:
        print("  none")
        print(f"{'='*95}")
        return

    for metric in metrics:
        print(f"  {metric.tag:<20} {metric.value:>16} {metric.currency}")

    print(f"{'='*95}")


def print_recent_fills(fills: list[FillEvent]) -> None:
    """Pretty-print execution fills."""
    print(f"\n{'='*95}")
    print(f"  FILLS — {len(fills)}")
    print(f"{'='*95}")

    if not fills:
        print("  none")
        print(f"{'='*95}")
        return

    for fill in fills:
        contract_label = format_contract_label(
            fill.symbol,
            fill.sec_type,
            fill.expiry,
            fill.strike,
            fill.right,
        )
        pnl_str = f" pnl={fill.realized_pnl:+,.2f}" if fill.realized_pnl else ""
        comm_str = f" comm={fill.commission:.2f}" if fill.commission else ""
        print(
            f"  orderId={fill.order_id:<4d} {contract_label:<28}"
            f" side={fill.side:<3} shares={fill.shares:g}"
            f" price=${fill.price:.2f}{pnl_str}{comm_str}"
            f" time={fill.time}"
        )

    print(f"{'='*95}")
