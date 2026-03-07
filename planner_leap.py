import json
import math
import os
from datetime import datetime
from ib_insync import *
import numpy as np

def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def black_scholes_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0:
        return max(0.0, S - K)
    sigma = max(1e-6, sigma)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)

def monte_carlo_short_call_metrics(S: float, K: float, T: float, sigma: float, premium: float, num_simulations: int = 25000) -> tuple[float, float, float]:
    """
    Simulates price paths to calculate risk/return metrics for a short call.
    Assumes mu = 0.0.
    Returns (prob_profit, expected_pnl, p05)
    """
    if T <= 0:
        pnl = premium - max(0.0, S - K)
        return (1.0 if pnl > 0 else 0.0, pnl, pnl)
    
    mu = 0.0
    # Geometric Brownian Motion terminal price
    Z = np.random.standard_normal(num_simulations)
    S_T = S * np.exp((mu - 0.5 * sigma**2) * T + sigma * np.sqrt(T) * Z)
    
    # PnL for short call = premium received - intrinsic value at expiration
    pnl = premium - np.maximum(0.0, S_T - K)
    
    prob_profit = np.mean(pnl > 0.0)
    expected_pnl = np.mean(pnl)
    p05 = np.percentile(pnl, 5)
    
    return float(prob_profit), float(expected_pnl), float(p05)

def main():
    # Load configuration
    with open('pmcc_config.json', 'r') as f:
        config = json.load(f)
        
    conn_cfg = config.get('connection', {})
    host = conn_cfg.get('host', '127.0.0.1')
    port = conn_cfg.get('port', 7497)
    client_id = conn_cfg.get('client_id_planner', 1)
    market_data_type = conn_cfg.get('market_data_type', 1)
    
    strat_cfg = config.get('strategy', {})
    min_short_dte = strat_cfg.get('min_short_dte', 10)
    max_short_dte = strat_cfg.get('max_short_dte', 45)
    min_bid = strat_cfg.get('min_bid', 0.05)
    max_bid_ask_spread_pct = strat_cfg.get('max_bid_ask_spread_pct', 0.40)
    enable_collar = strat_cfg.get('enable_collar', True)
    collar_max_cost_pct_of_credit = strat_cfg.get('collar_max_cost_pct_of_credit', 0.30)
    collar_target_delta = strat_cfg.get('collar_target_delta', -0.15)
    
    score_weights = strat_cfg.get('score_weights', {})
    w_edge = score_weights.get('theoretical_edge', 3.0)
    w_ann_roc = score_weights.get('annualized_roc', 2.0)
    w_spread = score_weights.get('spread_penalty', -1.5)
    w_prob_profit = score_weights.get('prob_profit', 2.0)
    w_expected_pnl = score_weights.get('expected_pnl', 1.0)
    w_tail_loss = score_weights.get('tail_loss', 1.0)
    
    model_cfg = config.get('model', {})
    risk_free_rate = model_cfg.get('risk_free_rate', 0.045)
    
    exec_cfg = config.get('execution', {})
    what_if_margin_check = exec_cfg.get('what_if_margin_check', True)
    max_coverage_pct_per_run = exec_cfg.get('max_coverage_pct_per_run', 1.0)

    # 1. Read portfolio state
    if not os.path.exists('portfolio_state.json'):
        print("Portfolio state not found. Run portfolio.py first.")
        return
        
    with open('portfolio_state.json', 'r') as f:
        portfolio_state = json.load(f)
        
    total_unencumbered_inventory = portfolio_state.get('total_unencumbered_inventory', 0)
    if total_unencumbered_inventory <= 0:
        print("No unencumbered inventory available. Exiting planner.")
        return
        
    unencumbered_leaps = portfolio_state.get('unencumbered_leaps', [])
    if not unencumbered_leaps:
        print("No unencumbered LEAPs found.")
        return
        
    # Pick the lowest strike unencumbered LEAP to use for spread math
    target_leap = unencumbered_leaps[0]
    long_leap_strike = target_leap['strike']
    avg_cost_leaps = target_leap['avg_cost']
    
    # Calculate pacing
    max_qty_allowed = max(1, math.ceil(total_unencumbered_inventory * max_coverage_pct_per_run))
    # We shouldn't sell more than what's available in this specific LEAP bucket for strict math alignment,
    # or we can cap it. Let's cap it to max_qty_allowed or target_leap['qty_available']
    total_quantity_to_sell = min(max_qty_allowed, target_leap['qty_available'])
    
    print(f"Pacing Check: Total Unencumbered={total_unencumbered_inventory}, Max Pct={max_coverage_pct_per_run*100}%, Selling={total_quantity_to_sell} against {long_leap_strike}C")

    # Read regime state for our model's baseline Volatility
    baseline_vol = 0.25
    if os.path.exists('regime_state.json'):
        with open('regime_state.json', 'r') as f:
            regime_state = json.load(f)
            rv_30d = regime_state.get('metrics', {}).get('rv_30d')
            if rv_30d and not math.isnan(rv_30d):
                baseline_vol = rv_30d

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id)
        ib.reqMarketDataType(market_data_type)

        symbol = portfolio_state.get('symbol', 'EWY')
        underlying = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(underlying)
        
        [ticker] = ib.reqTickers(underlying)
        current_price = ticker.marketPrice()
        if math.isnan(current_price):
            current_price = ticker.close 
        print(f"{symbol} Current Price: {current_price}")
        print(f"Pricing Model Baseline Volatility (RV): {baseline_vol:.4f}")

        chains = ib.reqSecDefOptParams(underlying.symbol, '', underlying.secType, underlying.conId)
        chain = next((c for c in chains if c.exchange == 'SMART'), None)
        
        if not chain:
            print("No option chain found.")
            return

        today = datetime.now()
        
        # Filter expirations and strikes
        # Scan for options within target DTE and OTM (strike > spot AND strike >= long_leap_strike)
        valid_expirations = []
        for exp in chain.expirations:
            exp_date = datetime.strptime(exp, '%Y%m%d')
            dte = (exp_date - today).days
            if min_short_dte <= dte <= max_short_dte:
                valid_expirations.append((exp, dte))
                
        valid_strikes = [s for s in chain.strikes if s > current_price and s >= long_leap_strike]

        contracts = []
        for exp, dte in valid_expirations:
            for strike in valid_strikes:
                contracts.append(Option(symbol, exp, strike, 'C', 'SMART'))
                
        print(f"Qualifying {len(contracts)} contracts for scanning...")
        # Batch qualify to avoid getting throttled if the chain is huge
        contracts = ib.qualifyContracts(*contracts)
        
        print(f"Polling market data for {len(contracts)} options. This may take a moment...")
        tickers = ib.reqTickers(*contracts)
        
        opportunities = []
        for t in tickers:
            bid = t.bid
            ask = t.ask
            if math.isnan(bid) or math.isnan(ask) or bid < min_bid:
                continue
                
            mid_price = (bid + ask) / 2
            
            # Bid/Ask Spread Percentage check
            spread = ask - bid
            spread_pct = spread / mid_price if mid_price > 0 else float('inf')
            if spread_pct > max_bid_ask_spread_pct:
                continue
                
            exp_str = t.contract.lastTradeDateOrContractMonth
            exp_date = datetime.strptime(exp_str, '%Y%m%d')
            dte = max((exp_date - today).days, 1)
            T = dte / 365.0
            
            strike = t.contract.strike
            
            # Black-Scholes Theoretical Value
            tv = black_scholes_call(current_price, strike, T, risk_free_rate, baseline_vol)
            
            # Edge definition
            edge = mid_price - tv
            
            # Level 5 Math
            premium_collected = mid_price
            adjusted_basis = avg_cost_leaps - premium_collected
            max_profit = (strike - long_leap_strike) - adjusted_basis
            roc = (max_profit / adjusted_basis) * 100 if adjusted_basis > 0 else float('inf')
            annualized_roc = (roc / dte) * 365.0 if dte > 0 else 0.0
            
            # Monte Carlo Metrics
            prob_profit, expected_pnl, p05 = monte_carlo_short_call_metrics(
                current_price, strike, T, baseline_vol, premium_collected, num_simulations=25000
            )
            
            # Holistic Scoring
            score = (prob_profit * w_prob_profit) + (expected_pnl * w_expected_pnl) + (min(0, p05) * w_tail_loss) + (edge * w_edge) + (spread_pct * w_spread)
            
            opportunities.append({
                "contract": t.contract,
                "dte": dte,
                "strike": strike,
                "bid": bid,
                "ask": ask,
                "mid_price": mid_price,
                "theoretical_value": tv,
                "edge": edge,
                "roc": roc,
                "annualized_roc": annualized_roc,
                "spread_pct": spread_pct,
                "score": score,
                "iv": t.modelGreeks.impliedVol if t.modelGreeks else "N/A",
                "adjusted_basis": adjusted_basis,
                "max_profit": max_profit,
                "prob_profit": prob_profit,
                "expected_pnl": expected_pnl,
                "p05": p05
            })
            
        if not opportunities:
            print("No viable opportunities found matching criteria (e.g. no valid bids).")
            return
            
        # Ensure max_profit is positive
        valid_opps = [o for o in opportunities if o['max_profit'] > 0]
        
        if not valid_opps:
            print("No options found with positive max profit. Showing best available by Annualized ROC.")
            valid_opps = sorted(opportunities, key=lambda x: x['annualized_roc'], reverse=True)
        else:
            # Sort by highest holistic score
            valid_opps = sorted(valid_opps, key=lambda x: x['score'], reverse=True)
            
        best_opp = valid_opps[0]
        contract = best_opp['contract']
        mid_price = best_opp['mid_price']
        
        print("\n" + "="*50)
        print("--- BEST OPTION PRICING OPPORTUNITY FOUND ---")
        print(f"Target Contract: {contract.symbol} {contract.lastTradeDateOrContractMonth} {contract.strike}{contract.right}")
        print(f"DTE: {best_opp['dte']} days")
        print(f"Market Mid Price: ${mid_price:.2f}")
        print(f"Black-Scholes Theoretical Value: ${best_opp['theoretical_value']:.2f}")
        print(f"Theoretical Edge (Alpha): ${best_opp['edge']:.2f}")
        print(f"Bid/Ask Spread Pct: {best_opp['spread_pct']*100:.2f}%")
        print(f"Holistic Score: {best_opp['score']:.2f}")
        print(f"Implied Volatility: {best_opp['iv']}")
        print(f"Prob of Profit: {best_opp['prob_profit']*100:.2f}%")
        print(f"Expected PnL: ${best_opp['expected_pnl']:.2f}")
        print(f"5th Percentile Tail (p05): ${best_opp['p05']:.2f}")
        
        print(f"\n--- Level 5 Spread Math ---")
        print(f"Assumed Long LEAP Strike: {long_leap_strike}")
        print(f"Original LEAP Cost Basis: ${avg_cost_leaps:.2f}")
        print(f"Premium Collected: ${mid_price:.2f}")
        print(f"Adjusted Cost Basis: ${best_opp['adjusted_basis']:.2f}")
        print(f"Max Profit: ${best_opp['max_profit']:.2f}")
        print(f"Return on Capital (ROC): {best_opp['roc']:.2f}%")
        print(f"Annualized ROC: {best_opp['annualized_roc']:.2f}%")
        print("="*50)

        # 5. Generate JSON Proposal (Tranches)
        # Using paced total_quantity_to_sell calculated earlier
        
        TICK_SIZE = 0.05
        
        # Patient / Theoretical Discovery Pricing
        tv = best_opp['theoretical_value']
        ask = best_opp['ask']
        
        if tv > mid_price:
            start_price = max(tv, ask) if ask > 0 else tv + TICK_SIZE
        else:
            start_price = ask if ask > 0 else mid_price + TICK_SIZE
            
        # Round up to nearest tick
        start_price = math.ceil(start_price / TICK_SIZE) * TICK_SIZE

        tranches = []
        qty_per_tranche = max(1, total_quantity_to_sell // 2)
        remaining_qty = total_quantity_to_sell
        
        tranche_idx = 0
        while remaining_qty > 0:
            tranche_qty = min(qty_per_tranche, remaining_qty)
            target_price = start_price - (tranche_idx * TICK_SIZE)
            # Patient order flow: Never go below Theoretical Value
            price = max(target_price, tv)
            # Round to tick
            price = round(price / TICK_SIZE) * TICK_SIZE
            price = round(price, 2)
            
            tranches.append({
                "quantity": tranche_qty,
                "lmtPrice": price
            })
            remaining_qty -= tranche_qty
            tranche_idx += 1

        order_proposal = {
            "action": "SELL",
            "total_quantity": total_quantity_to_sell,
            "contract": {
                "symbol": contract.symbol,
                "secType": "OPT",
                "exchange": "SMART",
                "currency": "USD",
                "lastTradeDateOrContractMonth": contract.lastTradeDateOrContractMonth,
                "strike": contract.strike,
                "right": contract.right
            },
            "order_type": "LMT",
            "tranches": tranches,
            "metrics": {
                "current_underlying_price": current_price,
                "iv_at_capture": best_opp['iv'],
                "theoretical_value": best_opp['theoretical_value'],
                "theoretical_edge": best_opp['edge'],
                "adjusted_basis": best_opp['adjusted_basis'],
                "max_profit": best_opp['max_profit'],
                "roc": best_opp['roc'],
                "annualized_roc": best_opp['annualized_roc'],
                "breakeven": long_leap_strike + best_opp['adjusted_basis'],
                "spread_pct": best_opp['spread_pct'],
                "prob_profit": best_opp['prob_profit'],
                "expected_pnl": best_opp['expected_pnl'],
                "p05": best_opp['p05'],
                "score": best_opp['score']
            }
        }

        proposals = [order_proposal]

        if enable_collar:
            print("\n--- Scanning for Downside Put Hedge (Collar) ---")
            target_exp = contract.lastTradeDateOrContractMonth
            
            collar_contracts = []
            for strike in chain.strikes:
                if strike < current_price:
                    collar_contracts.append(Option(symbol, target_exp, strike, 'P', 'SMART'))
                    
            if collar_contracts:
                print(f"Qualifying {len(collar_contracts)} puts for collar...")
                collar_contracts = ib.qualifyContracts(*collar_contracts)
                collar_tickers = ib.reqTickers(*collar_contracts)
                
                collar_candidates = []
                max_cost = mid_price * collar_max_cost_pct_of_credit
                
                for t in collar_tickers:
                    bid = t.bid
                    ask = t.ask
                    if math.isnan(bid) or math.isnan(ask) or ask <= 0:
                        continue
                        
                    p_mid = (bid + ask) / 2
                    if p_mid > max_cost:
                        continue
                    
                    delta = t.modelGreeks.delta if t.modelGreeks and t.modelGreeks.delta is not None else None
                    if delta is None or math.isnan(delta):
                        continue
                    
                    delta_diff = abs(delta - collar_target_delta)
                    
                    collar_candidates.append({
                        "contract": t.contract,
                        "bid": bid,
                        "ask": ask,
                        "mid_price": p_mid,
                        "delta": delta,
                        "delta_diff": delta_diff
                    })
                    
                if collar_candidates:
                    collar_candidates.sort(key=lambda x: x['delta_diff'])
                    best_put = collar_candidates[0]
                    
                    print(f"Found collar put: {best_put['contract'].strike}P")
                    print(f"Target Delta: {collar_target_delta}, Put Delta: {best_put['delta']:.2f}")
                    print(f"Put Mid Price: ${best_put['mid_price']:.2f} (Max Cost: ${max_cost:.2f})")
                    
                    collar_proposal = {
                        "action": "BUY",
                        "quantity": total_quantity_to_sell,
                        "contract": {
                            "symbol": best_put['contract'].symbol,
                            "secType": "OPT",
                            "exchange": "SMART",
                            "currency": "USD",
                            "lastTradeDateOrContractMonth": best_put['contract'].lastTradeDateOrContractMonth,
                            "strike": best_put['contract'].strike,
                            "right": best_put['contract'].right
                        },
                        "order_type": "MKT",
                        "estimated_price": best_put['mid_price']
                    }
                    proposals.append(collar_proposal)
                else:
                    print("No suitable collar put found within cost and delta constraints.")

        # WhatIf Margin Check
        if what_if_margin_check:
            print("\n--- Performing WhatIf Margin Check ---")
            order = LimitOrder('SELL', total_quantity_to_sell, tranches[0]['lmtPrice'])
            what_if = ib.whatIfOrder(contract, order)
            if what_if:
                margin_impact = {
                    "initMarginChange": what_if.initMarginChange,
                    "maintMarginChange": what_if.maintMarginChange,
                    "commission": what_if.commission,
                    "minCommission": what_if.minCommission,
                    "maxCommission": what_if.maxCommission
                }
                proposals[0]['what_if'] = margin_impact
                print(f"Initial Margin Change: {what_if.initMarginChange}")
                print(f"Maintenance Margin Change: {what_if.maintMarginChange}")
                print(f"Commission: {what_if.commission}")
            else:
                print("Failed to retrieve WhatIf data.")

        with open('trade_proposal.json', 'w') as f:
            json.dump(proposals, f, indent=4)
            
    except Exception as e:
        print(f"Error in planner: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()

if __name__ == "__main__":
    main()
