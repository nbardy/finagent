from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import yfinance as yf


OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
PRIMARY_PREDICTED_MODEL = "model_ewma_vrp"


def parse_nextjs_payload(html: str) -> str:
    segs = re.findall(r'self\.__next_f\.push\(\[\d+,"(.*?)"\]\)</script>', html, flags=re.S)
    if not segs:
        raise RuntimeError("Unable to parse Next.js payload.")
    return "".join(segs)


def fetch_tickertools_history(symbol: str, contract_id: str) -> tuple[Dict[str, str], pd.DataFrame]:
    url = f"https://tickertools.app/symbols/{symbol}/options/contracts/{contract_id}"
    html = requests.get(url, timeout=30).text
    payload = parse_nextjs_payload(html)
    i_cur = payload.find(r"\"current\":")
    i_hist = payload.find(r",\"historical\":", i_cur)
    i_rel = payload.find(r",\"related\":", i_hist)
    if min(i_cur, i_hist, i_rel) < 0:
        raise RuntimeError(f"Unable to parse {contract_id}")
    current = json.loads(bytes(payload[i_cur + len(r"\"current\":") : i_hist], "utf-8").decode("unicode_escape"))
    hist = json.loads(bytes(payload[i_hist + len(r",\"historical\":") : i_rel], "utf-8").decode("unicode_escape"))
    df = pd.DataFrame(hist)
    df["data_date"] = pd.to_datetime(df["data_date"])
    for col in ["iv", "last", "bid", "ask", "delta", "gamma", "theta", "vega", "underlying_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("data_date").reset_index(drop=True)
    return current, df


def expected_iv_mean_reversion(
    current_iv: float,
    long_run_iv: float,
    kappa: float,
    tenor_years: float,
    vrp: float,
) -> float:
    cur_var = max(current_iv, 1e-8) ** 2
    long_var = max(long_run_iv, 1e-8) ** 2
    exp_var = long_var + (cur_var - long_var) * math.exp(-kappa * max(tenor_years, 0.0))
    return math.sqrt(max(exp_var * (1.0 + vrp), 1e-12))


def ewma_vol(log_returns: np.ndarray, lam: float = 0.94) -> float:
    if len(log_returns) == 0:
        return float("nan")
    var = float(np.var(log_returns))
    for x in log_returns:
        var = lam * var + (1.0 - lam) * float(x) ** 2
    return math.sqrt(max(var, 0.0) * 252.0)


def qlike(actual_vol: np.ndarray, forecast_vol: np.ndarray) -> float:
    av = np.maximum(actual_vol**2, 1e-12)
    fv = np.maximum(forecast_vol**2, 1e-12)
    return float(np.mean(np.log(fv) + av / fv))


def main() -> None:
    # 1) "Actual IV" in this workflow:
    # EWY ATM proxy from 145C/145P average. (We label it as Actual IV in outputs for clarity.)
    _, c145 = fetch_tickertools_history("EWY", "EWY280121C00145000")
    _, p145 = fetch_tickertools_history("EWY", "EWY280121P00145000")
    iv = c145[["data_date", "iv"]].rename(columns={"iv": "iv_145c"}).merge(
        p145[["data_date", "iv"]].rename(columns={"iv": "iv_145p"}),
        on="data_date",
        how="inner",
    )
    iv["actual_iv"] = 0.5 * (iv["iv_145c"] + iv["iv_145p"])
    iv = iv.sort_values("data_date").reset_index(drop=True)

    # 2) Build long-horizon expected-IV model panel over time.
    close_ewy = yf.Ticker("EWY").history(period="5y")["Close"].dropna()
    close_ewy.index = pd.to_datetime(close_ewy.index).tz_localize(None).normalize()
    log_ret = np.log(close_ewy / close_ewy.shift(1)).dropna()
    log_ret.index = pd.to_datetime(log_ret.index).tz_localize(None).normalize()

    rows: List[Dict[str, float | str]] = []
    for dt, actual_iv in zip(iv["data_date"], iv["actual_iv"]):
        hist = log_ret[log_ret.index <= dt].dropna()
        if len(hist) < 260:
            continue
        r20 = float(np.std(hist.tail(20), ddof=1) * math.sqrt(252.0))
        r60 = float(np.std(hist.tail(60), ddof=1) * math.sqrt(252.0))
        r252 = float(np.std(hist.tail(252), ddof=1) * math.sqrt(252.0))
        ew = ewma_vol(hist.values, lam=0.94)

        model_ewma_vrp = 1.12 * ew
        model_blend = 1.08 * math.sqrt(0.7 * r20**2 + 0.3 * r252**2)
        model_mr = expected_iv_mean_reversion(r20, r252, kappa=1.0, tenor_years=2.0, vrp=0.10)

        # Simple regime blend driven by short-vs-long realized spread.
        z = (r20 - r252) / max(r252, 1e-6)
        p_high = 1.0 / (1.0 + math.exp(-6.0 * z))
        mr_low = expected_iv_mean_reversion(r20, 0.30, kappa=1.3, tenor_years=2.0, vrp=0.08)
        mr_high = expected_iv_mean_reversion(r20, 0.50, kappa=0.7, tenor_years=2.0, vrp=0.12)
        model_regime = (1.0 - p_high) * mr_low + p_high * mr_high

        rows.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "actual_iv": float(actual_iv),
                "rv20": r20,
                "rv60": r60,
                "rv252": r252,
                "model_ewma_vrp": model_ewma_vrp,
                "model_blend": model_blend,
                "model_mean_revert": model_mr,
                "model_regime_blend": model_regime,
                "regime_high_prob": p_high,
            }
        )

    panel = pd.DataFrame(rows)
    panel["date"] = pd.to_datetime(panel["date"])

    model_cols = ["model_ewma_vrp", "model_blend", "model_mean_revert", "model_regime_blend"]
    err_rows = []
    for m in model_cols:
        e = panel["actual_iv"] - panel[m]
        err_rows.append(
            {
                "model": m,
                "rmse": float(np.sqrt(np.mean(e**2))),
                "mae": float(np.mean(np.abs(e))),
                "bias": float(np.mean(e)),
                "qlike": qlike(panel["actual_iv"].values, panel[m].values),
            }
        )
    err_df = pd.DataFrame(err_rows).sort_values("rmse")
    err_df.to_csv(OUTPUT_DIR / "ewy_iv_model_error_metrics.csv", index=False)
    best_model = str(err_df.iloc[0]["model"])
    panel["predicted_iv"] = panel[PRIMARY_PREDICTED_MODEL]
    panel["predicted_model"] = PRIMARY_PREDICTED_MODEL
    panel["iv_mispricing"] = panel["actual_iv"] - panel["predicted_iv"]
    panel["iv_mispricing_vol_pts"] = panel["iv_mispricing"] * 100.0
    roll_mean = panel["iv_mispricing"].rolling(60, min_periods=20).mean()
    roll_std = panel["iv_mispricing"].rolling(60, min_periods=20).std()
    panel["iv_mispricing_z60"] = (panel["iv_mispricing"] - roll_mean) / roll_std.replace(0.0, np.nan)
    panel.to_csv(OUTPUT_DIR / "ewy_iv_model_panel_long_horizon.csv", index=False)

    # 3) Charts
    # Primary: Actual IV vs Predicted IV (fixed ex-ante model for mispricing)
    plt.figure(figsize=(12, 6))
    plt.plot(panel["date"], panel["actual_iv"] * 100, label="Actual IV", linewidth=2.4)
    plt.plot(
        panel["date"],
        panel["predicted_iv"] * 100,
        label=f"Predicted IV ({PRIMARY_PREDICTED_MODEL}, fixed ex-ante)",
        linewidth=2.0,
    )
    plt.title("EWY Actual IV vs Predicted IV")
    plt.ylabel("IV (%)")
    plt.xlabel("Date")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ewy_actual_vs_predicted_iv.png", dpi=180)
    plt.close()

    plt.figure(figsize=(12, 5))
    plt.plot(panel["date"], panel["iv_mispricing_vol_pts"], label="Mispricing = Actual IV - Predicted IV", linewidth=2.0)
    plt.axhline(0.0, color="black", linewidth=1.0)
    plt.title("EWY IV Mispricing Signal")
    plt.ylabel("Vol Points")
    plt.xlabel("Date")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ewy_iv_mispricing_signal.png", dpi=180)
    plt.close()

    # Secondary: full model panel diagnostics
    plt.figure(figsize=(12, 6))
    plt.plot(panel["date"], panel["actual_iv"] * 100, label="Actual IV", linewidth=2.2)
    plt.plot(panel["date"], panel["model_ewma_vrp"] * 100, label="Predicted: EWMA+VRP")
    plt.plot(panel["date"], panel["model_blend"] * 100, label="Blend")
    plt.plot(panel["date"], panel["model_mean_revert"] * 100, label="Mean-Revert")
    plt.plot(panel["date"], panel["model_regime_blend"] * 100, label="Regime Blend")
    plt.title("EWY Actual IV vs Multiple Predicted IV Models")
    plt.ylabel("IV (%)")
    plt.xlabel("Date")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ewy_iv_models_over_time.png", dpi=180)
    plt.close()

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    axes[0].bar(err_df["model"], err_df["rmse"] * 100)
    axes[0].set_title("Model RMSE")
    axes[0].set_ylabel("Vol Pts")
    axes[0].tick_params(axis="x", rotation=25)
    axes[1].bar(err_df["model"], err_df["mae"] * 100)
    axes[1].set_title("Model MAE")
    axes[1].set_ylabel("Vol Pts")
    axes[1].tick_params(axis="x", rotation=25)
    plt.savefig(OUTPUT_DIR / "ewy_iv_model_error_metrics.png", dpi=180)
    plt.close()

    # 4) Basket-item IV proxy track (component realized -> implied proxy).
    w_sm = 0.2855
    w_sk = 0.1974
    w_mem = w_sm + w_sk
    w_sm_n = w_sm / w_mem
    w_sk_n = w_sk / w_mem

    ewy_close = yf.Ticker("EWY").history(period="2y")["Close"].dropna().rename("ewy")
    sm_close = yf.Ticker("005930.KS").history(period="2y")["Close"].dropna().rename("samsung")
    sk_close = yf.Ticker("000660.KS").history(period="2y")["Close"].dropna().rename("skhynix")
    for c in [ewy_close, sm_close, sk_close]:
        c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    px = pd.concat([ewy_close, sm_close, sk_close], axis=1, join="inner", sort=False).dropna()
    lr = np.log(px / px.shift(1)).dropna()

    out = pd.DataFrame(index=lr.index)
    out["rv_ewy_60"] = lr["ewy"].rolling(60).std() * math.sqrt(252.0)
    out["rv_sm_60"] = lr["samsung"].rolling(60).std() * math.sqrt(252.0)
    out["rv_sk_60"] = lr["skhynix"].rolling(60).std() * math.sqrt(252.0)
    out["corr_sm_sk_60"] = lr["samsung"].rolling(60).corr(lr["skhynix"])
    out = out.dropna()
    out["rv_memory_bucket_60"] = np.sqrt(
        w_sm_n**2 * out["rv_sm_60"] ** 2
        + w_sk_n**2 * out["rv_sk_60"] ** 2
        + 2.0 * w_sm_n * w_sk_n * out["corr_sm_sk_60"] * out["rv_sm_60"] * out["rv_sk_60"]
    )
    out["iv_memory_bucket_proxy"] = 1.10 * out["rv_memory_bucket_60"]
    out = out.reset_index().rename(columns={"Date": "date", "index": "date"})
    if "date" not in out.columns:
        out = out.rename(columns={out.columns[0]: "date"})
    out["date"] = pd.to_datetime(out["date"])

    comp = panel[["date", "actual_iv"]].merge(out[["date", "iv_memory_bucket_proxy"]], on="date", how="inner")
    comp.to_csv(OUTPUT_DIR / "ewy_memory_bucket_iv_proxy_timeseries.csv", index=False)

    plt.figure(figsize=(12, 6))
    plt.plot(comp["date"], comp["actual_iv"] * 100, label="EWY Actual IV")
    plt.plot(comp["date"], comp["iv_memory_bucket_proxy"] * 100, label="Memory Bucket IV proxy (Samsung/SK)")
    plt.title("EWY IV vs Memory-Bucket IV Proxy Over Time")
    plt.ylabel("IV (%)")
    plt.xlabel("Date")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ewy_memory_vs_ewy_iv_proxy.png", dpi=180)
    plt.close()

    # 5) Data requirements / methodology note.
    note = f"""# IV Calculation and Historical Data Requirements

Generated UTC: {datetime.now(timezone.utc).isoformat(timespec="seconds")}

## What data is needed to calculate implied volatility (IV)
For each option contract and date:
- Underlying spot `S_t`
- Strike `K`
- Time to expiry `T`
- Risk-free rate term `r(T)`
- Dividend yield or forward carry `q(T)` (or use forward directly)
- Option market price (preferably mid from bid/ask)
- Option type (call/put)

Then solve `sigma` in Black-Scholes such that model price matches market price.

## Historical data needed for expected-IV models
- EWY daily close history (for realized vol and regime state)
- Historical EWY option IV series (in this script: ATM proxy from 145C/145P average)
- Optional: risk-free term curve history and dividend expectations

## Models mapped over time in this script
- EWMA + variance risk premium
- Blend model using RV20 and RV252
- Mean-reversion variance model
- Regime-blend model (low/high structural vol blend)

## Mispricing definition used
- Predicted IV is fixed ex-ante as `{PRIMARY_PREDICTED_MODEL}` (no in-sample winner switching).
- Mispricing = Actual IV - Predicted IV.
- Positive mispricing means actual options-implied IV is above model-implied IV.

## Index IV vs basket-item IV
- True decomposition requires component option IV time series.
- If component option IV is unavailable, proxy with realized vol * VRP multiplier.
- This script includes Samsung/SK realized-vol-derived memory-bucket IV proxy versus EWY IV.
"""
    with open(OUTPUT_DIR / "ewy_iv_data_requirements.md", "w", encoding="utf-8") as f:
        f.write(note)

    print("=== Long-Horizon IV Expansion Analysis Complete ===")
    print(f"Panel rows: {len(panel)}")
    print("Best model by RMSE:", best_model, f"({err_df.iloc[0]['rmse']:.4f})")
    print("Primary predicted IV model (fixed ex-ante):", PRIMARY_PREDICTED_MODEL)
    print("Saved outputs to ./outputs/")


if __name__ == "__main__":
    main()
