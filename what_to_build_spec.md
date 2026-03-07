# Level 5 Options Trading Bot Specification

## 1. Objective
Build an institutional-grade, fully autonomous quantitative trading bot for Interactive Brokers (IBKR). The system executes "Level 5" option strategies: holding long-duration, directional LEAPs (e.g., EWY) while automatically selling short-dated premium (calls) or long-dated LEAP calls (converting to vertical spreads) to harvest spikes in Implied Volatility (IV) and reduce cost basis.

## 2. Core Philosophy
* **State Machine over Signal Spam:** The bot does not trade on a whim. It evaluates the macro volatility regime and only acts if the environment is safe.
* **Decoupled Architecture:** Separation of concerns. The planner generates a static JSON plan; the executor blindly reads and executes the JSON. This prevents runaway code from rapid-firing orders.
* **Capital Efficiency:** Leverage Portfolio Margin (if available) or defined-risk structures (PMCC/Diagonals) rather than raw margin debt.

## 3. System Components

### A. Regime Detector (`regime_detector.py`)
* **Role:** The safety switch. Assesses macro and micro volatility.
* **Inputs:** VIX spot, VIX3M (3-month), Underlying IV, Underlying 30D Realized Volatility (RV).
* **Outputs:** State (e.g., `NORMAL`, `HIGH_VOLATILITY`, `CRISIS`) and Action (`SELL_PREMIUM`, `DEFENSE_MODE_HALT_SELLING`).

### B. Portfolio Sync Engine (`portfolio.py`)
* **Role:** State reconciliation. Answers "What do I actually own right now?"
* **Inputs:** IBKR API position data, account margin data.
* **Outputs:** JSON map of unencumbered LEAP inventory (e.g., "I have 5 EWY LEAPs not currently covered by short calls").

### C. Return Estimator & Planner (`planner_leap.py` / `planner_weekly.py`)
* **Role:** The brain. Finds the optimal strike to sell, calculates expected returns, and generates the trade instructions.
* **Inputs:** Live option chains, Greeks, Portfolio inventory, Regime state.
* **Outputs:** `trade_proposal.json` containing the specific contracts, proposed limit prices, order sizing, and calculated Yield/Probability of Profit.

### D. Tranching & Execution Engine (`executor.py`)
* **Role:** The muscle. Slices large orders to minimize market impact.
* **Inputs:** `trade_proposal.json`.
* **Outputs:** Live IBKR Limit Orders.
* **Logic:** Never cross the bid/ask spread. Places limit orders pegged to the midpoint, potentially sliced into ladders (e.g., Mid, Mid + $0.05, Mid + $0.10).

### E. Master Orchestrator (`main.py`)
* **Role:** The conductor. Runs on a cron schedule (e.g., daily at 10:30 AM).
* **Workflow:**
  1. Pull Regime State. If `CRISIS` -> Exit.
  2. Pull Portfolio State. If inventory = 0 -> Exit.
  3. Run Planner to generate proposal.
  4. Pass proposal to Executor.

## 4. Operational Guardrails
1. **Never Sell Naked:** Short call quantity must strictly be `≤` Long LEAP quantity.
2. **Crisis Halt:** Stop all new short-selling if VIX term structure enters backwardation (VIX > VIX3M).
3. **Delta Floor:** Do not sell calls that reduce the net position delta below the target threshold (e.g., 0.50) unless legging into a permanent spread.
4. **Liquidity Check:** Do not place trades if the Bid/Ask spread is abnormally wide (e.g., > 20% of the mid-price).