"""
IBKR-backed CLI for building small price-discovery probe orders.

The logic lives in `stratoforge.pricing.probe`. This file only adapts IBKR quotes
into the shared proposal format and writes executor-ready JSON.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ib_insync import Option

from ibkr import (
    connect,
    get_option_quotes,
    get_smart_option_chain,
    get_spot,
    inspect_contract_market_data,
)
from stratoforge.pricing import price_option_probe
from stratoforge.pricing.models import OptionContractSpec, OptionMarketSnapshot
from stock_tooling.watch_rules import assess_watch_state, load_watch_rules


class ProbePricingError(RuntimeError):
    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(payload.get("reason", "probe pricing failed"))


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


def _failure_payload(
    *,
    symbol: str,
    expiry: str,
    strike: float,
    right: str,
    status: str,
    reason: str,
    used_fallback: bool = False,
    fallback_source: str | None = None,
    **extra,
) -> dict:
    payload = {
        "symbol": symbol,
        "expiry": expiry,
        "strike": strike,
        "right": right,
        "status": status,
        "reason": reason,
        "used_fallback": used_fallback,
        "fallback_source": fallback_source,
    }
    payload.update(extra)
    return payload


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
        chain = get_smart_option_chain(ib, symbol, debug=debug)
        if expiry not in chain.expirations:
            raise ProbePricingError(
                _failure_payload(
                    symbol=symbol,
                    expiry=expiry,
                    strike=strike,
                    right=right,
                    status="expiry_unavailable",
                    reason=f"Expiry {expiry} is not listed on the current SMART chain.",
                    available_expiries=list(chain.expirations[:25]),
                )
            )
        if strike not in chain.strikes:
            raise ProbePricingError(
                _failure_payload(
                    symbol=symbol,
                    expiry=expiry,
                    strike=strike,
                    right=right,
                    status="target_strike_unavailable",
                    reason=f"Strike {strike:.1f} is not listed on the current SMART chain.",
                    available_strikes=[round(x, 2) for x in chain.strikes[:25]],
                )
            )

        probe_contract = Option(symbol, expiry, strike, right, "SMART")
        quote_health = inspect_contract_market_data(
            ib,
            probe_contract,
            settle_secs=2.0,
            market_data_type=market_data_type,
        )
        if not quote_health.qualified:
            raise ProbePricingError(
                _failure_payload(
                    symbol=symbol,
                    expiry=expiry,
                    strike=strike,
                    right=right,
                    status="contract_unqualified",
                    reason="IBKR could not qualify the option contract.",
                    quote_health=asdict(quote_health),
                )
            )
        if not quote_health.has_two_sided_quote:
            raise ProbePricingError(
                _failure_payload(
                    symbol=symbol,
                    expiry=expiry,
                    strike=strike,
                    right=right,
                    status="quote_unavailable",
                    reason="IBKR did not return a usable two-sided quote for the probe contract.",
                    quote_health=asdict(quote_health),
                )
            )

        spot_source = "underlying_market"
        try:
            spot = get_spot(ib, symbol, debug=debug, allow_close_fallback=True)
        except Exception:
            if quote_health.spot > 0:
                spot = quote_health.spot
                spot_source = "option_model_underlying"
            else:
                raise ProbePricingError(
                    _failure_payload(
                        symbol=symbol,
                        expiry=expiry,
                        strike=strike,
                        right=right,
                        status="missing_underlying_price",
                        reason="Could not recover a usable underlying price from IBKR.",
                        quote_health=asdict(quote_health),
                    )
                )

        [quote] = get_option_quotes(ib, symbol, [(strike, expiry, right)], debug=debug)

        contract = OptionContractSpec(symbol=symbol, expiry=expiry, strike=strike, right=right)
        try:
            sigma = _require_implied_volatility(
                quote=quote,
                symbol=symbol,
                strike=strike,
                expiry=contract.expiry,
                right=contract.right,
                iv_override=iv_override,
            )
        except ValueError as exc:
            raise ProbePricingError(
                _failure_payload(
                    symbol=symbol,
                    expiry=expiry,
                    strike=strike,
                    right=right,
                    status="missing_iv",
                    reason=str(exc),
                    used_fallback=iv_override is not None,
                    fallback_source="manual_iv_override" if iv_override is not None else None,
                    quote_health=asdict(quote_health),
                )
            ) from exc
        market = OptionMarketSnapshot(
            spot=spot,
            bid=quote.bid,
            ask=quote.ask,
            last=quote.last,
            implied_volatility=sigma,
            risk_free_rate=r,
            dividend_yield=dividend_yield,
            source="ibkr",
            market_data_type=quote_health.market_data_type or market_data_type,
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
        payload["preflight"] = {
            "contract": asdict(quote_health),
            "spot_source": spot_source,
        }

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

    symbol_str = str(symbol).upper()
    expiry_str = str(expiry)
    strike_value = float(strike)
    right_str = str(right).upper()

    try:
        price_probe(
            symbol=symbol_str,
            expiry=expiry_str,
            strike=strike_value,
            right=right_str,
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
    except ProbePricingError as exc:
        print(json.dumps(exc.payload, indent=2))
        raise SystemExit(1) from exc
    except Exception as exc:
        status = "ibkr_connection_failed" if isinstance(exc, OSError) else "unexpected_error"
        print(json.dumps(
            _failure_payload(
                symbol=symbol_str,
                expiry=expiry_str,
                strike=strike_value,
                right=right_str,
                status=status,
                reason=f"{type(exc).__name__}: {exc}",
            ),
            indent=2,
        ))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
