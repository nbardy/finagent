import json
from ibkr import connect, get_open_orders, get_portfolio

def main():
    with open('config/pmcc_config.json', 'r') as f:
        config = json.load(f)
        
    conn_cfg = config.get('connection', {})
    client_id = conn_cfg.get('client_id_portfolio', 4)
    market_data_type = conn_cfg.get('market_data_type', 1)
    
    strat_cfg = config.get('strategy', {})
    target_symbol = strat_cfg.get('underlyings', ['EWY'])[0]
    min_long_dte_for_cover = int(strat_cfg.get('min_long_dte_for_cover', 180))

    try:
        with connect(client_id=client_id, market_data_type=market_data_type, readonly=True) as ib:
            print("Connected to IBKR for Portfolio Sync.")
            
            positions = get_portfolio(ib, symbols=[target_symbol])
            open_orders = get_open_orders(ib, symbols=[target_symbol])
        
            # We will collect all Long LEAPs here
            long_leaps = []
            short_calls_qty = 0
            
            for pos in positions:
                if pos.sec_type != 'OPT' or pos.right != 'C':
                    continue

                if pos.qty > 0 and (pos.dte or 0) >= min_long_dte_for_cover:
                    long_leaps.append({
                        "strike": float(pos.strike),
                        "expiry": pos.expiry,
                        "qty": int(pos.qty),
                        "avg_cost": pos.avg_cost / 100.0,
                    })
                elif pos.qty < 0:
                    short_calls_qty += abs(int(pos.qty))
                        
            pending_short_qty = sum(
                int(order.remaining)
                for order in open_orders
                if order.sec_type == 'OPT'
                and order.right == 'C'
                and order.action == 'SELL'
                and order.remaining > 0
            )
                        
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
            
            with open('config/portfolio_state.json', 'w') as f:
                json.dump(state, f, indent=4)

            print("Portfolio state saved to config/portfolio_state.json")
        
    except Exception as e:
        print(f"Error syncing portfolio: {e}")

if __name__ == "__main__":
    main()
