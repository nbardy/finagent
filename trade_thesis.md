# Trade Thesis: Level 5 PMCC & Dynamic Collar on EWY

## 1. The Current Situation (The Problem)
*   **Asset:** EWY (iShares MSCI South Korea ETF).
*   **Current Position:** Long-dated LEAP Calls (expiring in 2027).
*   **Market Condition:** The underlying asset (EWY) has experienced a significant crash and is currently trading sideways/bleeding. 
*   **The Impact:** The long LEAP position is suffering from structural decay. It is bleeding **Theta** (time decay) daily, and if Implied Volatility (IV) drops from its current panic levels, it will also suffer from **Vega** contraction (volatility crush).

## 2. The Strategic Goal (The Solution)
The goal is to transition the portfolio from a pure directional gamble (Level 1/2) to a synthetic balance sheet (Level 5) that monetizes the current high volatility environment.

We aim to:
1.  **Stop the Bleeding:** Generate immediate cash flow to offset the daily Theta decay of the LEAPs.
2.  **Lower Cost Basis:** Use the collected premium to aggressively buy down the average cost of the original LEAP position.
3.  **Hedge Downside (Optional):** Prevent a total wipeout in the event of a catastrophic secondary crash by structuring a "Poor Man's Collar."

## 3. The Execution Mechanics (Level 5 PMCC)

We are executing a **Poor Man's Covered Call (PMCC)**, also known as a Long Call Diagonal Spread.

*   **The Long Leg (Already Owned):** 2027 LEAP Call (e.g., Strike $50). Acts as synthetic stock ownership.
*   **The Short Leg (The Engine):** We systematically sell Out-of-the-Money (OTM) short-dated calls (10 to 45 Days to Expiration) against the LEAP.

### Why this works:
Because the Short Call expires *before* the Long LEAP, and the Short Call's strike is *above* the Long LEAP's strike, the broker (Interactive Brokers) recognizes the risk as fully defined. The trade requires **$0 in additional margin** while instantly depositing the short premium as cash into the account.

## 4. The Quantitative Math

The bot relies on a blend of theoretical pricing and statistical simulation to find the optimal strike to sell.

### A. Regime Detection & Baseline Volatility
Instead of blindly trusting the option's Implied Volatility (IV), we calculate the 30-day **Realized Volatility (RV)** of EWY.
$$ \sigma_{RV} = \text{Stdev}(\ln(P_t / P_{t-1})) \times \sqrt{252} $$
We use this RV as the "true" baseline volatility to price options. We also monitor the VIX Term Structure. If VIX Spot > VIX 3-Month (Backwardation), the system halts trading to prevent selling into a macro liquidity crisis.

### B. Theoretical Edge (Black-Scholes)
The bot calculates the Black-Scholes Theoretical Value (TV) of every option using our RV baseline.
$$ \text{Edge} = \text{Market Mid Price} - \text{Theoretical Value} $$
We only sell options where the Edge is positive (meaning the market is overpaying for the risk).

### C. Monte Carlo Simulation
For every candidate option, the bot runs 25,000 simulated future price paths for EWY. It calculates:
*   `prob_profit`: The percentage of paths where the option expires OTM (we keep the cash).
*   `expected_pnl`: The average mathematical profit across all paths.
*   `p05` (Tail Loss): The monetary loss experienced in the worst 5% of paths.

### D. Holistic Scoring
Options are ranked using a multi-factor algorithm to find the perfect balance of yield and safety:
$$ \text{Score} = (W_{Edge} \times \text{Edge}) + (W_{PnL} \times \text{Expected PnL}) + (W_{Prob} \times \text{Prob Profit}) + (W_{Tail} \times \text{Tail Loss Penalty}) - (W_{Spread} \times \text{Spread Pct}) $$

## 5. The "Bad" Scenarios & Defense

### Scenario A: EWY Rips Upward (The "Cap")
If EWY suddenly rockets past our Short Call strike (e.g., $155), the short call goes deep in the money.
*   **Result:** We are assigned. Our 2027 LEAP is automatically exercised to cover the shares. 
*   **Math:** We realize our **Maximum Profit**.
    $$ \text{Max Profit} = (\text{Short Strike} - \text{Long Strike}) - (\text{Original LEAP Cost} - \text{Premium Collected}) $$
*   **Action:** No action needed. We accept the predefined profit cap. If we want to stay in the trade, we must manually "roll" the short call up and out at a loss.

### Scenario B: EWY Crashes Further (The Collar)
If EWY crashes, the short call expires worthless, but the LEAP suffers massive capital destruction.
*   **Defense (The Collar):** If configured, the bot takes a fraction of the premium collected from the Short Call (e.g., 30%) and uses it to buy a deep OTM protective Put expiring on the same day. 
*   **Result:** The trade becomes a **Poor Man's Collar**. If the crash occurs, the Put explodes in value, offsetting the catastrophic losses on the LEAP. If the crash does not occur, the Put expires worthless, but it was financed entirely by "house money" from the short call.