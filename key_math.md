# Quantitative Models & Level 5 Mechanics

## 1. Volatility Regime Math
The bot relies on two primary metrics to detect if it is safe to sell option premium.

### A. IV vs RV Spread (The "Premium")
*   **Implied Volatility ($\sigma_{IV}$):** Forward-looking volatility priced into the options market.
*   **Realized Volatility ($\sigma_{RV}$):** Backward-looking historical volatility based on the standard deviation of daily logarithmic returns, annualized.

$$ \sigma_{RV} = \text{Stdev}(\ln(P_t / P_{t-1})) \times \sqrt{252} $$

**Signal:**
$$ \text{IV Premium} = \sigma_{IV} - \sigma_{RV} $$
*   If `IV Premium > 0`: Options are relatively expensive (Good time to sell).
*   If `IV Premium < 0`: Options are relatively cheap (Good time to buy).

### B. VIX Term Structure
*   **Spot VIX:** 30-day expected market volatility.
*   **VIX3M:** 90-day expected market volatility.

**Signal:**
*   **Contango (Normal):** $VIX < VIX3M$ (Future is expected to be more volatile than today). Safe to sell premium.
*   **Backwardation (Panic):** $VIX > VIX3M$ (Immediate panic). **HALT short-selling.**

## 2. Level 5 Structure Math (Poor Man's Covered Call / Diagonal Spread)
When converting a naked LEAP into a defined-risk spread, the financial profile changes.

### Variables
*   $P_{L}$: Price paid for the Long LEAP Call (Debit).
*   $K_{L}$: Strike price of the Long LEAP Call.
*   $P_{S}$: Premium collected from the Short Call (Credit).
*   $K_{S}$: Strike price of the Short Call.
*   $N$: Multiplier (usually 100).

### Key Equations
1.  **Adjusted Cost Basis:**
    $$ \text{Basis} = P_{L} - P_{S} $$
    *Goal is to drive this number as close to zero as possible over time.*

2.  **Maximum Profit (Yield):**
    If the underlying closes above $K_{S}$ at expiration, the spread is intrinsically worth the width of the strikes.
    $$ \text{Max Profit} = (K_{S} - K_{L}) - \text{Basis} $$

3.  **Return on Capital (ROC):**
    $$ \text{ROC} = \left( \frac{\text{Max Profit}}{\text{Basis}} \right) \times 100 $$

4.  **Static Breakeven:**
    The stock price required at expiration to neither make nor lose money.
    $$ \text{Breakeven} = K_{L} + \text{Basis} $$

## 3. Execution Math: Tranche Pricing
When slicing a large order into smaller tranches to minimize slippage, the pricing ladder is calculated as follows:

*   **Mid-Price ($P_{Mid}$):** $\frac{\text{Bid} + \text{Ask}}{2}$
*   **Tick Size ($T$):** The minimum price increment (e.g., $0.05).
*   **Aggression Factor ($A$):** The number of ticks to increment per tranche.

For $n$ tranches:
$$ \text{Price of Tranche } i = P_{Mid} + (i \times T \times A) $$
*(Where $i$ ranges from $0$ to $n-1$)*

*Example for 3 tranches with a $0.05 tick:*
*   Tranche 0: $P_{Mid}$
*   Tranche 1: $P_{Mid} + \$0.05$
*   Tranche 2: $P_{Mid} + \$0.10$

## 4. Expected Value (EV) for Weekly Short Options
If selling short-dated options rather than a LEAP, the probability model uses Delta ($\Delta$) as a proxy for the probability of expiring In-The-Money (ITM).

*   $P(\text{ITM}) \approx |\Delta|$
*   $P(\text{OTM}) = 1 - P(\text{ITM})$

$$ EV = (\text{Credit Collected} \times P(\text{OTM})) - (\text{Expected Roll Penalty} \times P(\text{ITM})) $$
*Where Expected Roll Penalty is an estimated cost of closing the short option at a loss if tested.*