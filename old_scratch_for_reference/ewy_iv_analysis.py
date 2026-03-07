from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import yfinance as yf


OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0:
        return max(0.0, S - K)
    sigma = max(1e-6, sigma)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


def black_scholes_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0:
        return max(0.0, K - S)
    sigma = max(1e-6, sigma)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def _decode_nextjs_contract_payload(html: str) -> str:
    segments = re.findall(
        r'self\.__next_f\.push\(\[\d+,"(.*?)"\]\)</script>',
        html,
        flags=re.S,
    )
    if not segments:
        raise RuntimeError("Could not parse Next.js payload segments from TickerTools response.")
    return "".join(segments)


def fetch_tickertools_contract(contract_id: str) -> Tuple[Dict[str, str], pd.DataFrame]:
    url = f"https://tickertools.app/symbols/EWY/options/contracts/{contract_id}"
    html = requests.get(url, timeout=30).text
    payload = _decode_nextjs_contract_payload(html)

    key_current = r"\"current\":"
    key_hist = r",\"historical\":"
    key_related = r",\"related\":"

    i_current = payload.find(key_current)
    i_hist = payload.find(key_hist, i_current)
    i_related = payload.find(key_related, i_hist)
    if min(i_current, i_hist, i_related) < 0:
        raise RuntimeError(f"Could not locate current/historical keys for {contract_id}.")

    current_raw = payload[i_current + len(key_current) : i_hist]
    hist_raw = payload[i_hist + len(key_hist) : i_related]

    current = json.loads(bytes(current_raw, "utf-8").decode("unicode_escape"))
    historical = pd.DataFrame(json.loads(bytes(hist_raw, "utf-8").decode("unicode_escape")))

    if historical.empty:
        raise RuntimeError(f"No historical rows for {contract_id}.")

    numeric_cols = [
        "last",
        "bid",
        "ask",
        "volume",
        "open_interest",
        "underlying_price",
        "iv",
        "delta",
        "gamma",
        "theta",
        "vega",
    ]
    for col in numeric_cols:
        if col in historical.columns:
            historical[col] = pd.to_numeric(historical[col], errors="coerce")

    historical["data_date"] = pd.to_datetime(historical["data_date"])
    historical = historical.sort_values("data_date").reset_index(drop=True)
    return current, historical


def ewma_annualized_vol(log_returns: pd.Series, lam: float = 0.94) -> float:
    variance = float(log_returns.var())
    for r in log_returns:
        variance = lam * variance + (1.0 - lam) * float(r) ** 2
    return math.sqrt(max(variance, 0.0) * 252.0)


def get_realized_vol_stats(symbol: str) -> Dict[str, float]:
    closes = yf.Ticker(symbol).history(period="1y")["Close"].dropna()
    log_returns = np.log(closes / closes.shift(1)).dropna()
    if len(log_returns) < 60:
        raise RuntimeError(f"Insufficient history for {symbol} vol stats.")

    rv20 = float(log_returns.tail(20).std() * math.sqrt(252.0))
    rv60 = float(log_returns.tail(60).std() * math.sqrt(252.0))
    rv252 = float(log_returns.std() * math.sqrt(252.0))
    ewma = ewma_annualized_vol(log_returns)
    return {
        "spot": float(closes.iloc[-1]),
        "rv20": rv20,
        "rv60": rv60,
        "rv252": rv252,
        "ewma": ewma,
    }


def get_ewy_memory_weights() -> Dict[str, float]:
    html = requests.get("https://stockanalysis.com/etf/ewy/holdings/", timeout=30).text

    samsung_match = re.search(
        r'n:"Samsung Electronics Co\., Ltd\.",s:"!krx/005930",as:"([0-9.]+)%"',
        html,
    )
    hynix_match = re.search(
        r'n:"SK hynix Inc\.",s:"!krx/000660",as:"([0-9.]+)%"',
        html,
    )
    date_match = re.search(r'date:"([A-Za-z]{3} [0-9]{1,2}, [0-9]{4})"', html)

    if not samsung_match or not hynix_match:
        raise RuntimeError("Could not parse Samsung/SK hynix weights from stockanalysis EWY holdings.")

    w_samsung = float(samsung_match.group(1)) / 100.0
    w_hynix = float(hynix_match.group(1)) / 100.0
    return {
        "samsung": w_samsung,
        "hynix": w_hynix,
        "other": max(0.0, 1.0 - w_samsung - w_hynix),
        "as_of": date_match.group(1) if date_match else "Unknown",
    }


def expected_iv_mean_reversion(
    current_iv: float,
    long_run_iv: float,
    kappa: float,
    tenor_years: float,
    variance_risk_premium: float = 0.0,
) -> float:
    """Simple Ornstein-Uhlenbeck-style variance mean reversion approximation."""
    cur_var = max(current_iv, 1e-8) ** 2
    long_var = max(long_run_iv, 1e-8) ** 2
    base_var = long_var + (cur_var - long_var) * math.exp(-kappa * max(tenor_years, 0.0))
    adj_var = base_var * (1.0 + variance_risk_premium)
    return math.sqrt(max(adj_var, 1e-12))


def basket_ewy_move(
    samsung_move: float,
    hynix_move: float,
    w_samsung: float,
    w_hynix: float,
    w_other: float,
    other_beta_to_memory: float,
) -> float:
    """
    Estimate EWY move from top-2 memory names plus a correlated move from the rest basket.
    other_beta_to_memory:
      - 0.0 -> remaining basket assumed flat
      - >0 -> remaining basket co-moves with weighted memory move
    """
    memory_weight = max(w_samsung + w_hynix, 1e-8)
    memory_combo = (w_samsung * samsung_move + w_hynix * hynix_move) / memory_weight
    other_move = other_beta_to_memory * memory_combo
    return w_samsung * samsung_move + w_hynix * hynix_move + w_other * other_move


@dataclass
class TradeLeg:
    contract_id: str
    strike: float
    option_type: str
    bid: float
    ask: float
    last: float
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    volume: float
    open_interest: float
    underlying_price: float
    data_date: datetime
    expiration: datetime

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return 0.5 * (self.bid + self.ask)
        return self.last


def build_leg(contract_id: str, strike: float, option_type: str) -> TradeLeg:
    current, _ = fetch_tickertools_contract(contract_id)
    return TradeLeg(
        contract_id=contract_id,
        strike=strike,
        option_type=option_type,
        bid=float(current["bid"]),
        ask=float(current["ask"]),
        last=float(current["last"]),
        iv=float(current["iv"]),
        delta=float(current["delta"]),
        gamma=float(current["gamma"]),
        theta=float(current["theta"]),
        vega=float(current["vega"]),
        volume=float(current["volume"]),
        open_interest=float(current["open_interest"]),
        underlying_price=float(current["underlying_price"]),
        data_date=datetime.strptime(current["data_date"], "%Y-%m-%d"),
        expiration=datetime.strptime(current["expiration"], "%Y-%m-%d"),
    )


def main() -> None:
    # Contracts used:
    # 145C/145P for historical ATM-proxy IV trend
    # 150C/140P for user-requested strangle pricing
    c145_current, c145_hist = fetch_tickertools_contract("EWY280121C00145000")
    p145_current, p145_hist = fetch_tickertools_contract("EWY280121P00145000")

    c150 = build_leg("EWY280121C00150000", 150.0, "call")
    p140 = build_leg("EWY280121P00140000", 140.0, "put")

    # 1) Historical IV chart (ATM proxy from 145C/145P)
    iv_hist = c145_hist[["data_date", "iv"]].rename(columns={"iv": "iv_145c"}).merge(
        p145_hist[["data_date", "iv"]].rename(columns={"iv": "iv_145p"}),
        on="data_date",
        how="inner",
    )
    iv_hist["iv_proxy"] = 0.5 * (iv_hist["iv_145c"] + iv_hist["iv_145p"])
    iv_hist["iv_proxy_pct"] = iv_hist["iv_proxy"] * 100.0

    iv_start = float(iv_hist["iv_proxy"].iloc[0])
    iv_end = float(iv_hist["iv_proxy"].iloc[-1])
    iv_change_abs = iv_end - iv_start
    iv_change_pct = (iv_change_abs / iv_start) * 100.0

    iv_hist.to_csv(OUTPUT_DIR / "ewy_iv_history_145_proxy.csv", index=False)

    plt.figure(figsize=(11, 6))
    plt.plot(iv_hist["data_date"], iv_hist["iv_145c"] * 100, label="145C IV")
    plt.plot(iv_hist["data_date"], iv_hist["iv_145p"] * 100, label="145P IV")
    plt.plot(iv_hist["data_date"], iv_hist["iv_proxy_pct"], label="ATM Proxy IV (avg)", linewidth=2.5)
    plt.title("EWY 2028 LEAP IV History (145C/145P Proxy)")
    plt.ylabel("Implied Volatility (%)")
    plt.xlabel("Date")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ewy_iv_history.png", dpi=180)
    plt.close()

    # 2) Expected IV from MM-style formulas vs actual
    ewy_vol = get_realized_vol_stats("EWY")
    rv20 = ewy_vol["rv20"]
    rv252 = ewy_vol["rv252"]
    ewma = ewy_vol["ewma"]

    iv_expected_ewma_vrp = 1.12 * ewma
    iv_expected_blend = 1.08 * math.sqrt(0.7 * rv20**2 + 0.3 * rv252**2)
    iv_actual_atm_proxy = 0.5 * (float(c145_current["iv"]) + float(p145_current["iv"]))
    iv_actual_trade = 0.5 * (c150.iv + p140.iv)
    iv_expected_mean_revert_base = expected_iv_mean_reversion(
        current_iv=iv_actual_atm_proxy,
        long_run_iv=0.35,
        kappa=1.0,
        tenor_years=1.90,  # approx tenor to Jan 2028
        variance_risk_premium=0.10,
    )

    iv_compare = pd.DataFrame(
        [
            {"metric": "Actual ATM proxy IV (145C/145P)", "value": iv_actual_atm_proxy},
            {"metric": "Actual trade IV avg (150C/140P)", "value": iv_actual_trade},
            {"metric": "Expected IV: EWMA + VRP (1.12x)", "value": iv_expected_ewma_vrp},
            {"metric": "Expected IV: Mean-revert blend (1.08x)", "value": iv_expected_blend},
            {"metric": "Expected IV: Mean-revert variance model", "value": iv_expected_mean_revert_base},
        ]
    )
    iv_compare["value_pct"] = iv_compare["value"] * 100.0
    iv_compare.to_csv(OUTPUT_DIR / "ewy_iv_expected_vs_actual.csv", index=False)

    plt.figure(figsize=(11, 6))
    bars = plt.bar(iv_compare["metric"], iv_compare["value_pct"])
    plt.title("EWY Actual vs Model-Expected IV")
    plt.ylabel("IV (%)")
    plt.xticks(rotation=20, ha="right")
    for bar in bars:
        y = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2, y + 0.25, f"{y:.1f}%", ha="center", va="bottom")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ewy_expected_vs_actual_iv.png", dpi=180)
    plt.close()

    # 2b) Rolling realized volatility context (what feeds expected-IV math)
    ewy_close_2y = yf.Ticker("EWY").history(period="2y")["Close"].dropna()
    ewy_lr_2y = np.log(ewy_close_2y / ewy_close_2y.shift(1)).dropna()
    rolling_vol = pd.DataFrame(index=ewy_lr_2y.index)
    rolling_vol["rv20"] = ewy_lr_2y.rolling(20).std() * math.sqrt(252.0)
    rolling_vol["rv60"] = ewy_lr_2y.rolling(60).std() * math.sqrt(252.0)
    rolling_vol["rv252"] = ewy_lr_2y.rolling(252).std() * math.sqrt(252.0)
    rolling_vol = rolling_vol.dropna().reset_index().rename(columns={"Date": "date", "index": "date"})
    if "date" not in rolling_vol.columns:
        rolling_vol = rolling_vol.rename(columns={rolling_vol.columns[0]: "date"})
    rolling_vol.to_csv(OUTPUT_DIR / "ewy_realized_vol_rolling.csv", index=False)

    plt.figure(figsize=(11, 6))
    plt.plot(rolling_vol["date"], rolling_vol["rv20"] * 100, label="RV20")
    plt.plot(rolling_vol["date"], rolling_vol["rv60"] * 100, label="RV60")
    plt.plot(rolling_vol["date"], rolling_vol["rv252"] * 100, label="RV252")
    plt.axhline(iv_actual_atm_proxy * 100, color="black", linestyle="--", linewidth=1.5, label="Current ATM Proxy IV")
    plt.title("EWY Realized Volatility Regimes vs Current LEAP IV")
    plt.ylabel("Annualized Volatility (%)")
    plt.xlabel("Date")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ewy_realized_vol_regimes.png", dpi=180)
    plt.close()

    # 2c) Mean-reversion expected-IV model surfaces (regime scenarios)
    tenor_grid = np.array([0.25, 0.50, 1.00, 1.50, 2.00, 3.00])
    regime_defs = [
        {"regime": "Low structural vol", "long_run_iv": 0.30, "kappa": 1.30, "vrp": 0.08},
        {"regime": "Mid structural vol", "long_run_iv": 0.38, "kappa": 1.00, "vrp": 0.10},
        {"regime": "High structural vol", "long_run_iv": 0.48, "kappa": 0.70, "vrp": 0.12},
    ]

    mr_rows = []
    for reg in regime_defs:
        for tenor in tenor_grid:
            exp_iv = expected_iv_mean_reversion(
                current_iv=iv_actual_atm_proxy,
                long_run_iv=reg["long_run_iv"],
                kappa=reg["kappa"],
                tenor_years=float(tenor),
                variance_risk_premium=reg["vrp"],
            )
            mr_rows.append(
                {
                    "regime": reg["regime"],
                    "tenor_years": float(tenor),
                    "long_run_iv": reg["long_run_iv"],
                    "kappa": reg["kappa"],
                    "vrp": reg["vrp"],
                    "expected_iv": exp_iv,
                }
            )
    mr_df = pd.DataFrame(mr_rows)
    mr_df.to_csv(OUTPUT_DIR / "ewy_mean_reversion_iv_term_structure.csv", index=False)

    plt.figure(figsize=(11, 6))
    for reg in regime_defs:
        reg_df = mr_df[mr_df["regime"] == reg["regime"]].sort_values("tenor_years")
        plt.plot(reg_df["tenor_years"], reg_df["expected_iv"] * 100, marker="o", label=reg["regime"])
    plt.axhline(iv_actual_atm_proxy * 100, color="black", linestyle="--", linewidth=1.5, label="Current ATM Proxy IV")
    plt.title("EWY Expected IV by Tenor (Mean-Reversion Variance Model)")
    plt.xlabel("Tenor (Years)")
    plt.ylabel("Expected IV (%)")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ewy_mean_reversion_term_structure.png", dpi=180)
    plt.close()

    theta_grid = np.arange(0.25, 0.61, 0.05)
    kappa_grid = np.arange(0.30, 2.01, 0.10)
    heat = np.zeros((len(kappa_grid), len(theta_grid)))
    for i, kappa in enumerate(kappa_grid):
        for j, theta_iv in enumerate(theta_grid):
            heat[i, j] = expected_iv_mean_reversion(
                current_iv=iv_actual_atm_proxy,
                long_run_iv=float(theta_iv),
                kappa=float(kappa),
                tenor_years=2.0,
                variance_risk_premium=0.10,
            )
    heat_df = pd.DataFrame(
        heat,
        index=[f"k={k:.2f}" for k in kappa_grid],
        columns=[f"theta={t:.2f}" for t in theta_grid],
    )
    heat_df.to_csv(OUTPUT_DIR / "ewy_mean_reversion_iv_heatmap_2y.csv")

    plt.figure(figsize=(11, 7))
    im = plt.imshow(heat * 100, aspect="auto", origin="lower", cmap="viridis")
    plt.colorbar(im, label="Expected 2Y IV (%)")
    plt.xticks(np.arange(len(theta_grid)), [f"{x:.0%}" for x in theta_grid], rotation=30, ha="right")
    plt.yticks(np.arange(len(kappa_grid))[::2], [f"{k:.1f}" for k in kappa_grid[::2]])
    plt.xlabel("Long-Run IV (theta)")
    plt.ylabel("Mean-Reversion Speed (kappa)")
    plt.title("EWY Expected 2Y IV Surface (10% Variance Risk Premium)")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ewy_mean_reversion_heatmap_2y.png", dpi=180)
    plt.close()

    # 3) Strangle pricing (150C + 140P)
    debit = c150.mid + p140.mid
    upper_be = c150.strike + debit
    lower_be = p140.strike - debit
    net_delta = c150.delta + p140.delta
    net_gamma = c150.gamma + p140.gamma
    net_theta = c150.theta + p140.theta
    net_vega = c150.vega + p140.vega

    days_to_exp = (c150.expiration - c150.data_date).days
    T_now = max(days_to_exp / 365.0, 1e-6)
    T_30d = max(T_now - (30.0 / 365.0), 1e-6)
    r = 0.04
    S0 = c150.underlying_price

    def mtm_value(spot: float) -> float:
        call_v = black_scholes_call(spot, c150.strike, T_30d, r, c150.iv)
        put_v = black_scholes_put(spot, p140.strike, T_30d, r, p140.iv)
        return call_v + put_v

    mtm_up_10 = mtm_value(S0 * 1.10)
    mtm_dn_10 = mtm_value(S0 * 0.90)
    mtm_flat = mtm_value(S0)

    strangle_summary = {
        "spot": S0,
        "as_of": c150.data_date.strftime("%Y-%m-%d"),
        "expiration": c150.expiration.strftime("%Y-%m-%d"),
        "days_to_exp": days_to_exp,
        "call_150_bid": c150.bid,
        "call_150_ask": c150.ask,
        "call_150_volume": c150.volume,
        "call_150_open_interest": c150.open_interest,
        "call_150_mid": c150.mid,
        "put_140_bid": p140.bid,
        "put_140_ask": p140.ask,
        "put_140_volume": p140.volume,
        "put_140_open_interest": p140.open_interest,
        "put_140_mid": p140.mid,
        "net_debit": debit,
        "max_loss_per_contract_usd": debit * 100.0,
        "break_even_upper": upper_be,
        "break_even_lower": lower_be,
        "net_delta": net_delta,
        "net_gamma": net_gamma,
        "net_theta_per_year": net_theta,
        "net_vega_per_1pt_iv": net_vega / 100.0,
        "est_30d_mtm_up10pct_usd": (mtm_up_10 - debit) * 100.0,
        "est_30d_mtm_dn10pct_usd": (mtm_dn_10 - debit) * 100.0,
        "est_30d_mtm_flat_usd": (mtm_flat - debit) * 100.0,
    }

    # 4) EWY LEAP return vs Samsung/SK hynix LEAP-style scenarios
    weights = get_ewy_memory_weights()

    # 4a) Basket sensitivity: what EWY move is implied by Samsung/SK hynix moves
    sm_move_grid = np.arange(-0.20, 0.201, 0.05)
    hy_move_grid = np.arange(-0.20, 0.201, 0.05)
    basket_rows = []
    heat_flat = np.zeros((len(hy_move_grid), len(sm_move_grid)))
    heat_corr = np.zeros((len(hy_move_grid), len(sm_move_grid)))

    for i, hy_move in enumerate(hy_move_grid):
        for j, sm_move in enumerate(sm_move_grid):
            ewy_flat = basket_ewy_move(
                samsung_move=float(sm_move),
                hynix_move=float(hy_move),
                w_samsung=weights["samsung"],
                w_hynix=weights["hynix"],
                w_other=weights["other"],
                other_beta_to_memory=0.0,
            )
            ewy_corr = basket_ewy_move(
                samsung_move=float(sm_move),
                hynix_move=float(hy_move),
                w_samsung=weights["samsung"],
                w_hynix=weights["hynix"],
                w_other=weights["other"],
                other_beta_to_memory=0.35,
            )
            heat_flat[i, j] = ewy_flat
            heat_corr[i, j] = ewy_corr
            basket_rows.append(
                {
                    "samsung_move": float(sm_move),
                    "sk_hynix_move": float(hy_move),
                    "ewy_move_flat_rest": ewy_flat,
                    "ewy_move_correlated_rest_beta_0p35": ewy_corr,
                }
            )

    basket_df = pd.DataFrame(basket_rows)
    basket_df.to_csv(OUTPUT_DIR / "ewy_basket_sensitivity_grid.csv", index=False)

    # User-highlighted scenarios where both move together at +5% and +10%
    basket_together = pd.DataFrame(
        [
            {
                "scenario": "+5% Samsung & +5% SK hynix",
                "ewy_move_flat_rest": basket_ewy_move(0.05, 0.05, weights["samsung"], weights["hynix"], weights["other"], 0.0),
                "ewy_move_correlated_rest_beta_0p35": basket_ewy_move(0.05, 0.05, weights["samsung"], weights["hynix"], weights["other"], 0.35),
            },
            {
                "scenario": "+10% Samsung & +10% SK hynix",
                "ewy_move_flat_rest": basket_ewy_move(0.10, 0.10, weights["samsung"], weights["hynix"], weights["other"], 0.0),
                "ewy_move_correlated_rest_beta_0p35": basket_ewy_move(0.10, 0.10, weights["samsung"], weights["hynix"], weights["other"], 0.35),
            },
        ]
    )
    basket_together.to_csv(OUTPUT_DIR / "ewy_basket_simple_5_10pct.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True, constrained_layout=True)
    axes[0].imshow(heat_flat * 100, origin="lower", aspect="auto", cmap="coolwarm", vmin=-15, vmax=15)
    im1 = axes[1].imshow(heat_corr * 100, origin="lower", aspect="auto", cmap="coolwarm", vmin=-15, vmax=15)
    axes[0].set_title("EWY Move (%) | Rest Basket Flat")
    axes[1].set_title("EWY Move (%) | Rest Basket Beta 0.35")
    for ax in axes:
        ax.set_xlabel("Samsung Move")
        ax.set_xticks(np.arange(len(sm_move_grid))[::2])
        ax.set_xticklabels([f"{x:.0%}" for x in sm_move_grid[::2]], rotation=30, ha="right")
    axes[0].set_ylabel("SK hynix Move")
    axes[0].set_yticks(np.arange(len(hy_move_grid))[::2])
    axes[0].set_yticklabels([f"{x:.0%}" for x in hy_move_grid[::2]])
    fig.colorbar(im1, ax=axes, label="Estimated EWY Move (%)")
    plt.savefig(OUTPUT_DIR / "ewy_basket_sensitivity_heatmap.png", dpi=180)
    plt.close()

    sm_stats = get_realized_vol_stats("005930.KS")
    sk_stats = get_realized_vol_stats("000660.KS")

    # Synthetic ATM LEAP assumptions for single names (no U.S. listed LEAP chain available).
    sigma_sm = min(1.0, max(0.20, 1.05 * sm_stats["ewma"]))
    sigma_sk = min(1.0, max(0.20, 1.05 * sk_stats["ewma"]))
    prem_sm = black_scholes_call(sm_stats["spot"], sm_stats["spot"], T_now, r, sigma_sm)
    prem_sk = black_scholes_call(sk_stats["spot"], sk_stats["spot"], T_now, r, sigma_sk)

    scenarios = [
        ("Base Bull", 0.40, 0.70, 0.10),
        ("Strong Bull", 0.60, 1.00, 0.12),
        ("Supercycle", 0.80, 1.30, 0.15),
    ]
    rows = []
    for name, r_sm, r_sk, r_other in scenarios:
        r_ewy = (
            weights["samsung"] * r_sm
            + weights["hynix"] * r_sk
            + weights["other"] * r_other
        )
        S_ewy_T = S0 * (1.0 + r_ewy)
        ewy_payoff = max(S_ewy_T - c150.strike, 0.0)
        ewy_roi = (ewy_payoff - c150.mid) / c150.mid

        sm_payoff = max(sm_stats["spot"] * (1.0 + r_sm) - sm_stats["spot"], 0.0)
        sk_payoff = max(sk_stats["spot"] * (1.0 + r_sk) - sk_stats["spot"], 0.0)
        sm_roi = (sm_payoff - prem_sm) / prem_sm
        sk_roi = (sk_payoff - prem_sk) / prem_sk

        rows.append(
            {
                "scenario": name,
                "samsung_move": r_sm,
                "sk_hynix_move": r_sk,
                "other_ewy_move": r_other,
                "implied_ewy_move": r_ewy,
                "ewy_150c_roi": ewy_roi,
                "samsung_atm_call_roi": sm_roi,
                "sk_hynix_atm_call_roi": sk_roi,
            }
        )

    scenario_df = pd.DataFrame(rows)
    scenario_df.to_csv(OUTPUT_DIR / "ewy_vs_memory_leap_returns.csv", index=False)

    plt.figure(figsize=(11, 6))
    x = np.arange(len(scenario_df))
    width = 0.25
    plt.bar(x - width, scenario_df["ewy_150c_roi"] * 100, width, label="EWY 150C (actual)")
    plt.bar(x, scenario_df["samsung_atm_call_roi"] * 100, width, label="Samsung ATM LEAP (synthetic)")
    plt.bar(x + width, scenario_df["sk_hynix_atm_call_roi"] * 100, width, label="SK hynix ATM LEAP (synthetic)")
    plt.xticks(x, scenario_df["scenario"])
    plt.ylabel("Return (%)")
    plt.title("LEAP Return Comparison Under Memory Scenarios")
    plt.legend()
    plt.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ewy_vs_memory_leap_returns.png", dpi=180)
    plt.close()

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "iv_history": {
            "start_date": iv_hist["data_date"].iloc[0].strftime("%Y-%m-%d"),
            "end_date": iv_hist["data_date"].iloc[-1].strftime("%Y-%m-%d"),
            "iv_start": iv_start,
            "iv_end": iv_end,
            "iv_change_abs": iv_change_abs,
            "iv_change_pct": iv_change_pct,
        },
        "iv_expected_vs_actual": {
            "actual_atm_proxy_iv": iv_actual_atm_proxy,
            "actual_trade_iv_avg": iv_actual_trade,
            "expected_ewma_vrp": iv_expected_ewma_vrp,
            "expected_blend": iv_expected_blend,
            "expected_mean_revert_variance_model": iv_expected_mean_revert_base,
            "gap_vs_ewma_vrp": iv_actual_atm_proxy - iv_expected_ewma_vrp,
            "gap_vs_blend": iv_actual_atm_proxy - iv_expected_blend,
            "gap_vs_mean_revert_variance_model": iv_actual_atm_proxy - iv_expected_mean_revert_base,
        },
        "strangle_150c_140p": strangle_summary,
        "weights_used": weights,
        "basket_examples": {
            row["scenario"]: {
                "ewy_move_flat_rest": float(row["ewy_move_flat_rest"]),
                "ewy_move_correlated_rest_beta_0p35": float(row["ewy_move_correlated_rest_beta_0p35"]),
            }
            for _, row in basket_together.iterrows()
        },
        "mean_reversion_regimes": regime_defs,
        "single_name_synthetic_iv": {
            "samsung": sigma_sm,
            "sk_hynix": sigma_sk,
        },
    }
    with open(OUTPUT_DIR / "ewy_analysis_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    report = f"""# EWY IV + LEAP Research Pack

Generated: {summary["generated_at_utc"]}

## 1) Historical IV (EWY 2028 proxy)
- Window: {summary["iv_history"]["start_date"]} to {summary["iv_history"]["end_date"]}
- ATM proxy IV (145C/145P avg): {summary["iv_history"]["iv_start"]:.2%} -> {summary["iv_history"]["iv_end"]:.2%}
- Change: {summary["iv_history"]["iv_change_abs"]:+.2%} ({summary["iv_history"]["iv_change_pct"]:+.1f}%)

## 2) Expected IV model comparison
Core formula used for mean reversion:
- expected_var(T) = theta_var + (current_var - theta_var) * exp(-kappa * T)
- expected_iv(T) = sqrt(expected_var(T) * (1 + VRP))

Values:
- Actual ATM proxy IV: {summary["iv_expected_vs_actual"]["actual_atm_proxy_iv"]:.2%}
- Expected IV (EWMA + VRP): {summary["iv_expected_vs_actual"]["expected_ewma_vrp"]:.2%}
- Expected IV (Blend): {summary["iv_expected_vs_actual"]["expected_blend"]:.2%}
- Expected IV (Mean-revert model): {summary["iv_expected_vs_actual"]["expected_mean_revert_variance_model"]:.2%}

## 3) Basket concentration math (Samsung + SK hynix)
Weights (as of {weights["as_of"]}):
- Samsung: {weights["samsung"]:.2%}
- SK hynix: {weights["hynix"]:.2%}
- Combined top-2: {weights["samsung"] + weights["hynix"]:.2%}

Simple same-direction scenarios:
- +5% / +5% (flat rest): {basket_together.iloc[0]["ewy_move_flat_rest"]:.2%}
- +10% / +10% (flat rest): {basket_together.iloc[1]["ewy_move_flat_rest"]:.2%}
- +5% / +5% (correlated rest beta=0.35): {basket_together.iloc[0]["ewy_move_correlated_rest_beta_0p35"]:.2%}
- +10% / +10% (correlated rest beta=0.35): {basket_together.iloc[1]["ewy_move_correlated_rest_beta_0p35"]:.2%}

## 4) Trade pricing: 2028-01-21 150C + 140P strangle
- Spot: {strangle_summary["spot"]:.2f}
- Net debit: ${strangle_summary["net_debit"]:.2f} (${strangle_summary["max_loss_per_contract_usd"]:.0f}/contract)
- Break-evens: {strangle_summary["break_even_lower"]:.2f} / {strangle_summary["break_even_upper"]:.2f}
- Net Greeks: delta {strangle_summary["net_delta"]:+.3f}, gamma {strangle_summary["net_gamma"]:+.4f}, theta {strangle_summary["net_theta_per_year"]:+.2f}/yr, vega {strangle_summary["net_vega_per_1pt_iv"]:+.3f} per +1 vol point
- Liquidity: 150C vol/OI = {strangle_summary["call_150_volume"]:.0f}/{strangle_summary["call_150_open_interest"]:.0f}; 140P vol/OI = {strangle_summary["put_140_volume"]:.0f}/{strangle_summary["put_140_open_interest"]:.0f}

## 5) LEAP return scenarios (EWY vs memory single-names)
See `ewy_vs_memory_leap_returns.csv` and `ewy_vs_memory_leap_returns.png`.

## Output files
- ewy_analysis_summary.json
- ewy_analysis_report.md
- ewy_iv_history.png
- ewy_expected_vs_actual_iv.png
- ewy_realized_vol_regimes.png
- ewy_mean_reversion_term_structure.png
- ewy_mean_reversion_heatmap_2y.png
- ewy_basket_sensitivity_heatmap.png
- ewy_vs_memory_leap_returns.png
"""
    with open(OUTPUT_DIR / "ewy_analysis_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    print("=== EWY Analysis Complete ===")
    print(f"IV proxy range: {summary['iv_history']['start_date']} -> {summary['iv_history']['end_date']}")
    print(
        "IV proxy change: "
        f"{summary['iv_history']['iv_start']:.2%} -> {summary['iv_history']['iv_end']:.2%} "
        f"({summary['iv_history']['iv_change_abs']:+.2%}, {summary['iv_history']['iv_change_pct']:+.1f}%)"
    )
    print("\nExpected vs Actual IV:")
    print(
        f"  Actual ATM proxy IV: {iv_actual_atm_proxy:.2%}\n"
        f"  Expected (EWMA+VRP): {iv_expected_ewma_vrp:.2%}\n"
        f"  Expected (Blend): {iv_expected_blend:.2%}\n"
        f"  Expected (Mean-revert model): {iv_expected_mean_revert_base:.2%}"
    )
    print("\n150C + 140P (2028-01-21) strangle:")
    print(
        f"  Net debit: ${debit:.2f} ({debit*100:.0f} USD/contract)\n"
        f"  Break-evens at expiry: {lower_be:.2f} / {upper_be:.2f}\n"
        f"  Net Greeks: delta {net_delta:+.3f}, gamma {net_gamma:+.4f}, "
        f"theta {net_theta:+.2f}/yr, vega {net_vega:+.2f}"
    )
    print("\nBasket math (flat rest):")
    print(
        f"  +5% Samsung/+5% SK hynix -> EWY {basket_together.iloc[0]['ewy_move_flat_rest']:+.2%}\n"
        f"  +10% Samsung/+10% SK hynix -> EWY {basket_together.iloc[1]['ewy_move_flat_rest']:+.2%}"
    )
    print("\nSaved outputs to ./outputs/")


if __name__ == "__main__":
    main()
