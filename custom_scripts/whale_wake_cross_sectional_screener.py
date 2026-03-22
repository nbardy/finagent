from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
from ib_insync import Stock

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibkr import connect, get_account_summary, get_open_orders, get_option_quotes, get_portfolio, get_spot
from stratoforge.pricing.limits import recommend_limit, tranche_ladder
from stratoforge.pricing.models import OptionContractSpec, dte_and_time_to_expiry


REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = REPO_ROOT / "analysis"
ORDERS_ROOT = REPO_ROOT / "orders"
STRATEGY_KEY = "whale_wake_cross_sectional_screener"
DEFAULT_BASKET = ("PLTR", "EWY", "XBI", "HOOD", "RDDT", "CELH", "KRE", "URA", "DKNG")
DEFAULT_EARNINGS_PATH = REPO_ROOT / "config" / "earnings_blackout.json"


@dataclass(frozen=True)
class WhaleWakeConfig:
    strategy_key: str
    scan_time_et: str
    exit_check_time_et: str
    lookback_days: int
    min_hurst_entry: float
    min_hurst_exit: float
    min_positive_drift: float
    min_edge_ratio: float
    max_spread_pct: float
    target_dte: int
    min_dte: int
    max_dte: int
    expiry_search_count: int
    strike_search_count: int
    earnings_blackout_days: int
    assumed_win_prob: float
    max_trade_risk_pct: float
    risk_free_rate: float
    market_data_type: int
    settle_secs: float
    skip_symbols_with_open_orders: bool
    universe: tuple[str, ...]
    data_policy: str
    execution_policy: str


@dataclass(frozen=True)
class FootprintMetrics:
    mu: float
    hurst: float
    sigma: float
    spot: float
    bar_count: int
    avg_volume: float


@dataclass(frozen=True)
class OptionCandidate:
    symbol: str
    expiry: str
    strike: float
    right: str
    bid: float
    ask: float
    mid: float
    iv: float
    dte: int
    time_to_expiry: float
    spread_pct: float
    theoretical_value: float
    suggested_limit: float
    edge_ratio: float


@dataclass(frozen=True)
class RankedOpportunity:
    symbol: str
    spot: float
    mu: float
    hurst: float
    sigma: float
    expiry: str
    strike: float
    bid: float
    ask: float
    mid: float
    market_iv: float
    dte: int
    theoretical_value: float
    suggested_limit: float
    edge_ratio: float
    kelly_pct: float
    budget_dollars: float
    contracts: int
    has_open_orders: bool
    existing_option_position_qty: int


def default_config(universe: tuple[str, ...] = DEFAULT_BASKET) -> WhaleWakeConfig:
    return WhaleWakeConfig(
        strategy_key=STRATEGY_KEY,
        scan_time_et="14:30",
        exit_check_time_et="15:00",
        lookback_days=14,
        min_hurst_entry=0.60,
        min_hurst_exit=0.55,
        min_positive_drift=0.0,
        min_edge_ratio=1.20,
        max_spread_pct=0.15,
        target_dte=21,
        min_dte=10,
        max_dte=40,
        expiry_search_count=3,
        strike_search_count=4,
        earnings_blackout_days=5,
        assumed_win_prob=0.55,
        max_trade_risk_pct=0.05,
        risk_free_rate=0.045,
        market_data_type=3,
        settle_secs=2.0,
        skip_symbols_with_open_orders=True,
        universe=universe,
        data_policy="IBKR-first for executable pricing. No silent Yahoo fallback.",
        execution_policy="Write analysis first, then optionally create broker-ready proposals under orders/{YYYY-MM-DD}/.",
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_slug(now: datetime | None = None) -> str:
    current = now or _utc_now()
    return current.strftime("%H%M%S")


def _analysis_output_path(output_path: str | None = None, now: datetime | None = None) -> Path:
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    current = now or _utc_now()
    analysis_dir = ANALYSIS_ROOT / current.strftime("%Y-%m-%d")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    return analysis_dir / f"{STRATEGY_KEY}_scan_{_timestamp_slug(current)}.json"


def _proposal_output_path(output_path: str | None = None, now: datetime | None = None) -> Path:
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    current = now or _utc_now()
    order_dir = ORDERS_ROOT / current.strftime("%Y-%m-%d")
    order_dir.mkdir(parents=True, exist_ok=True)
    return order_dir / f"{STRATEGY_KEY}_add.json"


def _parse_metric_float(metrics: list[Any], tag: str) -> float | None:
    for metric in metrics:
        if metric.tag != tag:
            continue
        try:
            return float(str(metric.value).replace(",", ""))
        except ValueError:
            return None
    return None


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def slugify_symbols(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    symbols: list[str] = []
    for raw in values:
        symbol = raw.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return tuple(symbols)


def load_earnings_blackout(path: str | None = None) -> dict[str, date]:
    earnings_path = Path(path) if path else DEFAULT_EARNINGS_PATH
    if not earnings_path.exists():
        return {}
    payload = json.loads(earnings_path.read_text(encoding="utf-8"))
    normalized: dict[str, date] = {}
    for raw_symbol, raw_date in payload.items():
        symbol = raw_symbol.strip().upper()
        normalized[symbol] = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
    return normalized


def is_in_earnings_blackout(
    symbol: str,
    earnings_dates: dict[str, date],
    blackout_days: int,
    *,
    as_of: date | None = None,
) -> bool:
    earnings_date = earnings_dates.get(symbol.upper())
    if earnings_date is None:
        return False
    current = as_of or datetime.now().date()
    days_until = (earnings_date - current).days
    return 0 <= days_until <= blackout_days


def fractional_black_scholes(S: float, K: float, T: float, r: float, sigma: float, H: float) -> float:
    if S <= 0 or K <= 0:
        raise ValueError("S and K must be positive.")

    time_to_expiry = max(T, 1e-6)
    volatility = max(sigma, 1e-6)
    hurst = min(max(H, 0.01), 0.99)

    vol_frac = volatility * (time_to_expiry ** hurst)
    var_frac = (volatility ** 2) * (time_to_expiry ** (2.0 * hurst))
    d1 = (math.log(S / K) + r * time_to_expiry + 0.5 * var_frac) / vol_frac
    d2 = d1 - vol_frac
    return S * _norm_cdf(d1) - K * math.exp(-r * time_to_expiry) * _norm_cdf(d2)


def kelly_bet_size(win_prob: float, edge_ratio: float, max_portfolio_risk_pct: float) -> float:
    payoff = edge_ratio - 1.0
    if payoff <= 0:
        return 0.0

    kelly_pct = (win_prob * payoff - (1.0 - win_prob)) / payoff
    half_kelly = kelly_pct / 2.0
    return max(0.0, min(half_kelly, max_portfolio_risk_pct))


def size_position_contracts(net_liq: float | None, option_ask: float, risk_fraction: float) -> tuple[float, int]:
    if net_liq is None or net_liq <= 0 or option_ask <= 0 or risk_fraction <= 0:
        return 0.0, 0
    budget = net_liq * risk_fraction
    contracts = int(budget // (option_ask * 100.0))
    return round(budget, 2), max(contracts, 0)


def select_target_expiries(
    expiries: list[str] | tuple[str, ...],
    *,
    target_dte: int,
    min_dte: int,
    max_dte: int,
    max_count: int,
    now: datetime | None = None,
) -> list[str]:
    current = now or datetime.now()
    scored: list[tuple[int, str]] = []
    for expiry in expiries:
        dte, _ = dte_and_time_to_expiry(expiry, current)
        if dte < min_dte or dte > max_dte:
            continue
        scored.append((abs(dte - target_dte), expiry))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [expiry for _, expiry in scored[:max_count]]


def build_scaffold_snapshot(
    universe: tuple[str, ...] = DEFAULT_BASKET,
    now: datetime | None = None,
) -> dict[str, object]:
    current = now or _utc_now()
    config = default_config(universe=universe)
    return {
        "generated_at": current.isoformat(timespec="seconds"),
        "strategy_key": STRATEGY_KEY,
        "mode": "scaffold",
        "config": asdict(config),
        "pipeline": [
            "scan_volume_weighted_footprints_from_ibkr_history",
            "filter_hurst_and_drift",
            "exclude_earnings_blackout_if_configured",
            "select_otm_call_near_target_dte",
            "reject_wide_spreads",
            "compute_fractional_value",
            "rank_by_edge_ratio",
            "size_with_half_kelly",
            "write_analysis_snapshot",
            "optionally_prepare_order_proposal",
        ],
        "next_integration_targets": [
            "agentic review of ranked output via custom_scripts.research_session",
            "filled-order feedback loop for execution-quality tracking",
        ],
    }


def write_scaffold_snapshot(
    output_path: str | None = None,
    universe: tuple[str, ...] = DEFAULT_BASKET,
    now: datetime | None = None,
) -> Path:
    path = _analysis_output_path(output_path=output_path, now=now)
    snapshot = build_scaffold_snapshot(universe=universe, now=now)
    path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return path


def compute_volume_weighted_footprints(
    closes: list[float] | np.ndarray,
    highs: list[float] | np.ndarray,
    lows: list[float] | np.ndarray,
    volumes: list[float] | np.ndarray,
    *,
    lookback_days: int,
) -> FootprintMetrics:
    close_arr = np.asarray(closes, dtype=float)
    high_arr = np.asarray(highs, dtype=float)
    low_arr = np.asarray(lows, dtype=float)
    volume_arr = np.asarray(volumes, dtype=float)

    if len(close_arr) < 20 or len(high_arr) != len(close_arr) or len(low_arr) != len(close_arr):
        raise ValueError("Need at least 20 aligned bars to compute footprints.")

    if np.any(close_arr <= 0) or np.any(high_arr <= 0) or np.any(low_arr <= 0):
        raise ValueError("Price series must be strictly positive.")

    avg_volume = float(np.mean(volume_arr)) if len(volume_arr) else 0.0
    relative_volume = np.ones(len(volume_arr)) if avg_volume <= 0 else np.where(volume_arr <= 0, 1.0, volume_arr / avg_volume)

    returns = np.diff(close_arr) / close_arr[:-1]
    vw_returns = returns * relative_volume[1:]
    vw_prices = np.insert(np.cumprod(1.0 + vw_returns), 0, 1.0)

    time_fraction = max(lookback_days / 252.0, 1e-6)
    mu = float((vw_prices[-1] - 1.0) / time_fraction)

    lags = range(2, min(20, len(vw_prices) // 2))
    tau: list[float] = []
    lag_values: list[int] = []
    for lag in lags:
        path_diff = np.subtract(vw_prices[lag:], vw_prices[:-lag])
        std = float(np.std(path_diff))
        if std > 0:
            tau.append(std)
            lag_values.append(lag)
    if len(tau) >= 2:
        slope = float(np.polyfit(np.log(lag_values), np.log(tau), 1)[0])
        hurst = min(max(slope, 0.01), 0.99)
    else:
        hurst = 0.50

    safe_lows = np.where(low_arr <= 0, 1e-8, low_arr)
    log_hl = np.log(high_arr / safe_lows) ** 2
    sigma = float(np.sqrt((1.0 / (4.0 * math.log(2.0))) * np.mean(log_hl)) * math.sqrt(252.0 * 6.5))

    return FootprintMetrics(
        mu=mu,
        hurst=hurst,
        sigma=max(sigma, 0.05),
        spot=float(close_arr[-1]),
        bar_count=len(close_arr),
        avg_volume=avg_volume,
    )


def fetch_volume_weighted_footprints(
    ib,
    symbol: str,
    *,
    lookback_days: int,
) -> FootprintMetrics:
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    duration_days = max(lookback_days + 5, 20)
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=f"{duration_days} D",
        barSizeSetting="1 hour",
        whatToShow="TRADES",
        useRTH=True,
    )
    if len(bars) < 20:
        raise RuntimeError(f"IBKR returned too few hourly bars for {symbol}.")

    cutoff = datetime.now() - timedelta(days=lookback_days + 1)
    filtered = [bar for bar in bars if getattr(bar, "date", cutoff) >= cutoff]
    if len(filtered) < 20:
        filtered = list(bars)[-min(len(bars), 40 * max(lookback_days, 1)) :]

    closes = [float(bar.close) for bar in filtered]
    highs = [float(bar.high) for bar in filtered]
    lows = [float(bar.low) for bar in filtered]
    volumes = [float(bar.volume) for bar in filtered]
    return compute_volume_weighted_footprints(
        closes=closes,
        highs=highs,
        lows=lows,
        volumes=volumes,
        lookback_days=lookback_days,
    )


def select_best_otm_call(
    ib,
    symbol: str,
    *,
    spot: float,
    sigma: float,
    hurst: float,
    config: WhaleWakeConfig,
) -> OptionCandidate | None:
    underlying = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(underlying)
    chains = ib.reqSecDefOptParams(underlying.symbol, "", underlying.secType, underlying.conId)
    chain = next((item for item in chains if item.exchange == "SMART"), None)
    if chain is None:
        return None

    expiries = select_target_expiries(
        sorted(chain.expirations),
        target_dte=config.target_dte,
        min_dte=config.min_dte,
        max_dte=config.max_dte,
        max_count=config.expiry_search_count,
    )
    if not expiries:
        return None

    strikes = sorted(float(strike) for strike in chain.strikes if float(strike) > spot)
    if not strikes:
        return None

    specs: list[tuple[float, str, str]] = []
    for expiry in expiries:
        for strike in strikes[: config.strike_search_count]:
            specs.append((strike, expiry, "C"))
    if not specs:
        return None

    quotes = get_option_quotes(
        ib,
        symbol,
        specs,
        settle_secs=config.settle_secs,
        debug=False,
    )

    best_candidate: OptionCandidate | None = None
    for (strike, expiry, right), quote in zip(specs, quotes, strict=True):
        if not quote.has_market or quote.ask <= 0 or quote.bid <= 0 or quote.iv <= 0:
            continue
        if quote.spread_pct > config.max_spread_pct:
            continue

        dte, time_to_expiry = dte_and_time_to_expiry(expiry)
        theoretical_value = fractional_black_scholes(
            S=spot,
            K=strike,
            T=time_to_expiry,
            r=config.risk_free_rate,
            sigma=sigma,
            H=hurst,
        )
        if theoretical_value <= 0:
            continue

        limit = recommend_limit(theoretical_value, bid=quote.bid, ask=quote.ask, action="BUY")
        candidate = OptionCandidate(
            symbol=symbol,
            expiry=expiry,
            strike=strike,
            right=right,
            bid=quote.bid,
            ask=quote.ask,
            mid=quote.mid,
            iv=quote.iv,
            dte=dte,
            time_to_expiry=time_to_expiry,
            spread_pct=quote.spread_pct,
            theoretical_value=theoretical_value,
            suggested_limit=limit.suggested_limit,
            edge_ratio=theoretical_value / quote.ask,
        )
        if best_candidate is None or candidate.edge_ratio > best_candidate.edge_ratio:
            best_candidate = candidate
    return best_candidate


def build_executor_trade(opportunity: RankedOpportunity) -> dict[str, Any]:
    contract = OptionContractSpec(
        symbol=opportunity.symbol,
        expiry=opportunity.expiry,
        strike=opportunity.strike,
        right="C",
    )
    tranches = tranche_ladder(
        tv=opportunity.theoretical_value,
        bid=opportunity.bid,
        ask=opportunity.ask,
        total_qty=opportunity.contracts,
        action="BUY",
        n_tranches=min(3, opportunity.contracts),
    )
    return {
        "intent": "add",
        "contract": contract.as_executor_contract(),
        "action": "BUY",
        "tif": "DAY",
        "algo": "Adaptive",
        "algoPriority": "Normal",
        "tranches": [
            {
                "tranche": tranche["tranche"],
                "quantity": tranche["quantity"],
                "lmtPrice": tranche["limit_price"],
                "note": (
                    f"{STRATEGY_KEY} add "
                    f"edge={opportunity.edge_ratio:.2f} "
                    f"H={opportunity.hurst:.3f}"
                )[:40],
            }
            for tranche in tranches
        ],
    }


def build_order_payload(
    opportunities: list[RankedOpportunity],
    *,
    max_trades: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _utc_now()
    selected = [op for op in opportunities if op.contracts > 0][:max_trades]
    return {
        "description": f"{STRATEGY_KEY} add candidates ranked by edge ratio",
        "generated": current.strftime("%Y-%m-%d"),
        "trades": [build_executor_trade(opportunity) for opportunity in selected],
    }


def scan_universe(
    *,
    config: WhaleWakeConfig,
    earnings_path: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _utc_now()
    earnings_dates = load_earnings_blackout(earnings_path)

    with connect(
        client_id=41,
        market_data_type=config.market_data_type,
        readonly=True,
        debug=False,
    ) as ib:
        account_metrics = get_account_summary(ib, tags={"NetLiquidation"}, currencies={"USD", "BASE"})
        net_liq = _parse_metric_float(account_metrics, "NetLiquidation")
        open_orders = get_open_orders(ib, symbols=list(config.universe))
        portfolio = get_portfolio(ib, symbols=list(config.universe))

        open_order_symbols = {
            order.symbol
            for order in open_orders
            if order.sec_type == "OPT"
        }
        existing_option_qty: dict[str, int] = {}
        for position in portfolio:
            if position.sec_type != "OPT":
                continue
            existing_option_qty[position.symbol] = existing_option_qty.get(position.symbol, 0) + position.qty

        opportunities: list[RankedOpportunity] = []
        skipped: list[dict[str, Any]] = []

        for symbol in config.universe:
            if is_in_earnings_blackout(
                symbol,
                earnings_dates,
                config.earnings_blackout_days,
                as_of=current.date(),
            ):
                skipped.append({"symbol": symbol, "reason": "earnings_blackout"})
                continue

            has_open_orders = symbol in open_order_symbols
            if config.skip_symbols_with_open_orders and has_open_orders:
                skipped.append({"symbol": symbol, "reason": "existing_open_option_orders"})
                continue

            try:
                spot = get_spot(ib, symbol, allow_close_fallback=False)
                footprints = fetch_volume_weighted_footprints(
                    ib,
                    symbol,
                    lookback_days=config.lookback_days,
                )
            except Exception as exc:
                skipped.append({"symbol": symbol, "reason": "data_error", "detail": str(exc)})
                continue

            if footprints.hurst < config.min_hurst_entry:
                skipped.append({"symbol": symbol, "reason": "hurst_below_threshold", "hurst": round(footprints.hurst, 4)})
                continue
            if footprints.mu <= config.min_positive_drift:
                skipped.append({"symbol": symbol, "reason": "non_positive_drift", "mu": round(footprints.mu, 4)})
                continue

            candidate = select_best_otm_call(
                ib,
                symbol,
                spot=spot,
                sigma=footprints.sigma,
                hurst=footprints.hurst,
                config=config,
            )
            if candidate is None:
                skipped.append({"symbol": symbol, "reason": "no_tradeable_otm_call"})
                continue
            if candidate.edge_ratio < config.min_edge_ratio:
                skipped.append({
                    "symbol": symbol,
                    "reason": "edge_below_threshold",
                    "edge_ratio": round(candidate.edge_ratio, 4),
                })
                continue

            kelly_pct = kelly_bet_size(
                win_prob=config.assumed_win_prob,
                edge_ratio=candidate.edge_ratio,
                max_portfolio_risk_pct=config.max_trade_risk_pct,
            )
            budget_dollars, contracts = size_position_contracts(net_liq, candidate.ask, kelly_pct)
            opportunities.append(RankedOpportunity(
                symbol=symbol,
                spot=spot,
                mu=footprints.mu,
                hurst=footprints.hurst,
                sigma=footprints.sigma,
                expiry=candidate.expiry,
                strike=candidate.strike,
                bid=candidate.bid,
                ask=candidate.ask,
                mid=candidate.mid,
                market_iv=candidate.iv,
                dte=candidate.dte,
                theoretical_value=round(candidate.theoretical_value, 4),
                suggested_limit=candidate.suggested_limit,
                edge_ratio=round(candidate.edge_ratio, 4),
                kelly_pct=round(kelly_pct, 6),
                budget_dollars=budget_dollars,
                contracts=contracts,
                has_open_orders=has_open_orders,
                existing_option_position_qty=existing_option_qty.get(symbol, 0),
            ))

    opportunities.sort(key=lambda item: item.edge_ratio, reverse=True)
    return {
        "generated_at": current.isoformat(timespec="seconds"),
        "strategy_key": STRATEGY_KEY,
        "config": asdict(config),
        "account": {
            "net_liquidation": net_liq,
        },
        "open_order_symbols": sorted(open_order_symbols),
        "opportunities": [asdict(opportunity) for opportunity in opportunities],
        "skipped": skipped,
        "warnings": [
            "Earnings blackout filter is active only when config/earnings_blackout.json exists.",
        ],
    }


def run_and_write(
    *,
    config: WhaleWakeConfig,
    analysis_output: str | None = None,
    proposal_output: str | None = None,
    max_trades: int = 2,
    write_proposal: bool = False,
    earnings_path: str | None = None,
) -> tuple[Path, Path | None, dict[str, Any]]:
    report = scan_universe(
        config=config,
        earnings_path=earnings_path,
    )
    analysis_path = _analysis_output_path(analysis_output)
    analysis_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    proposal_path: Path | None = None
    if write_proposal:
        opportunities = [RankedOpportunity(**row) for row in report["opportunities"]]
        payload = build_order_payload(opportunities, max_trades=max_trades)
        if not payload["trades"]:
            raise RuntimeError("No sized trade candidates available for proposal output.")
        proposal_path = _proposal_output_path(proposal_output)
        proposal_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return analysis_path, proposal_path, report


def check_daily_exits(
    symbols: tuple[str, ...],
    *,
    min_hurst_exit: float,
    lookback_days: int,
    market_data_type: int = 3,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with connect(client_id=42, market_data_type=market_data_type, readonly=True, debug=False) as ib:
        for symbol in symbols:
            footprints = fetch_volume_weighted_footprints(
                ib,
                symbol,
                lookback_days=lookback_days,
            )
            results.append({
                "symbol": symbol,
                "hurst": round(footprints.hurst, 4),
                "mu": round(footprints.mu, 4),
                "action": "SELL_TO_CLOSE" if footprints.hurst < min_hurst_exit else "HOLD",
            })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IBKR-native whale wake cross-sectional screener.",
    )
    parser.add_argument("--universe", nargs="*", default=list(DEFAULT_BASKET), help="Ticker universe override.")
    parser.add_argument("--output", help="Optional analysis JSON output path.")
    parser.add_argument("--proposal-output", help="Optional proposal JSON output path.")
    parser.add_argument("--proposal", action="store_true", help="Write executor-compatible proposal JSON.")
    parser.add_argument("--max-trades", type=int, default=2, help="Maximum ranked trades to include in proposal output.")
    parser.add_argument("--target-dte", type=int, default=21)
    parser.add_argument("--min-dte", type=int, default=10)
    parser.add_argument("--max-dte", type=int, default=40)
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--min-hurst", type=float, default=0.60)
    parser.add_argument("--min-edge-ratio", type=float, default=1.20)
    parser.add_argument("--max-spread-pct", type=float, default=0.15)
    parser.add_argument("--assumed-win-prob", type=float, default=0.55)
    parser.add_argument("--max-trade-risk-pct", type=float, default=0.05)
    parser.add_argument("--market-data-type", type=int, default=3, help="1=live, 3=delayed, 4=delayed-frozen")
    parser.add_argument("--risk-free", type=float, default=0.045)
    parser.add_argument("--earnings-path", default=None, help="Optional earnings blackout JSON path.")
    parser.add_argument("--allow-open-order-symbols", action="store_true", help="Do not skip symbols with existing open option orders.")
    parser.add_argument("--scaffold-only", action="store_true", help="Write the non-live scaffold snapshot instead of running IBKR scan.")
    parser.add_argument("--check-exits", nargs="*", default=None, help="Run the daily exit manager on held symbols.")
    args = parser.parse_args()

    universe = slugify_symbols(args.universe)
    config = default_config(universe=universe)
    config = WhaleWakeConfig(
        **{
            **asdict(config),
            "lookback_days": args.lookback_days,
            "min_hurst_entry": args.min_hurst,
            "min_edge_ratio": args.min_edge_ratio,
            "max_spread_pct": args.max_spread_pct,
            "target_dte": args.target_dte,
            "min_dte": args.min_dte,
            "max_dte": args.max_dte,
            "assumed_win_prob": args.assumed_win_prob,
            "max_trade_risk_pct": args.max_trade_risk_pct,
            "risk_free_rate": args.risk_free,
            "market_data_type": args.market_data_type,
            "skip_symbols_with_open_orders": not args.allow_open_order_symbols,
            "universe": universe,
        }
    )

    if args.scaffold_only:
        output_path = write_scaffold_snapshot(output_path=args.output, universe=universe)
        print(output_path)
        return

    if args.check_exits:
        results = check_daily_exits(
            symbols=slugify_symbols(args.check_exits),
            min_hurst_exit=config.min_hurst_exit,
            lookback_days=config.lookback_days,
            market_data_type=config.market_data_type,
        )
        print(json.dumps(results, indent=2))
        return

    analysis_path, proposal_path, report = run_and_write(
        config=config,
        analysis_output=args.output,
        proposal_output=args.proposal_output,
        max_trades=args.max_trades,
        write_proposal=args.proposal,
        earnings_path=args.earnings_path,
    )

    print(analysis_path)
    if proposal_path is not None:
        print(proposal_path)

    opportunities = report["opportunities"]
    if opportunities:
        print("\nTop opportunities:")
        for index, opportunity in enumerate(opportunities[: args.max_trades], start=1):
            print(
                f"{index}. {opportunity['symbol']} "
                f"{opportunity['expiry']} {opportunity['strike']:.1f}C "
                f"edge={opportunity['edge_ratio']:.2f} "
                f"H={opportunity['hurst']:.3f} "
                f"qty={opportunity['contracts']}"
            )
    else:
        print("\nNo opportunities passed the filters.")


if __name__ == "__main__":
    main()
