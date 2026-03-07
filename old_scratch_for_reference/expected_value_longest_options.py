from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass
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


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0:
        return max(0.0, S - K)
    sigma = max(1e-8, sigma)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


def parse_nextjs_payload(html: str) -> str:
    segs = re.findall(r'self\.__next_f\.push\(\[\d+,"(.*?)"\]\)</script>', html, flags=re.S)
    if not segs:
        raise RuntimeError("Failed to parse Next.js payload.")
    return "".join(segs)


def fetch_tickertools_contract(symbol: str, contract_id: str) -> Dict[str, float | str]:
    url = f"https://tickertools.app/symbols/{symbol}/options/contracts/{contract_id}"
    html = requests.get(url, timeout=30).text
    payload = parse_nextjs_payload(html)
    start = payload.find(r"\"current\":")
    hist = payload.find(r",\"historical\":", start)
    if start < 0 or hist < 0:
        raise RuntimeError(f"Could not parse current quote from {url}")
    current = json.loads(bytes(payload[start + len(r"\"current\":") : hist], "utf-8").decode("unicode_escape"))
    return current


@dataclass
class OptionSnapshot:
    symbol: str
    contract_symbol: str
    expiry: str
    strike: float
    spot: float
    last: float
    bid: float
    ask: float
    mid: float
    iv: float
    volume: float
    open_interest: float
    currency: str
    quality_flag: str


def choose_longest_atm_call(symbol: str) -> OptionSnapshot:
    tkr = yf.Ticker(symbol)
    expiries = list(tkr.options)
    if not expiries:
        raise RuntimeError(f"No option expiries for {symbol}.")
    expiry = expiries[-1]
    spot = float(tkr.fast_info.get("lastPrice"))
    currency = str(tkr.fast_info.get("currency") or "USD")

    chain = tkr.option_chain(expiry)
    calls = chain.calls.copy()
    if calls.empty:
        raise RuntimeError(f"No call chain for {symbol} at {expiry}.")
    calls["dist"] = (calls["strike"] - spot).abs()
    atm = calls.sort_values("dist").iloc[0]
    contract = str(atm["contractSymbol"])

    current = fetch_tickertools_contract(symbol, contract)
    last = float(current["last"])
    bid = float(current["bid"])
    ask = float(current["ask"])
    mid = 0.5 * (bid + ask) if bid > 0 and ask > 0 else last
    quality = "bidask_mid" if bid > 0 and ask > 0 else "last_fallback"

    return OptionSnapshot(
        symbol=symbol,
        contract_symbol=contract,
        expiry=expiry,
        strike=float(current["strike"]),
        spot=float(current["underlying_price"]),
        last=last,
        bid=bid,
        ask=ask,
        mid=mid,
        iv=float(current["iv"]),
        volume=float(current["volume"]),
        open_interest=float(current["open_interest"]),
        currency=currency,
        quality_flag=quality,
    )


def ewma_vol(close: pd.Series, lam: float = 0.94) -> float:
    lr = np.log(close / close.shift(1)).dropna()
    var = float(lr.var())
    for x in lr:
        var = lam * var + (1.0 - lam) * float(x) ** 2
    return math.sqrt(max(var, 0.0) * 252.0)


def krx_json(payload: str) -> Dict[str, object]:
    cmd = [
        "curl",
        "-s",
        "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
        "-H",
        "User-Agent: Mozilla/5.0",
        "-H",
        "Referer: https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
        "--data",
        payload,
    ]
    raw = subprocess.check_output(cmd)
    return json.loads(raw)


def get_krx_sec_skh_status(trd_date: str = "20260226") -> pd.DataFrame:
    meta = krx_json(
        "bld=dbms/MDC/STAT/standard/MDCSTAT12801&locale=ko_KR&prodId=KRDRVOPEQU&subProdId=KRDRVOPEQU&csvxls_isNo=false"
    )["output"]
    quotes = krx_json(
        f"bld=dbms/MDC/STAT/standard/MDCSTAT12501&locale=ko_KR&trdDd={trd_date}&prodId=KRDRVOPEQU&mktTpCd=T&rghtTpCd=T"
    )["output"]

    meta_df = pd.DataFrame(meta)
    meta_df = meta_df[
        meta_df["ISU_ENG_NM"].str.startswith("SEC ") | meta_df["ISU_ENG_NM"].str.startswith("SKH ")
    ].copy()
    meta_df["underlying"] = np.where(meta_df["ISU_ENG_NM"].str.startswith("SEC "), "Samsung", "SKHynix")

    q_df = pd.DataFrame(quotes)[["ISU_CD", "TDD_CLSPRC", "SETL_PRC", "ACC_TRDVOL", "ACC_OPNINT_QTY"]].copy()
    m = meta_df.merge(q_df, on="ISU_CD", how="left")
    m["LSTTRD_DD"] = pd.to_datetime(m["LSTTRD_DD"])
    m["trdvol"] = pd.to_numeric(m["ACC_TRDVOL"].astype(str).str.replace(",", ""), errors="coerce").fillna(0.0)
    m["oi"] = pd.to_numeric(m["ACC_OPNINT_QTY"].astype(str).str.replace(",", ""), errors="coerce").fillna(0.0)
    return m


def get_ewy_weights() -> Dict[str, float]:
    html = requests.get("https://stockanalysis.com/etf/ewy/holdings/", timeout=30).text
    m1 = re.search(r'n:"Samsung Electronics Co\., Ltd\.",s:"!krx/005930",as:"([0-9.]+)%"', html)
    m2 = re.search(r'n:"SK hynix Inc\.",s:"!krx/000660",as:"([0-9.]+)%"', html)
    if not m1 or not m2:
        raise RuntimeError("Could not parse Samsung/SK hynix EWY weights.")
    w_sm = float(m1.group(1)) / 100.0
    w_sk = float(m2.group(1)) / 100.0
    return {"samsung": w_sm, "hynix": w_sk, "other": 1.0 - w_sm - w_sk}


def expected_roi_expiry(option: OptionSnapshot, move: float) -> float:
    terminal = option.spot * (1.0 + move)
    payoff = max(terminal - option.strike, 0.0)
    return (payoff - option.mid) / option.mid


def main() -> None:
    now = datetime.now(timezone.utc).date()
    r = 0.04

    ewy = choose_longest_atm_call("EWY")
    mu = choose_longest_atm_call("MU")

    # KRX status for Samsung/SK (availability/liquidity check)
    krx = get_krx_sec_skh_status("20260226")
    status_rows: List[Dict[str, object]] = []
    for name in ["Samsung", "SKHynix"]:
        sub = krx[krx["underlying"] == name].copy()
        longest = sub["LSTTRD_DD"].max()
        viable = sub[(sub["trdvol"] > 0) | (sub["oi"] > 0)]
        viable_longest = viable["LSTTRD_DD"].max() if not viable.empty else pd.NaT
        status_rows.append(
            {
                "underlying": name,
                "longest_listed_expiry": longest.date().isoformat(),
                "longest_viable_expiry": viable_longest.date().isoformat() if pd.notna(viable_longest) else "",
                "contracts_longest_listed": int((sub["LSTTRD_DD"] == longest).sum()),
                "contracts_with_liquidity": int(len(viable)),
            }
        )
    status_df = pd.DataFrame(status_rows)
    status_df.to_csv(OUTPUT_DIR / "krx_samsung_skh_option_status.csv", index=False)

    # Scenario engine: memory-cycle weighted EWY move + MU beta-to-memory move.
    weights = get_ewy_weights()
    w_mem_norm_sm = weights["samsung"] / (weights["samsung"] + weights["hynix"])
    w_mem_norm_sk = weights["hynix"] / (weights["samsung"] + weights["hynix"])

    # Estimate MU beta to memory-proxy return from history.
    mu_c = yf.Ticker("MU").history(period="2y")["Close"].dropna()
    sm_c = yf.Ticker("005930.KS").history(period="2y")["Close"].dropna()
    sk_c = yf.Ticker("000660.KS").history(period="2y")["Close"].dropna()
    for c in [mu_c, sm_c, sk_c]:
        c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    rets = pd.concat(
        [
            np.log(mu_c / mu_c.shift(1)).rename("mu"),
            np.log(sm_c / sm_c.shift(1)).rename("sm"),
            np.log(sk_c / sk_c.shift(1)).rename("sk"),
        ],
        axis=1,
        join="inner",
        sort=False,
    ).dropna()
    rets["mem"] = w_mem_norm_sm * rets["sm"] + w_mem_norm_sk * rets["sk"]
    if len(rets) < 30 or float(np.var(rets["mem"])) < 1e-10:
        beta_mu_mem = 1.20
    else:
        x = rets["mem"].values
        y = rets["mu"].values
        x_center = x - x.mean()
        beta_mu_mem = float((x_center @ y) / (x_center @ x_center))

    scenarios = [
        {"scenario": "Bear", "prob": 0.20, "sm": -0.20, "sk": -0.25, "other": -0.08},
        {"scenario": "Base Bull", "prob": 0.35, "sm": 0.40, "sk": 0.70, "other": 0.10},
        {"scenario": "Strong Bull", "prob": 0.30, "sm": 0.60, "sk": 1.00, "other": 0.12},
        {"scenario": "Supercycle", "prob": 0.15, "sm": 0.80, "sk": 1.30, "other": 0.15},
    ]
    rows: List[Dict[str, float | str]] = []
    for s in scenarios:
        mem_move = w_mem_norm_sm * s["sm"] + w_mem_norm_sk * s["sk"]
        ewy_move = weights["samsung"] * s["sm"] + weights["hynix"] * s["sk"] + weights["other"] * s["other"]
        mu_move = float(np.clip(beta_mu_mem * mem_move, -0.90, 3.00))

        rows.append(
            {
                "scenario": s["scenario"],
                "prob": s["prob"],
                "memory_combo_move": mem_move,
                "ewy_move": ewy_move,
                "mu_move": mu_move,
                "ewy_longest_call_roi_expiry": expected_roi_expiry(ewy, ewy_move),
                "mu_longest_call_roi_expiry": expected_roi_expiry(mu, mu_move),
            }
        )
    scen_df = pd.DataFrame(rows)
    scen_df.to_csv(OUTPUT_DIR / "expected_value_longest_options_scenarios.csv", index=False)

    ev_ewy = float((scen_df["prob"] * scen_df["ewy_longest_call_roi_expiry"]).sum())
    ev_mu = float((scen_df["prob"] * scen_df["mu_longest_call_roi_expiry"]).sum())
    prob_loss_ewy = float(scen_df.loc[scen_df["ewy_longest_call_roi_expiry"] < 0, "prob"].sum())
    prob_loss_mu = float(scen_df.loc[scen_df["mu_longest_call_roi_expiry"] < 0, "prob"].sum())

    # Optional synthetic proxies for Samsung/SK using longest viable KRX horizon (not LEAPS).
    spot_sm = float(yf.Ticker("005930.KS").history(period="5d")["Close"].dropna().iloc[-1])
    spot_sk = float(yf.Ticker("000660.KS").history(period="5d")["Close"].dropna().iloc[-1])
    sigma_sm = 1.10 * ewma_vol(yf.Ticker("005930.KS").history(period="1y")["Close"].dropna())
    sigma_sk = 1.10 * ewma_vol(yf.Ticker("000660.KS").history(period="1y")["Close"].dropna())

    viable_dates = status_df["longest_viable_expiry"].replace("", np.nan).dropna()
    if not viable_dates.empty:
        t_krx = (pd.to_datetime(viable_dates.max()).date() - now).days / 365.0
    else:
        t_krx = (pd.to_datetime(status_df["longest_listed_expiry"].max()).date() - now).days / 365.0
    t_krx = max(float(t_krx), 1e-6)

    prem_sm = bs_call_price(spot_sm, spot_sm, t_krx, r, sigma_sm)
    prem_sk = bs_call_price(spot_sk, spot_sk, t_krx, r, sigma_sk)

    syn_rows = []
    for s in scenarios:
        roi_sm = (max(spot_sm * (1.0 + s["sm"]) - spot_sm, 0.0) - prem_sm) / prem_sm
        roi_sk = (max(spot_sk * (1.0 + s["sk"]) - spot_sk, 0.0) - prem_sk) / prem_sk
        syn_rows.append({"scenario": s["scenario"], "prob": s["prob"], "samsung_synth_roi": roi_sm, "skhynix_synth_roi": roi_sk})
    syn_df = pd.DataFrame(syn_rows)
    syn_df.to_csv(OUTPUT_DIR / "expected_value_samsung_skh_synthetic.csv", index=False)

    ev_sm = float((syn_df["prob"] * syn_df["samsung_synth_roi"]).sum())
    ev_sk = float((syn_df["prob"] * syn_df["skhynix_synth_roi"]).sum())

    summary = pd.DataFrame(
        [
            {
                "instrument": f"EWY {ewy.contract_symbol}",
                "kind": "longest_listed_call",
                "expiry": ewy.expiry,
                "spot": ewy.spot,
                "strike": ewy.strike,
                "entry_mid": ewy.mid,
                "iv": ewy.iv,
                "volume": ewy.volume,
                "open_interest": ewy.open_interest,
                "quality_flag": ewy.quality_flag,
                "expected_roi_expiry": ev_ewy,
                "probability_of_loss": prob_loss_ewy,
            },
            {
                "instrument": f"MU {mu.contract_symbol}",
                "kind": "longest_listed_call",
                "expiry": mu.expiry,
                "spot": mu.spot,
                "strike": mu.strike,
                "entry_mid": mu.mid,
                "iv": mu.iv,
                "volume": mu.volume,
                "open_interest": mu.open_interest,
                "quality_flag": mu.quality_flag,
                "expected_roi_expiry": ev_mu,
                "probability_of_loss": prob_loss_mu,
            },
            {
                "instrument": "Samsung synthetic ATM call",
                "kind": "proxy_not_live_bidask",
                "expiry": viable_dates.max() if not viable_dates.empty else status_df["longest_listed_expiry"].max(),
                "spot": spot_sm,
                "strike": spot_sm,
                "entry_mid": prem_sm,
                "iv": sigma_sm,
                "volume": np.nan,
                "open_interest": np.nan,
                "quality_flag": "synthetic_proxy",
                "expected_roi_expiry": ev_sm,
                "probability_of_loss": float(syn_df.loc[syn_df["samsung_synth_roi"] < 0, "prob"].sum()),
            },
            {
                "instrument": "SK hynix synthetic ATM call",
                "kind": "proxy_not_live_bidask",
                "expiry": viable_dates.max() if not viable_dates.empty else status_df["longest_listed_expiry"].max(),
                "spot": spot_sk,
                "strike": spot_sk,
                "entry_mid": prem_sk,
                "iv": sigma_sk,
                "volume": np.nan,
                "open_interest": np.nan,
                "quality_flag": "synthetic_proxy",
                "expected_roi_expiry": ev_sk,
                "probability_of_loss": float(syn_df.loc[syn_df["skhynix_synth_roi"] < 0, "prob"].sum()),
            },
        ]
    )
    summary.to_csv(OUTPUT_DIR / "expected_value_longest_options_summary.csv", index=False)

    # Visualization
    plt.figure(figsize=(10, 6))
    display_df = summary[["instrument", "expected_roi_expiry"]].copy()
    plt.bar(display_df["instrument"], display_df["expected_roi_expiry"] * 100.0)
    plt.axhline(0, color="black", linewidth=1.0)
    plt.ylabel("Expected ROI at Expiry (%)")
    plt.title("Expected Return Comparison: Longest Options / Proxies")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "expected_value_longest_options_comparison.png", dpi=180)
    plt.close()

    # Report
    report = f"""# Expected Value Comparison (Longest Maturity Focus)

Generated UTC: {datetime.now(timezone.utc).isoformat(timespec="seconds")}

## What is live vs proxy
- EWY and MU: longest listed US option maturities with live contract snapshots.
- Samsung / SK hynix: KRX longest listed options are available, but longest tenors are currently illiquid in public snapshots; synthetic ATM call proxies are shown for directional torque only.

## Longest maturity discovered
- EWY longest expiry: {ewy.expiry}
- MU longest expiry: {mu.expiry}
- Samsung KRX longest listed expiry: {status_df.loc[status_df['underlying']=='Samsung','longest_listed_expiry'].iloc[0]}
- SK hynix KRX longest listed expiry: {status_df.loc[status_df['underlying']=='SKHynix','longest_listed_expiry'].iloc[0]}

## Expected ROI at expiry (scenario-weighted)
- EWY longest call: {ev_ewy:.2%} (loss-prob {prob_loss_ewy:.2%})
- MU longest call: {ev_mu:.2%} (loss-prob {prob_loss_mu:.2%})
- Samsung synthetic call: {ev_sm:.2%}
- SK hynix synthetic call: {ev_sk:.2%}

## Notes
- Scenario probabilities and moves are in `expected_value_longest_options_scenarios.csv`.
- KRX viability status is in `krx_samsung_skh_option_status.csv`.
- Synthetic proxies are not executable quotes; they are model placeholders when long-dated Korean chain liquidity is absent.
"""
    with open(OUTPUT_DIR / "expected_value_longest_options_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    print("=== Expected Value Longest-Maturity Analysis Complete ===")
    print(f"EWY longest: {ewy.contract_symbol} exp {ewy.expiry} mid {ewy.mid:.2f}")
    print(f"MU longest:  {mu.contract_symbol} exp {mu.expiry} mid {mu.mid:.2f}")
    print(f"Expected ROI (expiry): EWY {ev_ewy:.2%}, MU {ev_mu:.2%}, Samsung proxy {ev_sm:.2%}, SK hynix proxy {ev_sk:.2%}")
    print("Saved outputs to ./outputs/")


if __name__ == "__main__":
    main()
