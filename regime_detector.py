import json
import numpy as np
import pandas as pd
from ib_insync import *

def get_realized_volatility(ib, contract, days=30):
    """Calculate 30-day realized volatility based on daily closes."""
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr=f'{days} D',
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )
    if not bars:
        return None
        
    df = util.df(bars)
    # Calculate daily returns
    df['returns'] = np.log(df['close'] / df['close'].shift(1))
    
    # Calculate annualized realized volatility (RV)
    rv = df['returns'].std() * np.sqrt(252)
    return rv

def get_vix_term_structure(ib):
    """Check VIX term structure for backwardation (short term > long term)."""
    vix_index = Index('VIX', 'CBOE')
    ib.qualifyContracts(vix_index)
    
    # For a robust check, we'd look at VIX futures (VX), but for simplicity in this proxy:
    # We can fetch VIX3M (3-month VIX) vs VIX to check the spread.
    vix3m_index = Index('VIX3M', 'CBOE')
    ib.qualifyContracts(vix3m_index)
    
    [vix_ticker, vix3m_ticker] = ib.reqTickers(vix_index, vix3m_index)
    
    vix_price = vix_ticker.marketPrice()
    vix3m_price = vix3m_ticker.marketPrice()
    
    # If VIX is higher than 3M VIX, the market is in backwardation (panic)
    backwardation = False
    if vix_price and vix3m_price and not np.isnan(vix_price) and not np.isnan(vix3m_price):
        backwardation = vix_price > vix3m_price
        
    return vix_price, vix3m_price, backwardation

def main():
    with open('pmcc_config.json', 'r') as f:
        config = json.load(f)

    conn_cfg = config.get('connection', {})
    host = conn_cfg.get('host', '127.0.0.1')
    port = conn_cfg.get('port', 7497)
    client_id = conn_cfg.get('client_id_regime', 3)
    market_data_type = conn_cfg.get('market_data_type', 1)

    strat_cfg = config.get('strategy', {})
    symbol = strat_cfg.get('underlyings', ['EWY'])[0]

    ib = IB()
    ib.connect(host, port, clientId=client_id)
    ib.reqMarketDataType(market_data_type)
    underlying = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(underlying)
    
    print(f"--- Running Regime Detection for {symbol} ---")
    
    # 1. Get IV vs RV
    [ticker] = ib.reqTickers(underlying)
    iv = ticker.impliedVolatility
    if np.isnan(iv):
        iv = 0.0 # Fallback if IV not available
        
    rv = get_realized_volatility(ib, underlying, days=30)
    
    print(f"Implied Volatility (IV): {iv:.4f}")
    print(f"Realized Volatility (30D RV): {rv:.4f}" if rv else "Realized Volatility: N/A")
    
    iv_premium = 0.0
    if rv:
        iv_premium = iv - rv
        print(f"IV Premium (IV - RV): {iv_premium:.4f}")
        
    # 2. Check Macro Regime (VIX Term Structure)
    vix, vix3m, backwardation = get_vix_term_structure(ib)
    print(f"VIX: {vix} | VIX3M: {vix3m}")
    if backwardation:
        print("WARNING: VIX Term Structure is in BACKWARDATION (Panic Regime).")
    else:
        print("VIX Term Structure is in CONTANGO (Normal Regime).")

    # 3. Determine State
    state = "NEUTRAL"
    action = "HOLD"
    
    if backwardation:
        state = "CRISIS"
        action = "DEFENSE_MODE_HALT_SELLING"
    elif iv_premium > 0.05: # IV is significantly overpricing risk
        state = "HIGH_VOLATILITY"
        action = "SELL_PREMIUM"
    elif iv_premium < -0.02:
        state = "LOW_VOLATILITY"
        action = "BUY_PREMIUM"
    else:
        state = "NORMAL"
        action = "SELL_CONSERVATIVE_PREMIUM"
        
    print(f"\n=> Evaluated Regime: {state}")
    print(f"=> Recommended Action: {action}")
    
    regime_output = {
        "symbol": symbol,
        "state": state,
        "action": action,
        "metrics": {
            "iv": iv,
            "rv_30d": rv,
            "iv_premium": iv_premium,
            "vix": vix,
            "vix3m": vix3m,
            "vix_backwardation": backwardation
        }
    }
    
    with open('regime_state.json', 'w') as f:
        json.dump(regime_output, f, indent=4)
        
    print("\nRegime state saved to regime_state.json")
    ib.disconnect()

if __name__ == "__main__":
    main()