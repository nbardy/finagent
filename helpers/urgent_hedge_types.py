from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


HedgeStructure = Literal["put", "put_spread"]
ExecutionMode = Literal["regular", "near_close", "closed"]


@dataclass(frozen=True)
class MacroScenario:
    label: str
    horizon_days: int
    spot_move_pct: float
    vol_shift: float
    probability: float
    notes: str = ""


@dataclass(frozen=True)
class MacroScenarioSet:
    name: str
    symbol: str
    as_of: str
    scenarios: tuple[MacroScenario, ...]
    thesis: str = ""
    reference_spot: float | None = None
    risk_free_rate: float = 0.045


@dataclass(frozen=True)
class PortfolioOptionLine:
    label: str
    right: str
    strike: float
    dte: int
    qty: int
    mark: float
    iv: float


@dataclass(frozen=True)
class PortfolioBook:
    symbol: str
    spot: float
    risk_free_rate: float
    positions: tuple[PortfolioOptionLine, ...]


@dataclass(frozen=True)
class HedgeStructureSpec:
    name: str
    expiry: str
    structure: HedgeStructure
    long_strike: float
    short_strike: float | None = None
    quantity_hint: int = 0
    notes: str = ""


@dataclass(frozen=True)
class ComboLegSpec:
    action: Literal["BUY", "SELL"]
    strike: float
    right: Literal["C", "P"]
    expiry: str
    ratio: int = 1


@dataclass(frozen=True)
class LegQuoteSnapshot:
    strike: float
    right: str
    expiry: str
    bid: float
    ask: float
    mid: float
    iv: float
    last: float = 0.0
    volume: int | None = None
    open_interest: int | None = None


@dataclass(frozen=True)
class ComboQuoteSnapshot:
    symbol: str
    spot: float
    legs: tuple[ComboLegSpec, ...]
    leg_quotes: tuple[LegQuoteSnapshot, ...]
    combo_bid: float
    combo_ask: float
    combo_mid: float
    quote_time: str = ""
    source: str = "yfinance"


@dataclass(frozen=True)
class ScenarioOutcome:
    label: str
    probability: float
    hedge_pnl: float
    book_pnl: float | None = None
    combined_pnl: float | None = None
    coverage_pct: float = 0.0


@dataclass(frozen=True)
class HedgeCandidate:
    spec: HedgeStructureSpec
    combo: ComboQuoteSnapshot
    target_quantity: int
    entry_debit: float
    max_value: float
    scenario_outcomes: tuple[ScenarioOutcome, ...]
    expected_pnl: float
    expected_combined_pnl: float | None
    conditional_downside_coverage_pct: float
    downside_probability_pct: float
    carry_loss_pct: float
    score: float


@dataclass(frozen=True)
class ProbePolicy:
    probe_qty: int
    max_wait_seconds: int
    poll_interval_seconds: int
    escalation_ticks: tuple[int, ...]
    stop_after_partials: bool = False


@dataclass(frozen=True)
class ChasePolicy:
    max_rounds: int
    tick_up_per_round: float
    max_unit_debit: float
    convert_to_open_ready_if_closed: bool = True


@dataclass(frozen=True)
class MarketSessionState:
    as_of: str
    market_tz: str
    mode: ExecutionMode
    is_trading_day: bool
    is_open: bool
    minutes_to_close: int | None
    next_open: str


@dataclass(frozen=True)
class HedgeExecutionPlan:
    symbol: str
    thesis: str
    candidate_name: str
    target_quantity: int
    budget: float
    recommended_artifact: str
    combo: ComboQuoteSnapshot
    probe_policy: ProbePolicy
    chase_policy: ChasePolicy
    session: MarketSessionState
    probe_file: str
    full_file: str
    open_ready_file: str


@dataclass
class LiveOrderState:
    order_ids: list[int] = field(default_factory=list)
    status: str = ""
    filled_qty: int = 0
    remaining_qty: int = 0
    avg_fill_price: float = 0.0
