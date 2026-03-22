"""
Helper utility for building BAG (Combo) order JSON payloads.
"""

import json
from datetime import datetime

def build_bag_json(
    symbol: str,
    description: str,
    notes: str,
    legs: list[dict],
    quantity: int,
    limit_price: float,
    action: str = "BUY",
    tif: str = "DAY",
    algo: str = "Adaptive",
    algo_priority: str = "Normal",
    exchange: str = "SMART",
    currency: str = "USD"
) -> str:
    """
    Constructs the JSON payload for a BAG order.
    
    legs format:
    [
        {"action": "BUY", "strike": 100.0, "right": "C", "expiry": "20261218", "ratio": 1},
        {"action": "SELL", "strike": 105.0, "right": "C", "expiry": "20261218", "ratio": 1}
    ]
    """
    
    order = {
        "description": description,
        "generated": datetime.now().strftime("%Y-%m-%d"),
        "notes": notes,
        "trades": [
            {
                "contract": {
                    "secType": "BAG",
                    "symbol": symbol,
                    "exchange": exchange,
                    "currency": currency,
                    "legs": legs
                },
                "action": action,
                "tif": tif,
                "algo": algo,
                "algoPriority": algo_priority,
                "tranches": [
                    {
                        "tranche": 1,
                        "quantity": quantity,
                        "lmtPrice": limit_price,
                        "note": description
                    }
                ]
            }
        ]
    }
    
    return json.dumps(order, indent=2)

def save_bag_order(filepath: str, **kwargs):
    """Generates and saves a BAG order JSON to the specified filepath."""
    json_str = build_bag_json(**kwargs)
    with open(filepath, 'w') as f:
        f.write(json_str)
    print(f"Saved BAG order proposal to {filepath}")
