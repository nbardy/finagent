import math
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple


def norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def black_scholes_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str,
) -> float:
    if T <= 0:
        if option_type == "C":
            return max(0.0, S - K)
        return max(0.0, K - S)

    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "C":
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    if option_type == "P":
        return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    raise ValueError("option_type must be 'C' or 'P'")


@dataclass(frozen=True)
class Contract:
    option_type: str
    strike: int

    @property
    def label(self) -> str:
        return f"{self.strike}{self.option_type}"


@dataclass(frozen=True)
class Scenario:
    move: float
    target_iv: float

    @property
    def label(self) -> str:
        return f"Move {self.move:+.0%}, IV {self.target_iv:.0%}"


def normalized_probs(values: Sequence[float], probs: Dict[float, float] | None) -> Dict[float, float]:
    if probs is None:
        p = 1.0 / len(values)
        return {v: p for v in values}

    out = {v: max(0.0, probs.get(v, 0.0)) for v in values}
    total = sum(out.values())
    if total <= 0:
        p = 1.0 / len(values)
        return {v: p for v in values}
    return {k: v / total for k, v in out.items()}


def main() -> None:
    # --------- Base assumptions (edit here) ---------
    S_entry = 148.60
    T_entry = 0.90
    days_forward = 30
    r = 0.04
    iv_entry = 0.47

    # Include calls, puts, or both
    option_types = ("C", "P")

    # Strike universe to scan
    strikes = list(range(130, 211, 5))

    # Scenario grid
    spot_moves = [-0.10, -0.05, 0.00, 0.05, 0.10, 0.15]
    iv_targets = [0.55, iv_entry + 0.10, 0.60]  # includes +10 vol points (57%)

    # Optional probability inputs for EV; if None, uniform weights are used.
    # Example:
    # move_probs = {-0.10: 0.05, -0.05: 0.10, 0.00: 0.20, 0.05: 0.30, 0.10: 0.25, 0.15: 0.10}
    # iv_probs = {0.55: 0.30, 0.57: 0.40, 0.60: 0.30}
    move_probs = None
    iv_probs = None

    # Safety gates for a risk-aware ranking
    # Candidates that fail either gate are excluded from the "Filtered Ranking".
    max_prob_negative_pnl = 0.40
    min_worst_case_roi = -20.0
    # ------------------------------------------------

    T_target = max(1e-9, T_entry - (days_forward / 365.0))

    contracts: List[Contract] = [Contract(t, k) for t in option_types for k in strikes]
    scenarios: List[Scenario] = [Scenario(m, iv) for m in spot_moves for iv in iv_targets]

    move_weights = normalized_probs(spot_moves, move_probs)
    iv_weights = normalized_probs(iv_targets, iv_probs)

    entry_cost: Dict[Contract, float] = {}
    for c in contracts:
        entry_cost[c] = black_scholes_price(S_entry, c.strike, T_entry, r, iv_entry, c.option_type) * 100.0

    # scenario_result[(scenario, contract)] = (pnl, roi)
    scenario_result: Dict[Tuple[Scenario, Contract], Tuple[float, float]] = {}

    # aggregate metrics per contract
    agg: Dict[Contract, Dict[str, float]] = {
        c: {
            "exp_pnl": 0.0,
            "min_roi": float("inf"),
            "max_roi": float("-inf"),
            "prob_negative_pnl": 0.0,
            "sum_roi": 0.0,
            "sum_pnl": 0.0,
            "n": 0.0,
        }
        for c in contracts
    }

    for s in scenarios:
        S_target = S_entry * (1.0 + s.move)
        s_weight = move_weights[s.move] * iv_weights[s.target_iv]

        for c in contracts:
            final_value = (
                black_scholes_price(S_target, c.strike, T_target, r, s.target_iv, c.option_type)
                * 100.0
            )
            pnl = final_value - entry_cost[c]
            roi = (pnl / entry_cost[c]) * 100.0 if entry_cost[c] > 0 else float("nan")

            scenario_result[(s, c)] = (pnl, roi)

            a = agg[c]
            a["exp_pnl"] += s_weight * pnl
            a["min_roi"] = min(a["min_roi"], roi)
            a["max_roi"] = max(a["max_roi"], roi)
            if pnl < 0:
                a["prob_negative_pnl"] += s_weight
            a["sum_roi"] += roi
            a["sum_pnl"] += pnl
            a["n"] += 1.0

    print("=== Setup ===")
    print(f"Entry spot: {S_entry:.2f}, Entry IV: {iv_entry:.0%}, r: {r:.2%}")
    print(f"Entry T: {T_entry:.3f}y, Target T: {T_target:.3f}y (after ~{days_forward} days)")
    print(f"Contracts scanned: {len(contracts)} ({option_types}, strikes {strikes[0]}..{strikes[-1]})")
    print(
        "Scenarios: "
        + ", ".join([f"{m:+.0%}" for m in spot_moves])
        + " moves x "
        + ", ".join([f"{iv:.0%}" for iv in iv_targets])
        + " IV"
    )

    print("\n=== Best ROI Per Scenario (Top 3) ===")
    for s in scenarios:
        ranked = sorted(
            (
                (c, scenario_result[(s, c)][0], scenario_result[(s, c)][1])
                for c in contracts
            ),
            key=lambda x: x[2],
            reverse=True,
        )
        top3 = ranked[:3]
        row = " | ".join(
            [f"{c.label}: ROI {roi:7.2f}% PnL ${pnl:8.2f}" for c, pnl, roi in top3]
        )
        print(f"{s.label:<24} -> {row}")

    print("\n=== Best Dollar PnL Per Scenario ===")
    for s in scenarios:
        best = max(
            (
                (c, scenario_result[(s, c)][0], scenario_result[(s, c)][1])
                for c in contracts
            ),
            key=lambda x: x[1],
        )
        c, pnl, roi = best
        print(f"{s.label:<24} -> {c.label}: PnL ${pnl:8.2f}, ROI {roi:7.2f}%")

    summary_rows = []
    for c in contracts:
        a = agg[c]
        avg_roi = a["sum_roi"] / a["n"]
        avg_pnl = a["sum_pnl"] / a["n"]
        exp_roi = (a["exp_pnl"] / entry_cost[c]) * 100.0 if entry_cost[c] > 0 else float("nan")
        summary_rows.append(
            {
                "contract": c,
                "entry": entry_cost[c],
                "exp_pnl": a["exp_pnl"],
                "exp_roi": exp_roi,
                "avg_pnl": avg_pnl,
                "avg_roi": avg_roi,
                "min_roi": a["min_roi"],
                "max_roi": a["max_roi"],
                "prob_negative_pnl": a["prob_negative_pnl"],
            }
        )

    print("\n=== Ranking By Expected ROI (probability-weighted) ===")
    print("(If move_probs/iv_probs are None, this is equal-weight across scenarios.)")
    for row in sorted(summary_rows, key=lambda x: x["exp_roi"], reverse=True)[:15]:
        c = row["contract"]
        print(
            f"{c.label:<6} Entry ${row['entry']:8.2f} | ExpROI {row['exp_roi']:7.2f}% | "
            f"ExpPnL ${row['exp_pnl']:8.2f} | MinROI {row['min_roi']:7.2f}% | MaxROI {row['max_roi']:7.2f}% | "
            f"ProbNeg {row['prob_negative_pnl']*100:6.2f}%"
        )

    for opt_type in option_types:
        print(f"\n=== Expected ROI Ranking ({opt_type} only) ===")
        filtered_rows = [row for row in summary_rows if row["contract"].option_type == opt_type]
        for row in sorted(filtered_rows, key=lambda x: x["exp_roi"], reverse=True)[:10]:
            c = row["contract"]
            print(
                f"{c.label:<6} Entry ${row['entry']:8.2f} | ExpROI {row['exp_roi']:7.2f}% | "
                f"ExpPnL ${row['exp_pnl']:8.2f} | MinROI {row['min_roi']:7.2f}% | MaxROI {row['max_roi']:7.2f}% | "
                f"ProbNeg {row['prob_negative_pnl']*100:6.2f}%"
            )

    print("\n=== Filtered Ranking (Expected ROI with Risk Gates) ===")
    print(
        f"Gates: ProbNeg <= {max_prob_negative_pnl*100:.1f}% and "
        f"WorstROI >= {min_worst_case_roi:.1f}%"
    )
    survivors = [
        row
        for row in summary_rows
        if row["prob_negative_pnl"] <= max_prob_negative_pnl and row["min_roi"] >= min_worst_case_roi
    ]
    if not survivors:
        print("No candidates pass the current gates. Loosen gates or change scenario probabilities.")
    else:
        for row in sorted(survivors, key=lambda x: x["exp_roi"], reverse=True)[:15]:
            c = row["contract"]
            print(
                f"{c.label:<6} Entry ${row['entry']:8.2f} | ExpROI {row['exp_roi']:7.2f}% | "
                f"ProbNeg {row['prob_negative_pnl']*100:6.2f}% | WorstROI {row['min_roi']:7.2f}% | "
                f"ExpPnL ${row['exp_pnl']:8.2f}"
            )

    print("\n=== Ranking By Worst-Case ROI (maximin) ===")
    for row in sorted(summary_rows, key=lambda x: x["min_roi"], reverse=True)[:10]:
        c = row["contract"]
        print(
            f"{c.label:<6} Entry ${row['entry']:8.2f} | WorstROI {row['min_roi']:7.2f}% | "
            f"ExpROI {row['exp_roi']:7.2f}%"
        )


if __name__ == "__main__":
    main()
