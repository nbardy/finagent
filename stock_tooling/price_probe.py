"""
IBKR-backed CLI for building small price-discovery probe orders.

The logic lives in `option_pricing.probe`. This file only adapts IBKR quotes
into the shared proposal format and writes executor-ready JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibkr import connect, get_option_quotes, get_spot
from option_pricing import price_option_probe
from option_pricing.models import OptionContractSpec, OptionMarketSnapshot
from stock_tooling.watch_rules import assess_watch_state, load_watch_rules


def _parse_steps(raw: str | None) -> tuple[int, ...] | None:
    if not raw:
        return None
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(int(part))
    return tuple(values)


def _load_probe_config(path: str | None) -> dict:
    if not path:
        return {}
    config_path = Path(path)
    with config_path.open() as handle:
        payload = json.load(handle)
    return payload.get("probe", payload)


def _pick(cli_value, config_value):
    return cli_value if cli_value is not None else config_value


def _require_implied_volatility(quote, *, symbol: str, expiry: str, strike: float, right: str, iv_override: float | None) -> float:
    if iv_override is not None:
        return iv_override
    if quote.iv > 0:
        return quote.iv
    raise ValueError(
        f"Missing IBKR IV for {symbol} {expiry} {strike:.1f}{right}; "
        "provide --iv-override if you want to price this manually."
    )


def price_probe(
    symbol: str,
    expiry: str,
    strike: float,
    right: str,
    qty: int,
    probe_qty: int = 1,
    steps: tuple[int, ...] | None = None,
    r: float = 0.045,
    dividend_yield: float = 0.0,
    iv_override: float | None = None,
    market_data_type: int = 3,
    output_file: str = "probe_proposal.json",
    watch_rules_config: str | None = None,
    debug: bool = True,
) -> dict:
    with connect(client_id=14, market_data_type=market_data_type, debug=debug) as ib:
        spot = get_spot(ib, symbol, debug=debug)
        [quote] = get_option_quotes(ib, symbol, [(strike, expiry, right)], debug=debug)

        contract = OptionContractSpec(symbol=symbol, expiry=expiry, strike=strike, right=right)
        sigma = _require_implied_volatility(
            quote=quote,
            symbol=symbol,
            strike=strike,
            expiry=contract.expiry,
            right=contract.right,
            iv_override=iv_override,
        )
        market = OptionMarketSnapshot(
            spot=spot,
            bid=quote.bid,
            ask=quote.ask,
            last=quote.last,
            implied_volatility=sigma,
            risk_free_rate=r,
            dividend_yield=dividend_yield,
            source="ibkr",
            market_data_type=market_data_type,
        )
        payload = price_option_probe(
            contract=contract,
            market=market,
            total_qty=qty,
            probe_qty=probe_qty,
            steps=steps,
        )
        watch_rules = load_watch_rules(watch_rules_config)
        payload["watch_guidance"] = assess_watch_state(
            bid=payload["market"]["bid"],
            ask=payload["market"]["ask"],
            last=payload["market"]["last_price"],
            open_order_count=payload["probe_count"],
            new_fill_count=0,
            total_target_qty=payload["total_quantity"],
            observed_seconds=0.0,
            rules=watch_rules,
        )

        with open(output_file, "w") as handle:
            json.dump(payload, handle, indent=2)

        print(f"\n{symbol} {strike:.1f}{right.upper()} {contract.expiry}")
        print(
            f"Spot=${payload['spot_at_pricing']:.2f} "
            f"Quote=[{payload['market']['bid']:.2f} x {payload['market']['ask']:.2f}] "
            f"TV=${payload['metrics']['theoretical_value']:.2f}"
        )
        print(
            f"Anchor=${payload['anchor_price']:.2f} "
            f"HeldBack={payload['held_back_quantity']} "
            f"DataType={payload['quote_status']['market_data_type']}"
        )
        print("Probes:")
        for probe in payload["probes"]:
            print(
                f"  P{probe['probe']}: {probe['quantity']}x @ ${probe['lmtPrice']:.2f} "
                f"(+{probe['ticks_from_anchor']} ticks)"
            )
        guidance = payload["watch_guidance"]
        print(
            "Watch:"
            f" regime={guidance['liquidity_regime']}"
            f" confidence={guidance['confidence']:.2f}"
            f" poll={guidance['recommended_poll_seconds']:.0f}s"
            f" observe={guidance['recommended_observation_seconds']:.0f}s"
            f" action={guidance['suggested_action']}"
        )
        print(f"\nSaved to {output_file}")
        return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build probe orders from IBKR quotes")
    parser.add_argument("--config", default=None, help="Path to JSON config with a top-level 'probe' block or flat keys")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--expiry", default=None)
    parser.add_argument("--strike", default=None, type=float)
    parser.add_argument("--right", default=None)
    parser.add_argument("--qty", default=None, type=int)
    parser.add_argument("--probe-qty", type=int, default=None)
    parser.add_argument("--steps", default=None, help="Comma-separated tick offsets, e.g. 6,4,2,0")
    parser.add_argument("--iv", type=float, default=None, help="IV override (e.g. 0.45)")
    parser.add_argument("--risk-free", type=float, default=None)
    parser.add_argument("--dividend-yield", type=float, default=None)
    parser.add_argument("--market-data-type", type=int, default=None, help="1=live, 3=delayed, 4=delayed-frozen")
    parser.add_argument("--output", default=None)
    parser.add_argument("--watch-rules-config", default=None, help="Optional watch rules JSON path")
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Print detailed IBKR connection and quote diagnostics.",
    )
    args = parser.parse_args()

    cfg = _load_probe_config(args.config)
    symbol = _pick(args.symbol, cfg.get("symbol"))
    expiry = _pick(args.expiry, cfg.get("expiry"))
    strike = _pick(args.strike, cfg.get("strike"))
    right = _pick(args.right, cfg.get("right", "C"))
    qty = _pick(args.qty, cfg.get("qty"))
    probe_qty = _pick(args.probe_qty, cfg.get("probe_qty", 1))
    steps = _parse_steps(args.steps) if args.steps is not None else tuple(cfg.get("steps", [])) or None
    iv = _pick(args.iv, cfg.get("iv"))
    risk_free = _pick(args.risk_free, cfg.get("risk_free_rate", 0.045))
    dividend_yield = _pick(args.dividend_yield, cfg.get("dividend_yield", 0.0))
    market_data_type = _pick(args.market_data_type, cfg.get("market_data_type", 3))
    output = _pick(args.output, cfg.get("output", "probe_proposal.json"))
    watch_rules_config = _pick(args.watch_rules_config, cfg.get("watch_rules_config"))
    debug = _pick(args.debug, cfg.get("debug", True))

    missing = [
        name
        for name, value in {
            "symbol": symbol,
            "expiry": expiry,
            "strike": strike,
            "qty": qty,
        }.items()
        if value is None
    ]
    if missing:
        parser.error(f"missing required values: {', '.join(missing)}")

    price_probe(
        symbol=str(symbol).upper(),
        expiry=str(expiry),
        strike=float(strike),
        right=str(right).upper(),
        qty=int(qty),
        probe_qty=int(probe_qty),
        steps=steps,
        r=float(risk_free),
        dividend_yield=float(dividend_yield),
        iv_override=iv if iv is None else float(iv),
        market_data_type=int(market_data_type),
        output_file=str(output),
        watch_rules_config=watch_rules_config,
        debug=bool(debug),
    )


if __name__ == "__main__":
    main()
