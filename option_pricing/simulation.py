from __future__ import annotations

import numpy as np


def mc_option_pnl(
    S: float,
    K: float,
    T: float,
    sigma: float,
    premium: float,
    is_long: bool = False,
    is_call: bool = True,
    n_paths: int = 25_000,
) -> tuple[float, float, float]:
    if T <= 0:
        if is_call:
            intrinsic = max(0.0, S - K)
        else:
            intrinsic = max(0.0, K - S)
        pnl = (intrinsic - premium) if is_long else (premium - intrinsic)
        return (1.0 if pnl > 0 else 0.0, pnl, pnl)

    Z = np.random.standard_normal(n_paths)
    S_T = S * np.exp((-0.5 * sigma**2) * T + sigma * np.sqrt(T) * Z)

    if is_call:
        intrinsic = np.maximum(0.0, S_T - K)
    else:
        intrinsic = np.maximum(0.0, K - S_T)

    pnl = intrinsic - premium if is_long else premium - intrinsic
    return float(np.mean(pnl > 0)), float(np.mean(pnl)), float(np.percentile(pnl, 5))
