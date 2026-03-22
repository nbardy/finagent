"""
Manage active IBKR orders: view and cancel.

Usage:
    uv run python stock_tooling/manage_orders.py --list
    uv run python stock_tooling/manage_orders.py --cancel <order_id>
    uv run python stock_tooling/manage_orders.py --cancel-all <symbol>
"""

import argparse
from ib_insync import IB
from ibkr import connect

def get_all_orders():
    # We can fetch all open orders across clients using a generic client ID
    with connect() as ib:
        return ib.reqAllOpenOrders()

def cancel_order(order_id: int):
    # First find the order to know which clientId placed it
    orders = get_all_orders()
    target_order = next((o for o in orders if o.order.orderId == order_id), None)
    
    if not target_order:
        print(f"Error: Order {order_id} not found among open orders.")
        return
        
    client_id = target_order.order.clientId
    print(f"Order {order_id} was placed by clientId {client_id}. Reconnecting to cancel...")
    
    # Now connect with that specific clientId to cancel it
    ib = IB()
    try:
        # Default connection params matching ibkr.py
        ib.connect('127.0.0.1', 4001, clientId=client_id)
        # We need to fetch open orders again for this specific client to get the live Order object
        client_orders = ib.openOrders()
        client_target = next((o for o in client_orders if o.orderId == order_id), None)
        
        if client_target:
            ib.cancelOrder(client_target)
            ib.sleep(1)
            print(f"Successfully sent cancel request for Order {order_id} ({target_order.contract.symbol})")
        else:
            print("Could not find order when connected with specific clientId.")
            
    finally:
        if ib.isConnected():
            ib.disconnect()

def cancel_all_for_symbol(symbol: str):
    orders = get_all_orders()
    target_orders = [o for o in orders if o.contract.symbol == symbol]
    
    if not target_orders:
        print(f"No open orders found for symbol: {symbol}")
        return
        
    # Group by client ID to minimize reconnections
    orders_by_client = {}
    for o in target_orders:
        cid = o.order.clientId
        if cid not in orders_by_client:
            orders_by_client[cid] = []
        orders_by_client[cid].append(o.order.orderId)
        
    for cid, order_ids in orders_by_client.items():
        print(f"Connecting as clientId {cid} to cancel {len(order_ids)} orders...")
        ib = IB()
        try:
            ib.connect('127.0.0.1', 4001, clientId=cid)
            client_orders = ib.openOrders()
            for oid in order_ids:
                co = next((o for o in client_orders if o.orderId == oid), None)
                if co:
                    ib.cancelOrder(co)
                    print(f"  -> Cancelled Order {oid}")
            ib.sleep(1)
        finally:
            if ib.isConnected():
                ib.disconnect()
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
            print(f"Order {o.order.orderId} [Client: {o.order.clientId}]: {o.order.action} {o.order.totalQuantity} {o.contract.symbol} {o.contract.secType} @ {o.order.lmtPrice}")
    elif args.cancel:
        cancel_order(args.cancel)
    elif args.cancel_all:
        cancel_all_for_symbol(args.cancel_all.upper())
    else:
        parser.print_help()

if __name__ == "__main__":
    main()