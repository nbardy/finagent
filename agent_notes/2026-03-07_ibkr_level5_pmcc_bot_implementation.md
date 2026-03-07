# IBKR Level 5 (PMCC) Bot Implementation Notes
**Date:** 2026-03-07
**Topic:** End-to-End Build and Refinement of the Level 5 Options Trading Bot

## Overview
Successfully engineered a fully autonomous, risk-managed Interactive Brokers (IBKR) quantitative trading bot using the `ib_insync` library. The bot specializes in "Level 5" options trading, specifically executing a Poor Man's Covered Call (PMCC) strategy, while also supporting synthetic downside Collars.

## Core Architecture Components
The system was designed with a strict "State Machine" philosophy, decoupling risk evaluation from execution.

1.  **`regime_detector.py`:**
    *   Acts as the macro safety switch.
    *   Calculates the 30-day Realized Volatility (RV) from underlying historical data.
    *   Compares the spot VIX against VIX3M (3-month). Halts all trading if the market is in backwardation (panic).
2.  **`portfolio.py`:**
    *   Connects to IBKR to sync current account positions.
    *   Identifies open long LEAP options (>365 DTE) and maps their specific strikes and average costs.
    *   Cross-references live order books to subtract pending limit orders, ensuring the bot never "double-files" and over-leverages the account.
3.  **`planner_leap.py`:**
    *   The quantitative pricing engine.
    *   Pulls the entire option chain within a configured DTE window.
    *   Runs a Black-Scholes pricing model against every strike to find the Theoretical Value (TV) using the Realized Volatility baseline.
    *   Executes a 25,000-path Monte Carlo simulation (`numpy`) to calculate `prob_profit`, `expected_pnl`, and `p05` (tail loss risk).
    *   Scores options using a multi-factor algorithm.
    *   Slices the desired quantity into a "patient" pricing tranche ladder that never drops below the theoretical Black-Scholes value.
    *   Optionally scans for a protective Put to construct a Collar if configured.
    *   Executes an IBKR `whatIfOrder` to prove margin safety before generating a proposal.
4.  **`executor.py`:**
    *   The execution arm. Blindly reads the `trade_proposal_UUID.json` file.
    *   Handles mixed order types (`LMT` for short calls, `MKT` for long puts).
5.  **`main.py`:**
    *   The orchestrator that runs the pipeline sequentially, formats the output for user approval, and generates the final execution command.

## Key Upgrades & Features Implemented
*   **Pacing Mechanism:** Added `max_coverage_pct_per_run` to scale into the short positions over multiple days rather than blowing the entire inventory at once.
*   **Holistic Scoring:** Moved away from simple edge hunting. Now utilizes a weighted score of Theoretical Edge, Expected PnL, Prob of Profit, Spread Penalty, and Tail Loss Penalty.
*   **Patient Discovery Pricing:** Dropped aggressive limit pricing (mid minus 20%). The bot now uses Black-Scholes TV as a hard floor and walks limit orders down from the Ask towards the TV to capture maximum edge in illiquid chains.
*   **Dynamic Collar Construction:** The bot automatically buys cheap Out-of-the-Money Puts using a configurable percentage of the short call credit, providing catastrophic downside insurance for the LEAPs.

## Dependencies
*   Python 3.12+ (managed via `uv`)
*   `ib_insync`, `scipy`, `pandas`, `numpy`
*   IB Gateway or Trader Workstation (TWS) running locally with API enabled.