# Implementation Guide: IBKR Level 5 Bot

## 1. Environment & Prerequisites

### Infrastructure
* **Target Environment:** A dedicated machine or cloud server (e.g., AWS EC2, DigitalOcean Droplet) running Linux (Ubuntu recommended).
* **IB Gateway:** Install the headless IB Gateway (not the full TWS GUI) for stability.
* **IBC (IB Controller):** Install `IBC` to automate the daily login and restart of the IB Gateway. Interactive Brokers forces a daily logout; IBC handles this automatically so your bot can run 24/7.
* **Ports:** Ensure your bot connects to the correct port (default `4001` for Live Gateway, `4002` for Paper Gateway).

### Python Dependencies
```bash
pip install ib_insync pandas numpy scipy
```

## 2. Core Library: `ib_insync`
The entire bot relies on `ib_insync` to wrap the official IB API into an async/await pattern.
* **Client IDs:** Every distinct script (Regime, Portfolio, Planner, Executor) connecting to the Gateway simultaneously must use a unique `clientId`.
* **Qualifying Contracts:** Always run `ib.qualifyContracts(contract)` before requesting data. This ensures IBKR resolves the specific security (populating the `conId`).

## 3. Step-by-Step Implementation

### Step 1: The Portfolio Sync (`portfolio.py`)
1. Connect via `ib = IB()`.
2. Call `ib.positions()`. This returns a list of `Position` objects.
3. Iterate and filter for the target underlying (e.g., `symbol == 'EWY'`).
4. Separate the positions into `Long LEAPS` (DTE > 365, Quantity > 0) and `Short Calls` (Quantity < 0).
5. Calculate the *Unencumbered Inventory*: `Quantity(Long LEAPS) - ABS(Quantity(Short Calls))`.
6. Write this integer to a `portfolio_state.json` file.

### Step 2: The Return Estimator (`planner_leap.py`)
1. Read `portfolio_state.json`. If inventory `> 0`, proceed.
2. Define the target contract to sell (e.g., 2027 155c).
3. Request market data: `ib.reqTickers()`. **Note:** Ensure you have OPRA live data subscriptions, or the bid/ask will return `NaN`.
4. Calculate the execution price: `Mid = (Bid + Ask) / 2`.
5. Generate the JSON structure (Action, Quantity, Contract Details, LmtPrice).

### Step 3: Advanced Execution & Tranching (`executor.py`)
Retail traders dump market orders. Quants use tranches.
If the proposal requests selling 20 contracts:
1. Do not submit one `LMT` order of 20 at the Mid.
2. Slice the order:
   * Tranche 1: Qty 5 @ `Mid`
   * Tranche 2: Qty 5 @ `Mid + $0.05`
   * Tranche 3: Qty 5 @ `Mid + $0.10`
   * Tranche 4: Qty 5 @ `Ask`
3. Loop through the tranches, generating a unique `LimitOrder` object for each.
4. Call `ib.placeOrder(contract, order)`.
5. *Optional Upgrade:* Implement a timeout. If Tranche 1 isn't filled in 60 seconds, cancel and recalculate the mid.

### Step 4: The Master Orchestrator (`main.py`)
Create a standard python script utilizing `subprocess.run` to call the individual modules in sequence.
```python
import subprocess
import json

def run_pipeline():
    # 1. Check Regime
    subprocess.run(["python", "regime_detector.py"])
    with open('regime_state.json') as f:
         if json.load(f)['action'] == 'DEFENSE_MODE_HALT_SELLING':
             return # Abort
    
    # 2. Check Portfolio & Plan
    subprocess.run(["python", "portfolio.py"])
    subprocess.run(["python", "planner_leap.py"])
    
    # 3. Execute
    subprocess.run(["python", "executor.py", "--file", "trade_proposal.json"])
```

## 4. Deployment
Setup a crontab on your Linux server to run `main.py` at a specific time when liquidity is highest (e.g., 30 minutes after market open).
```bash
30 10 * * 1-5 /usr/bin/python3 /path/to/bot/main.py >> /var/log/ibkr_bot.log 2>&1
```