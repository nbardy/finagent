import subprocess
import json
import os
import sys

def run_script(script_name):
    print(f"\n{'='*50}\nRunning {script_name}...\n{'='*50}")
    result = subprocess.run([sys.executable, script_name])
    if result.returncode != 0:
        print(f"Error executing {script_name}. Aborting pipeline.")
        sys.exit(1)

def main():
    print("Starting IBKR Level 5 Bot Pipeline...")

    # 1. Regime Detection
    run_script("regime_detector.py")
    if not os.path.exists('regime_state.json'):
        print("Error: regime_state.json not found. Aborting.")
        return
        
    with open('regime_state.json', 'r') as f:
        regime = json.load(f)
        
    if regime.get('action') == 'DEFENSE_MODE_HALT_SELLING':
        print(f"Safety Halt: Regime state is {regime.get('state')}. Action: {regime.get('action')}. Aborting pipeline.")
        return
        
    print(f"Regime Check Passed (State: {regime.get('state')}). Proceeding to Portfolio Sync.")

    # 2. Portfolio Sync
    run_script("portfolio.py")
    if not os.path.exists('config/portfolio_state.json'):
        print("Error: config/portfolio_state.json not found. Aborting.")
        return

    with open('config/portfolio_state.json', 'r') as f:
        portfolio = json.load(f)
        
    if portfolio.get('unencumbered_inventory', 0) <= 0:
        print("Safety Halt: No unencumbered inventory available. Aborting pipeline.")
        return
        
    print(f"Portfolio Check Passed (Inventory: {portfolio.get('unencumbered_inventory')}). Proceeding to Planner.")

    # 3. Planner
    # Remove old proposal if it exists to ensure we don't execute a stale one
    if os.path.exists('trade_proposal.json'):
        os.remove('trade_proposal.json')
        
    run_script("planner_leap.py")
    if not os.path.exists('trade_proposal.json'):
        print("Warning: trade_proposal.json was not generated. Planner may have aborted due to market conditions.")
        return
        
    import uuid
    import shutil
    
    print("Planner execution successful. Trade proposal generated.")
    
    with open('trade_proposal.json', 'r') as f:
        proposals_data = json.load(f)
        
    if isinstance(proposals_data, dict) and 'trades' in proposals_data:
        proposals = proposals_data['trades']
    elif isinstance(proposals_data, list):
        proposals = proposals_data
    else:
        proposals = [proposals_data]

    for p_idx, proposal in enumerate(proposals):
        print(f"\n--- PROPOSED TRADE {p_idx + 1} ---")
        if 'tranches' in proposal:
            print("Tranches:")
            for i, tranche in enumerate(proposal.get('tranches', [])):
                print(f"  Tranche {i+1}: {proposal['action']} {tranche['quantity']} @ {tranche.get('lmtPrice', 'N/A')}")
        else:
            action = proposal.get('action', 'BUY/SELL')
            qty = proposal.get('quantity', 1)
            order_type = proposal.get('order_type', 'MKT')
            price = proposal.get('lmtPrice', 'N/A') if order_type == 'LMT' else 'MKT'
            print(f"Order: {action} {qty} @ {price}")

        metrics = proposal.get('metrics')
        if metrics:
            max_profit = metrics.get('max_profit', 'N/A')
            roc = metrics.get('roc', 'N/A')
            annualized_roc = metrics.get('annualized_roc', 'N/A')
            
            if isinstance(max_profit, (int, float)):
                print(f"\nTotal Return (Max Profit): ${max_profit:.2f}")
            else:
                print(f"\nTotal Return (Max Profit): {max_profit}")
                
            if isinstance(roc, (int, float)):
                print(f"Absolute ROC: {roc:.2f}%")
                print(f"Annualized ROC: {annualized_roc:.2f}%")
            else:
                print(f"Absolute ROC: {roc}%")
                print(f"Annualized ROC: {annualized_roc}%")
    
    proposal_uuid = str(uuid.uuid4())
    proposal_filename = f"trade_proposal_{proposal_uuid}.json"
    shutil.move('trade_proposal.json', proposal_filename)
    
    print("\n" + "="*50)
    print("Trade proposal generated and saved securely.")
    print("Please review the proposed tranches above.")
    print(f"To execute this trade, run the following command:")
    print(f"\n    uv run executor.py --file {proposal_filename}\n")
    print("="*50 + "\n")
    return
        
    print("\nPipeline completed successfully.")

if __name__ == "__main__":
    main()
