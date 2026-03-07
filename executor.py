import json
import argparse
from ib_insync import *

def execute_trade(file_path):
    with open('pmcc_config.json', 'r') as f:
        config = json.load(f)
        
    conn_cfg = config.get('connection', {})
    host = conn_cfg.get('host', '127.0.0.1')
    port = conn_cfg.get('port', 7497)
    client_id = conn_cfg.get('client_id_executor', 2)

    with open(file_path, 'r') as f:
        data = json.load(f)

    if isinstance(data, dict) and 'trades' in data:
        proposals = data['trades']
    elif isinstance(data, list):
        proposals = data
    else:
        proposals = [data]

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id) 
        
        for proposal in proposals:
            # Reconstruct contract
            c_data = proposal['contract']
            contract = Option(
                c_data['symbol'], 
                c_data['lastTradeDateOrContractMonth'], 
                c_data['strike'], 
                c_data['right'], 
                c_data['exchange'], 
                currency=c_data['currency']
            )
            ib.qualifyContracts(contract)
            
            action = proposal['action']
            
            if 'tranches' in proposal:
                print(f"Executing tranched order for {contract.symbol} {contract.strike}{contract.right}")
                for i, t_data in enumerate(proposal['tranches']):
                    qty = t_data['quantity']
                    lmt_price = t_data['lmtPrice']
                    
                    order = LimitOrder(action, qty, lmt_price)
                    
                    print(f" Tranche {i+1}: {action} {qty} @ {lmt_price}")
                    
                    trade = ib.placeOrder(contract, order)
                    ib.sleep(2) # Give it a moment to transmit
                    print(f"  Status: {trade.orderStatus.status}")
            else:
                qty = proposal.get('quantity', 1)
                order_type = proposal.get('order_type', 'MKT')
                if order_type == 'MKT':
                    order = MarketOrder(action, qty)
                    print(f"Executing {order_type} order for {contract.symbol} {contract.strike}{contract.right}: {action} {qty}")
                    trade = ib.placeOrder(contract, order)
                    ib.sleep(2)
                    print(f"  Status: {trade.orderStatus.status}")
                elif order_type == 'LMT' and 'lmtPrice' in proposal:
                    lmt_price = proposal['lmtPrice']
                    order = LimitOrder(action, qty, lmt_price)
                    print(f"Executing {order_type} order for {contract.symbol} {contract.strike}{contract.right}: {action} {qty} @ {lmt_price}")
                    trade = ib.placeOrder(contract, order)
                    ib.sleep(2)
                    print(f"  Status: {trade.orderStatus.status}")
                else:
                    print(f"Unsupported order type or missing parameters in proposal for {contract.symbol}")

    except Exception as e:
        print(f"Execution Error: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Path to the JSON proposal", default="trade_proposal.json")
    args = parser.parse_args()
    execute_trade(args.file)
