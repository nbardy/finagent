# Key Insights & Future Work (Level 5 PMCC Bot)
**Date:** 2026-03-07
**Topic:** Critical learnings from the PMCC implementation and roadmap for v2.0

## Key Quantitative Insights Documented
1. **The Gamma Risk of Weeklies:** While chaining weekly options mathematically generates higher gross premium over time due to accelerated Theta decay, it introduces severe Gamma Risk. If the underlying spikes, a weekly option's delta explodes towards 1.0 instantly, trapping the position. The switch to `annualized_roc` in our scoring formula elegantly handles this: it will favor weeklies *only* if the premium heavily outweighs the tail risk penalty detected by the Monte Carlo simulation.
2. **The "Mid Price" Illusion:** In illiquid chains (like many ETFs or individual stocks), the "Mid" price is a phantom number. Aggressive limit pricing (like `Mid - 20%`) just gets picked off by market makers. The true north must always be the **Black-Scholes Theoretical Value (TV)** driven by recent *Realized Volatility*, not just Implied Volatility. Patiently tranching down to the TV ensures we never surrender our statistical edge.
3. **Margin Efficiency (The "Free" Hedge):** By strictly enforcing that the short call's strike is $\ge$ the long LEAP's strike, Interactive Brokers recognizes the structure as a fully covered Long Call Diagonal Spread. This results in $0 additional Initial Margin required, allowing the collected premium to act as an immediate, liquid cash buffer.
4. **The Collar Trade-Off:** Buying a protective Put (the "Collar") is not a free lunch. It mathematically drags down the yield (ROC) during sideways or bullish markets. It is strictly a catastrophe insurance policy. Funding it with "house money" (a percentage of the short call credit) makes it psychologically easier to stomach, but it should only be enabled when macro regimes (like VIX term structure) look unstable.

## Remaining Work & Roadmap (v2.0)

While the V1 bot is fully capable of entering optimal trades, managing the lifecycle of those trades still requires human oversight.

### 1. Automated Rolling Engine
*   **The Gap:** Currently, if EWY spikes and the short call goes deep In-The-Money (ITM), the bot does nothing. The user must manually "roll" the option (buy it back at a loss and sell a higher strike further out in time) to prevent the LEAP from being assigned.
*   **The Fix:** Build a `roller.py` module that runs daily. If a short call's delta exceeds a danger threshold (e.g., $\Delta > 0.80$) or DTE gets too close to zero while ITM, the bot automatically generates a calendar/diagonal roll proposal to push the cap higher and extend duration.

### 2. Expiration Day Manager
*   **The Gap:** Options expiring worthless just disappear, which is fine. But options near the money on expiration Friday (0 DTE) carry massive "Pin Risk."
*   **The Fix:** Add a cron job specifically for Friday afternoons to evaluate any open short calls expiring that day. If they are within 1% of the strike price, automatically close them out for pennies to eliminate after-hours assignment risk.

### 3. Market Data Subscription Verification
*   **The Gap:** The bot heavily relies on live Bid/Ask and `modelGreeks`. If the user does not have the correct OPRA live data subscriptions in IBKR, the API will return `NaN` or delayed/stale data.
*   **The Fix:** Add a strict pre-flight check in `portfolio.py` or `main.py` that queries market data status and explicitly aborts with a clear error message if live data is not detected.

### 4. Dynamic Delta Hedging (The Institutional Upgrade)
*   **The Gap:** We are statically selling calls based on fixed DTE and Edge.
*   **The Fix:** Upgrade the bot to manage the *Net Delta* of the portfolio. If the long LEAP is $\Delta = 0.80$, we might want a constant Net Delta of $0.50$. The bot would dynamically sell or buy back short calls continuously to pin the portfolio to that $0.50$ target, turning the bot into a true continuous market-neutral(ish) volatility harvester.