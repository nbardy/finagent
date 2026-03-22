"""
Manage active IBKR orders: view and cancel.

Usage:
    uv run python stock_tooling/manage_orders.py --list
    uv run python stock_tooling/manage_orders.py --cancel <order_id>
    uv run python stock_tooling/manage_orders.py --cancel-all <symbol>
"""

import argparse
from ibkr import cancel_open_orders, connect, get_open_orders

def get_all_orders():
    with connect() as ib:
        return get_open_orders(ib)

def cancel_order(order_id: int):
    matched = cancel_open_orders(order_ids={order_id})
    if not matched:
        print(f"Error: Order {order_id} not found among open orders.")
        return
    order = matched[0]
    print(
        f"Successfully sent cancel request for Order {order.order_id} "
        f"({order.symbol}) via clientId {order.client_id}"
    )

def cancel_all_for_symbol(symbol: str):
    matched = cancel_open_orders(symbols={symbol})
    if not matched:
        print(f"No open orders found for symbol: {symbol}")
        return
    for order in matched:
        print(
            f"  -> Cancel requested for Order {order.order_id} "
            f"({order.symbol}) via clientId {order.client_id}"
        )
    print("Done.")

def main():
    parser = argparse.ArgumentParser(description="Manage IBKR orders.")
    parser.add_argument("--list", action="store_true", help="List all open orders")
    parser.add_argument("--cancel", type=int, help="Cancel specific order ID")
    parser.add_argument("--cancel-all", type=str, help="Cancel all orders for a symbol")
    
    args = parser.parse_args()
    
    if args.list:
        orders = get_all_orders()
        for o in orders:
            print(
                f"Order {o.order_id} [Client: {o.client_id}]: "
                f"{o.action} {o.quantity} {o.symbol} {o.sec_type} @ {o.limit_price}"
            )
    elif args.cancel:
        cancel_order(args.cancel)
    elif args.cancel_all:
        cancel_all_for_symbol(args.cancel_all.upper())
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
