from __future__ import annotations

from typing import Any

from ibkr import get_smart_option_chain


class PricingToolError(RuntimeError):
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        super().__init__(payload.get("reason", "pricing tool failed"))


def build_failure_payload(
    identity: dict[str, Any],
    *,
    status: str,
    reason: str,
    used_fallback: bool = False,
    fallback_source: str | None = None,
    defaults: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **(defaults or {}),
        **identity,
        "status": status,
        "reason": reason,
        "used_fallback": used_fallback,
        "fallback_source": fallback_source,
    }
    payload.update(extra)
    return payload


def load_smart_chain_or_raise(
    ib,
    symbol: str,
    *,
    identity: dict[str, Any],
    defaults: dict[str, Any] | None = None,
    debug: bool = False,
):
    try:
        return get_smart_option_chain(ib, symbol, debug=debug)
    except Exception as exc:
        raise PricingToolError(
            build_failure_payload(
                identity,
                status="chain_unavailable",
                reason=f"No SMART option chain found for {symbol}: {type(exc).__name__}: {exc}",
                defaults=defaults,
            )
        ) from exc


def ensure_expiry_or_raise(
    chain,
    expiry: str,
    *,
    identity: dict[str, Any],
    defaults: dict[str, Any] | None = None,
    status: str = "expiry_unavailable",
    available_key: str = "available_expiries",
) -> None:
    if expiry not in chain.expirations:
        raise PricingToolError(
            build_failure_payload(
                identity,
                status=status,
                reason=f"Expiry {expiry} is not listed on the current SMART chain.",
                defaults=defaults,
                **{available_key: list(chain.expirations[:25])},
            )
        )


def ensure_strike_or_raise(
    chain,
    strike: float,
    *,
    identity: dict[str, Any],
    defaults: dict[str, Any] | None = None,
    status: str = "target_strike_unavailable",
    reason: str | None = None,
    available_key: str = "available_strikes",
) -> None:
    if strike not in chain.strikes:
        raise PricingToolError(
            build_failure_payload(
                identity,
                status=status,
                reason=reason or f"Strike {strike:.1f} is not listed on the current SMART chain.",
                defaults=defaults,
                **{available_key: [round(x, 2) for x in chain.strikes[:25]]},
            )
        )


def ensure_strikes_or_raise(
    chain,
    strikes: tuple[float, ...] | list[float],
    *,
    identity: dict[str, Any],
    defaults: dict[str, Any] | None = None,
    status: str = "target_strike_unavailable",
    reason: str = "One or more requested strikes are not listed on the current SMART chain.",
    available_key: str = "available_strikes",
) -> None:
    missing = [strike for strike in strikes if strike not in chain.strikes]
    if missing:
        raise PricingToolError(
            build_failure_payload(
                identity,
                status=status,
                reason=reason,
                defaults=defaults,
                missing_strikes=[round(x, 2) for x in missing],
                **{available_key: [round(x, 2) for x in chain.strikes[:30]]},
            )
        )
