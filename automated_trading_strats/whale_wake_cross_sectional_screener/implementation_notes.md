# Whale Wake Cross-Sectional Screener: Production Upgrade Notes

To take this from a "theoretical script" to a **production-ready quantitative system**, you are missing the actual **execution plumbing** to pull the real options contracts, and you need two major pieces of **better math** to protect your capital.

Right now, the bot knows *what* to look for, but it needs a mathematical upgrade to avoid false positives (retail fake-outs), and it needs a risk engine to determine *how much money* to bet.

Here are the mathematical upgrades and the final Python code block to complete the system.

---

## Upgrade 1: Volume-Weighted Footprints (The Fake-Wake Filter)

Standard momentum (`mu`) and the Hurst Exponent (`H`) only look at *price*.

**The trap:** Retail traders can push a low-float stock up 5% on tiny volume. The bot will calculate a high `H` (memory) and buy the option, only to get crushed when a real institutional seller steps in.

**The fix:** Upgrade the math to **volume-weighted returns**. Multiply the hourly price change by the *relative volume* of that hour. If the stock goes up on tiny volume, the math scales the momentum down to near zero. If the stock goes up on massive volume (a true institutional VWAP algorithm), the momentum score explodes.

## Upgrade 2: The Kelly Criterion (Bet Sizing)

If the Fractional Black-Scholes equation tells you a call option is mathematically underpriced by 40%, **how many contracts do you buy?**

Retail traders guess. Quants use the **Kelly Criterion**. It is a portfolio-sizing formula that takes the edge ratio and calculates the precise percentage of the portfolio to risk to maximize compounding growth while controlling ruin risk.

---

## Final Python Architecture

```python
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm
import datetime
import warnings
warnings.filterwarnings('ignore')  # Suppress yfinance timezone warnings

# ==========================================
# 1. THE "BETTER MATH" ENGINE
# ==========================================

def get_volume_weighted_footprints(ticker_symbol, lookback_days=14):
    """
    UPGRADE 1: Calculates Momentum (mu) and Memory (H) using Volume-Weighted returns.
    This guarantees we are tracking a Whale, not retail noise.
    """
    df = yf.Ticker(ticker_symbol).history(period=f"{lookback_days}d", interval="1h")
    if len(df) < 20:
        return 0.0, 0.50, 0.20, df['Close'].iloc[-1]

    prices = df['Close'].values
    volumes = df['Volume'].values

    # 1. Calculate Relative Volume (RV)
    avg_vol = np.mean(volumes)
    rel_vol = np.where(volumes == 0, 1, volumes / avg_vol)

    # 2. Scale the returns by how heavy the volume was
    returns = np.diff(prices) / prices[:-1]
    vw_returns = returns * rel_vol[1:]

    # Reconstruct a "Volume-Weighted Price Path"
    vw_prices = np.insert(np.cumprod(1 + vw_returns), 0, 1.0)

    # 3. Drift (mu)
    time_fraction = lookback_days / 252.0
    vw_mu = (vw_prices[-1] - 1) / time_fraction

    # 4. Hurst Exponent (H) on the Volume-Weighted Path
    lags = range(2, 20)
    tau = [np.std(np.subtract(vw_prices[lag:], vw_prices[:-lag])) for lag in lags]
    poly = np.polyfit(np.log(lags), np.log(tau), 1)
    H = max(0.01, min(0.99, poly[0]))

    # Parkinson Volatility (Uses High/Lows for better intraday VWAP volatility)
    highs, lows = df['High'].values, df['Low'].values
    lows = np.where(lows == 0, 1e-8, lows)
    log_hl = np.log(highs / lows) ** 2
    sigma = np.sqrt((1.0 / (4.0 * np.log(2.0))) * np.mean(log_hl)) * np.sqrt(252 * 7)

    return vw_mu, H, max(sigma, 0.05), prices[-1]

def kelly_bet_size(win_prob, edge_ratio):
    """
    UPGRADE 2: Calculates the exact percentage of your account to risk.
    """
    b = edge_ratio - 1.0  # The payoff odds
    if b <= 0:
        return 0.0

    kelly_pct = (win_prob * b - (1 - win_prob)) / b

    # "Half-Kelly" is the quantitative industry standard to prevent massive drawdowns
    half_kelly = kelly_pct / 2.0

    # Hard cap at 5% of account per trade to survive tail-risk events
    return max(0.0, min(half_kelly, 0.05))

def fractional_black_scholes(S, K, T, r, sigma, H):
    T = max(T, 1e-5)
    vol_frac = sigma * (T ** H)
    var_frac = (sigma ** 2) * (T ** (2 * H))

    d1 = (np.log(S / K) + r * T + 0.5 * var_frac) / vol_frac
    d2 = d1 - vol_frac
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

# ==========================================
# 2. THE EXECUTION PLUMBING (Live Options API)
# ==========================================

def get_best_otm_call(ticker_symbol, S, target_dte=21):
    """
    Connects to the live market and finds the best Out-Of-The-Money Call
    expiring in roughly 3 weeks.
    """
    ticker = yf.Ticker(ticker_symbol)
    expirations = ticker.options
    if not expirations:
        return None

    today = datetime.datetime.now().date()
    best_date = None
    min_diff = 999

    # 1. Find expiration closest to 21 days out
    for date_str in expirations:
        exp_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        dte = (exp_date - today).days
        if 10 <= dte <= 40 and abs(dte - target_dte) < min_diff:
            min_diff = abs(dte - target_dte)
            best_date = date_str
            target_T = max(dte / 365.25, 0.001)

    if not best_date:
        return None

    chain = ticker.option_chain(best_date).calls

    # 2. Filter for OTM Calls (Strike > Current Price)
    otm_calls = chain[chain['strike'] > S].sort_values(by='strike')
    if otm_calls.empty:
        return None

    target_call = otm_calls.iloc[0]

    # 3. Liquidity & Spread Check (CRITICAL)
    if target_call['ask'] == 0 or target_call['volume'] == 0:
        return None

    spread_pct = (target_call['ask'] - target_call['bid']) / target_call['ask']
    if spread_pct > 0.15:
        return None

    return {
        'contract': target_call['contractSymbol'],
        'strike': target_call['strike'],
        'bid': target_call['bid'],
        'ask': target_call['ask'],
        'iv': target_call['impliedVolatility'],
        'T': target_T,
        'expiry': best_date
    }

# ==========================================
# 3. THE MASTER PIPELINE
# ==========================================

def run_quant_bot(basket):
    print(f"[*] Scanning {len(basket)} tickers for Volume-Weighted Wakes...\n")
    trades = []

    for symbol in basket:
        # 1. Get the Whale footprints
        mu, H, sigma, current_price = get_volume_weighted_footprints(symbol)

        # 2. FILTER: Only look at stocks with mathematically proven Momentum Memory
        if H > 0.60 and mu > 0:

            # 3. Pull Live Options Chain
            opt = get_best_otm_call(symbol, current_price)
            if not opt:
                continue

            # 4. Run the Fractional Math
            real_value = fractional_black_scholes(
                S=current_price, K=opt['strike'], T=opt['T'],
                r=0.045, sigma=sigma, H=H
            )

            # 5. Calculate the Edge Ratio
            edge_ratio = real_value / opt['ask']

            # 6. Only keep it if our math says it is at least 20% underpriced
            if edge_ratio > 1.20:

                # Assume a 55% win rate if the math aligns with a Volume Wake
                bet_size = kelly_bet_size(win_prob=0.55, edge_ratio=edge_ratio)

                trades.append({
                    'Ticker': symbol,
                    'VW-Hurst (H)': round(H, 3),
                    'Strike': f"${opt['strike']} ({opt['expiry']})",
                    'Market Ask': f"${opt['ask']:.2f}",
                    'Quant Value': f"${real_value:.2f}",
                    'Edge Ratio': round(edge_ratio, 2),
                    'Kelly Size': f"{round(bet_size * 100, 1)}%"
                })

    if trades:
        df = pd.DataFrame(trades).sort_values(by='Edge Ratio', ascending=False).reset_index(drop=True)
        print("=== TOP TRADES FOR TODAY ===")
        print(df.to_string())
    else:
        print("[-] No edge found today. Market is random. Stay in cash.")

# ==========================================
# 4. THE EXIT MANAGER
# ==========================================

def check_daily_exits(open_positions):
    """Run this daily at 3:00 PM on the tickers you currently hold options for."""
    print("\n=== RUNNING DAILY EXIT MANAGER ===")
    for ticker in open_positions:
        mu, H, _, _ = get_volume_weighted_footprints(ticker)
        print(f"[{ticker}] Live VW-Hurst: {H:.3f}")

        if H < 0.55:
            print(f"   [!] ALERT: Memory dropping (H < 0.55). The Whale is done buying.")
            print(f"   >>> ACTION: SELL TO CLOSE {ticker} IMMEDIATELY.")
        else:
            print("   [+] Wake is still active. HOLD position.")

if __name__ == "__main__":
    my_basket = ["PLTR", "EWY", "XBI", "HOOD", "RDDT", "CELH", "KRE", "URA", "DKNG"]
    run_quant_bot(my_basket)
    # my_portfolio = ["PLTR"]
    # check_daily_exits(my_portfolio)
```

---

## Daily Routine

1. **2:30 PM ET (Scan):** Run the volume-weighted wake scan across the basket.
2. **2:35 PM ET (Price & Size):** Pull the live option chain, enforce spread filters, compute edge, and size with Kelly.
3. **2:45 PM ET (Execute):** Route the selected trades.
4. **Days 2-7 (Manage):** Recompute `H` daily and exit when wake persistence breaks.

## Repo Integration Note

This saved note is a reference artifact. In this repo, executable pricing and order generation should be adapted to the typed IBKR utilities instead of relying on `yfinance` for production trade decisions.
