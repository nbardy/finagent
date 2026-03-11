import json
import math
import os
from datetime import date
from ib_insync import *

def main():
    ib = IB()
    # Connect to IBKR Gateway by default (4001 live / 4002 paper).
    ib.connect('127.0.0.1', 4001, clientId=1)

    underlying = Stock('EWY', 'SMART', 'USD')
    ib.qualifyContracts(underlying)
    
    # 1. Get current underlying price
    [ticker] = ib.reqTickers(underlying)
    current_price = ticker.marketPrice()
    print(f"EWY Current Price: {current_price}")

    # 2. Get the options chain
    chains = ib.reqSecDefOptParams(underlying.symbol, '', underlying.secType, underlying.conId)
    chain = next(c for c in chains if c.exchange == 'SMART')

    # Find the closest weekly expiry (e.g., 5 to 10 days out)
    expirations = sorted(exp for exp in chain.expirations)
    target_expiry = expirations[1] # Naively grabbing the next available expiry

    # Filter for OTM Calls
    strikes = [s for s in chain.strikes if s > current_price]
    contracts = [Option('EWY', target_expiry, strike, 'C', 'SMART') for strike in strikes]
    contracts = ib.qualifyContracts(*contracts)

    # 3. Poll Market Data, IV, and Greeks
    tickers = ib.reqTickers(*contracts)
    
    proposals = []
    for t in tickers:
        if not t.modelGreeks:
            continue
            
        iv = t.modelGreeks.impliedVol
        delta = t.modelGreeks.delta
        bid = t.bid
        ask = t.ask
        
        # Simple Model: Delta is roughly the probability of expiring ITM.
        prob_itm = delta if delta else 0
        prob_otm = 1 - prob_itm
        
        # Calculate Expected Value (EV) of the credit received
        mid_price = (bid + ask) / 2
        ev = (mid_price * prob_otm) - (current_price * 0.05 * prob_itm) # Rough penalty assumption
        
        proposals.append({
            "symbol": "EWY",
            "conId": t.contract.conId,
            "strike": t.contract.strike,
            "expiry": t.contract.lastTradeDateOrContractMonth,
            "iv": iv,
            "delta": delta,
            "prob_of_profit": prob_otm,
            "bid": bid,
            "ask": ask,
            "mid_price": mid_price,
            "ev": ev
        })

    # 4. Select the best trade (e.g., Highest EV where Prob of Profit > 85%)
    valid_trades = [p for p in proposals if p['prob_of_profit'] > 0.85 and p['bid'] > 0.05]
    
    if not valid_trades:
        print("No trades meet the risk criteria.")
        ib.disconnect()
        return

    best_trade = sorted(valid_trades, key=lambda x: x['ev'], reverse=True)[0]
    
    # 5. Generate JSON Proposal
    order_proposal = {
        "action": "SELL",
        "quantity": 2, # Assuming you have 2 LEAPS
        "contract": {
            "symbol": best_trade['symbol'],
            "secType": "OPT",
            "exchange": "SMART",
            "currency": "USD",
            "lastTradeDateOrContractMonth": best_trade['expiry'],
            "strike": best_trade['strike'],
            "right": "C"
        },
        "order": {
            "orderType": "LMT",
            "lmtPrice": round(best_trade['mid_price'], 2),
            "tif": "DAY"
        },
        "metrics": best_trade
    }

    out_dir = f"orders/{date.today()}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/trade_proposal.json"
    with open(out_path, 'w') as f:
        json.dump(order_proposal, f, indent=4)

    print(f"Proposed Trade saved to {out_path}")
    print(f"Strike: {best_trade['strike']} | Credit: ${round(best_trade['mid_price'] * 100, 2)} | POP: {round(best_trade['prob_of_profit']*100, 1)}%")

    ib.disconnect()

if __name__ == "__main__":
    main()
