from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def normalize_expiry(expiry: str) -> str:
    digits = expiry.replace("-", "").strip()
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError(f"Expected expiry as YYYYMMDD or YYYY-MM-DD, got: {expiry!r}")
    return digits


def display_expiry(expiry: str) -> str:
    digits = normalize_expiry(expiry)
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def dte_and_time_to_expiry(expiry: str, now: datetime | None = None) -> tuple[int, float]:
    current = now or datetime.now()
    expiry_dt = datetime.strptime(normalize_expiry(expiry), "%Y%m%d")
    dte = max((expiry_dt - current).days, 1)
    return dte, dte / 365.0


@dataclass(frozen=True)
class OptionContractSpec:
    symbol: str
    expiry: str
    strike: float
    right: str = "C"
    exchange: str = "SMART"
    currency: str = "USD"
    sec_type: str = "OPT"

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "expiry", normalize_expiry(self.expiry))
        object.__setattr__(self, "right", self.right.upper())

    def as_executor_contract(self) -> dict:
        return {
            "symbol": self.symbol,
            "secType": self.sec_type,
            "exchange": self.exchange,
            "currency": self.currency,
            "lastTradeDateOrContractMonth": self.expiry,
            "strike": float(self.strike),
            "right": self.right,
        }


@dataclass(frozen=True)
class OptionMarketSnapshot:
    spot: float
    bid: float
    ask: float
    last: float = 0.0
    implied_volatility: float = 0.0
    risk_free_rate: float = 0.045
    dividend_yield: float = 0.0
    source: str = ""
    quote_warning: str | None = None
    volume: int | None = None
    open_interest: int | None = None
    market_data_type: int | None = None
    quote_time: str | None = None
    model_underlying_price: float | None = None
    pv_dividend: float | None = None

    @property
    def mid(self) -> float:
        if self.ask > 0 and self.bid >= 0:
            return (self.bid + self.ask) / 2.0
        return self.last if self.last > 0 else 0.0

    @property
    def has_market(self) -> bool:
        return self.ask > 0 and self.bid >= 0

    @property
    def spread(self) -> float:
        return self.ask - self.bid if self.has_market else 0.0

    @property
    def spread_pct(self) -> float:
        mid = self.mid
        if mid <= 0:
            return float("inf")
        return self.spread / mid

    @property
    def is_delayed(self) -> bool | None:
        if self.market_data_type is None:
            return None
        return self.market_data_type in {3, 4}
