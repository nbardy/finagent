"""
Multi-Model Portfolio Scenario EV Analyzer.

Runs complex option hedges through Black-Scholes, Heston (stochastic volatility), 
and Variance Gamma (jump-diffusion) models to expose tail risks and model dependencies.

Usage:
    uv run python multi_model_ev.py --input analysis/2026-03-19/spy_hedges_input.json --macro analysis/2026-03-19/spy_macro_matrix.json
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stratoforge.pricing.black_scholes import option_price
from stratoforge.pricing.heston import heston_price, HestonParams
from stratoforge.pricing.variance_gamma import vg_price, VGParams
from helpers.urgent_hedge import load_macro_scenarios

# Default robust parameters for testing
DEFAULT_HESTON = HestonParams(v0=0.04, theta=0.04, kappa=2.0, xi=0.3, rho=-0.7)
DEFAULT_VG = VGParams(sigma=0.2, nu=0.1, theta=-0.1)

def dte_from_expiry(expiry: str) -> int:
    try:
        expiry_dt = datetime.strptime(expiry, "%Y%m%d").date()
        return max((expiry_dt - date.today()).days, 1)
    except ValueError:
        return 30

def price_leg(spot: float, strike: float, days_to_expiry: int, iv: float, right: str, model: str, r: float = 0.05) -> float:
    t = days_to_expiry / 365.0
    if t <= 0:
        if right.upper() == "C":
            return max(0.0, spot - strike)
        else:
            return max(0.0, strike - spot)
            
    if model == "heston":
        # Scale v0 roughly by the scenario IV
        hp = HestonParams(v0=iv**2, theta=DEFAULT_HESTON.theta, kappa=DEFAULT_HESTON.kappa, xi=DEFAULT_HESTON.xi, rho=DEFAULT_HESTON.rho)
        return heston_price(spot, strike, t, r, hp, right)
    elif model == "vg":
        vp = VGParams(sigma=iv, nu=DEFAULT_VG.nu, theta=DEFAULT_VG.theta)
        return vg_price(spot, strike, t, r, vp, right)
    else:
        return option_price(spot, strike, t, r, iv, right)

def run_cli():
    parser = argparse.ArgumentParser(description="Multi-Model EV Analyzer")
    parser.add_argument("--input", required=True, help="Input hedges JSON")
    parser.add_argument("--macro", required=True, help="Macro matrix JSON")
    args = parser.parse_args()

    with open(args.input) as f:
        hedges_config = json.load(f)
    
    macro = load_macro_scenarios(args.macro)
    
    # We use the macro reference spot if available, else the hedges config spot
    base_spot = float(macro.reference_spot) if macro.reference_spot else float(hedges_config.get("spot", 100.0))
    r = float(macro.risk_free_rate)
    
    # Extract hedges
    hedges = hedges_config.get("hedges", [])
    
    print("--- 3-MODEL EXPECTED VALUE (EV) STRESS TEST ---")
    print(f"Underlying: {macro.symbol} | Base Spot: {base_spot:.2f}\n")
    
    models = ["bs", "heston", "vg"]
    
    for model_name in models:
        print(f"[{model_name.upper()} MODEL]")
        
        # Initialize EV accumulators
        ev_totals = {h["name"]: 0.0 for h in hedges}
        
        for scenario in macro.scenarios:
            prob = scenario.probability
            days_passed = scenario.horizon_days
            scenario_spot = base_spot * (1.0 + scenario.spot_move_pct)
            
            # Print scenario header only on the first model (or skip if too noisy)
            
            for hedge in hedges:
                val = 0.0
                for leg in hedge["legs"]:
                    # Assume iv shift applies to leg iv or we just use base scenario vol if leg iv is missing
                    base_iv = float(leg.get("iv", 0.20))
                    iv = max(0.05, base_iv + scenario.vol_shift)
                    
                    dte = int(leg.get("dte", dte_from_expiry(leg.get("expiry", ""))))
                    remaining_dte = max(1, dte - days_passed)
                    
                    price = price_leg(
                        spot=scenario_spot, 
                        strike=float(leg["strike"]), 
                        days_to_expiry=remaining_dte, 
                        iv=iv, 
                        right=leg["right"], 
                        model=model_name, 
                        r=r
                    )
                    
                    val += price * 100.0 * float(leg["qty"])
                
                # Subtract entry cost (if provided, assume 0 for testing if omitted)
                entry_cost = float(hedge.get("entry_cost", 0.0))
                pnl = val - entry_cost
                
                ev_totals[hedge["name"]] += pnl * prob
                
        # Print results for this model
        for name, ev in ev_totals.items():
            print(f"  {name}: EV = ${ev:,.2f}")
        print("")

if __name__ == "__main__":
    run_cli()
