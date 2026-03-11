from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "watch_rules.json"


@dataclass(frozen=True)
class WatchBand:
    name: str
    poll_seconds: float
    observation_seconds: float
    confidence: float
    max_spread_pct: float | None = None


@dataclass(frozen=True)
class WatchAdjustments:
    one_sided_market_penalty: float
    no_last_trade_penalty: float
    first_fill_bonus: float
    additional_fill_bonus: float
    fill_ratio_bonus: float


@dataclass(frozen=True)
class WatchThresholds:
    bulk_ready_confidence: float
    reprice_confidence: float
    do_not_force_confidence: float


@dataclass(frozen=True)
class WatchRules:
    bands: tuple[WatchBand, ...]
    adjustments: WatchAdjustments
    thresholds: WatchThresholds


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _load_payload(path: str | None) -> dict:
    config_path = Path(path) if path else DEFAULT_RULES_PATH
    with config_path.open() as handle:
        payload = json.load(handle)
    return payload.get("watch", payload)


def load_watch_rules(path: str | None = None) -> WatchRules:
    payload = _load_payload(path)
    bands = tuple(
        WatchBand(
            name=band["name"],
            max_spread_pct=band.get("max_spread_pct"),
            poll_seconds=float(band["poll_seconds"]),
            observation_seconds=float(band["observation_seconds"]),
            confidence=float(band["confidence"]),
        )
        for band in payload["bands"]
    )
    adjustments_payload = payload["adjustments"]
    thresholds_payload = payload["thresholds"]
    return WatchRules(
        bands=bands,
        adjustments=WatchAdjustments(
            one_sided_market_penalty=float(adjustments_payload["one_sided_market_penalty"]),
            no_last_trade_penalty=float(adjustments_payload["no_last_trade_penalty"]),
            first_fill_bonus=float(adjustments_payload["first_fill_bonus"]),
            additional_fill_bonus=float(adjustments_payload["additional_fill_bonus"]),
            fill_ratio_bonus=float(adjustments_payload["fill_ratio_bonus"]),
        ),
        thresholds=WatchThresholds(
            bulk_ready_confidence=float(thresholds_payload["bulk_ready_confidence"]),
            reprice_confidence=float(thresholds_payload["reprice_confidence"]),
            do_not_force_confidence=float(thresholds_payload["do_not_force_confidence"]),
        ),
    )


def _quote_quality(*, bid: float, ask: float) -> str:
    if bid > 0 and ask > 0:
        return "two_sided"
    if bid > 0 or ask > 0:
        return "one_sided"
    return "no_market"


def _spread_metrics(*, bid: float, ask: float, last: float) -> tuple[float | None, float | None]:
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
        if mid > 0:
            return ask - bid, (ask - bid) / mid
        return ask - bid, None
    if last > 0 and ask > 0:
        return ask - last, None
    if last > 0 and bid > 0:
        return last - bid, None
    return None, None


def _pick_band(spread_pct: float | None, rules: WatchRules) -> WatchBand:
    if spread_pct is None or math.isinf(spread_pct):
        return rules.bands[-1]
    for band in rules.bands:
        if band.max_spread_pct is None or spread_pct <= band.max_spread_pct:
            return band
    return rules.bands[-1]


def assess_watch_state(
    *,
    bid: float,
    ask: float,
    last: float,
    open_order_count: int,
    new_fill_count: int,
    new_fill_qty: float = 0.0,
    total_target_qty: float | None = None,
    observed_seconds: float = 0.0,
    rules: WatchRules | None = None,
) -> dict:
    rules = rules or load_watch_rules()
    quote_quality = _quote_quality(bid=bid, ask=ask)
    spread, spread_pct = _spread_metrics(bid=bid, ask=ask, last=last)
    band = _pick_band(spread_pct, rules)

    confidence = band.confidence
    signals: list[str] = [f"band:{band.name}"]

    if quote_quality != "two_sided":
        confidence -= rules.adjustments.one_sided_market_penalty
        signals.append(f"quality:{quote_quality}")

    if last <= 0:
        confidence -= rules.adjustments.no_last_trade_penalty
        signals.append("no_last_trade")

    fill_ratio = 0.0
    if total_target_qty and total_target_qty > 0:
        fill_ratio = min(new_fill_qty / total_target_qty, 1.0)

    if new_fill_count > 0:
        confidence += rules.adjustments.first_fill_bonus
        if new_fill_count > 1:
            confidence += (new_fill_count - 1) * rules.adjustments.additional_fill_bonus
        if fill_ratio > 0:
            confidence += fill_ratio * rules.adjustments.fill_ratio_bonus
        signals.append(f"new_fills:{new_fill_count}")
        if fill_ratio > 0:
            signals.append(f"fill_ratio:{fill_ratio:.2f}")

    confidence = _clamp(confidence)

    if new_fill_count > 0 and confidence >= rules.thresholds.bulk_ready_confidence:
        suggested_action = "bulk_ready"
    elif observed_seconds >= band.observation_seconds and confidence <= rules.thresholds.do_not_force_confidence:
        suggested_action = "do_not_force"
    elif observed_seconds >= band.observation_seconds and confidence <= rules.thresholds.reprice_confidence:
        suggested_action = "reprice_candidate"
    else:
        suggested_action = "keep_watching"

    if observed_seconds < band.observation_seconds:
        signals.append(f"watch_window_remaining:{max(band.observation_seconds - observed_seconds, 0):.0f}s")
    else:
        signals.append("watch_window_complete")

    return {
        "quote_quality": quote_quality,
        "liquidity_regime": band.name,
        "spread": None if spread is None else round(spread, 6),
        "spread_pct": None if spread_pct is None else round(spread_pct, 6),
        "confidence": round(confidence, 4),
        "recommended_poll_seconds": band.poll_seconds,
        "recommended_observation_seconds": band.observation_seconds,
        "observed_seconds": round(observed_seconds, 2),
        "open_order_count": open_order_count,
        "new_fill_count": new_fill_count,
        "new_fill_qty": round(new_fill_qty, 4),
        "suggested_action": suggested_action,
        "signals": signals,
    }
