import json
from datetime import datetime
from ib_insync import *

def main():
    with open('pmcc_config.json', 'r') as f:
        config = json.load(f)
        
    conn_cfg = config.get('connection', {})
    host = conn_cfg.get('host', '127.0.0.1')
    port = conn_cfg.get('port', 7497)
    client_id = conn_cfg.get('client_id_portfolio', 4)
    
    strat_cfg = config.get('strategy', {})
    target_symbol = strat_cfg.get('underlyings', ['EWY'])[0]

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id)
        print("Connected to IBKR for Portfolio Sync.")
        
        positions = ib.positions()
        
        # We will collect all Long LEAPs here
        long_leaps = []
        short_calls_qty = 0
        
        today = datetime.now()
        
        for pos in positions:
            contract = pos.contract
            if contract.symbol == target_symbol and contract.secType == 'OPT' and contract.right == 'C':
                expiry_str = contract.lastTradeDateOrContractMonth
                try:
                    expiry_date = datetime.strptime(expiry_str, '%Y%m%d')
                    dte = (expiry_date - today).days
                except ValueError:
                    dte = 0
                    
                qty = pos.position
                
                if qty > 0 and dte > 365:
                    avg_cost_leaps = pos.avgCost / float(contract.multiplier or 100)
                    long_leaps.append({
                        "strike": float(contract.strike),
                        "expiry": expiry_str,
                        "qty": int(qty),
                        "avg_cost": avg_cost_leaps
                    })
                elif qty < 0:
                    short_calls_qty += abs(int(qty))
                    
        # Check for pending limit orders to prevent double filing
        trades = ib.reqOpenOrders()
        pending_short_qty = 0
        
        for trade in trades:
            # trade is an Order object, we need the contract
            # ib.reqOpenOrders() actually returns Order objects, but we can also use ib.openTrades() to get Trade objects containing contract and order.
            pass
            
        # Let's use ib.openTrades() which is easier
        open_trades = ib.openTrades()
        for t in open_trades:
            if t.contract.symbol == target_symbol and t.contract.secType == 'OPT' and t.contract.right == 'C':
                if t.order.action == 'SELL':
                    # Add remaining quantity of the pending order
                    pending_short_qty += int(t.order.totalQuantity - t.order.filledQuantity)
                    
        total_encumbrance = short_calls_qty + pending_short_qty
        
        print(f"Target Symbol: {target_symbol}")
        print(f"Total Existing Short Calls: {short_calls_qty}")
        print(f"Total Pending Short Sell Orders: {pending_short_qty}")
        print(f"Total Encumbrance: {total_encumbrance}")
        
        # Sort LEAPs by strike ascending (use lowest strikes to cover first)
        long_leaps.sort(key=lambda x: x["strike"])
        
        unencumbered_leaps = []
        remaining_encumbrance = total_encumbrance
        
        for leap in long_leaps:
            if remaining_encumbrance >= leap["qty"]:
                remaining_encumbrance -= leap["qty"]
                leap["qty_available"] = 0
            else:
                qty_available = leap["qty"] - remaining_encumbrance
                remaining_encumbrance = 0
                leap["qty_available"] = qty_available
                if qty_available > 0:
                    unencumbered_leaps.append(leap)
                    
        total_unencumbered = sum(l["qty_available"] for l in unencumbered_leaps)
        
        print(f"Unencumbered Inventory: {total_unencumbered}")
        for l in unencumbered_leaps:
            print(f"  - Strike {l['strike']} ({l['expiry']}): {l['qty_available']} available (Avg Cost: ${l['avg_cost']:.2f})")
        
        state = {
            "symbol": target_symbol,
            "total_unencumbered_inventory": total_unencumbered,
            "unencumbered_leaps": unencumbered_leaps,
            "total_encumbrance": total_encumbrance
        }
        
        with open('portfolio_state.json', 'w') as f:
            json.dump(state, f, indent=4)
            
        print("Portfolio state saved to portfolio_state.json")
        
    except Exception as e:
        print(f"Error syncing portfolio: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    main()
