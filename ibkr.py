"""
Shared IBKR connection and market data utilities.

All scripts should use this module instead of managing connections directly.
Reads connection config from pmcc_config.json once.

Usage:
    from ibkr import connect, get_spot, get_option_quotes, get_portfolio, load_fill_ledger

    with connect() as ib:
        spot = get_spot(ib, "EWY")
        quotes = get_option_quotes(ib, "EWY", [(145, "20280121", "C")])
        positions = get_portfolio(ib)
"""

import json
import math
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from ib_insync import IB, Contract, Stock, Option


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _contract_summary(contract) -> str:
    if not contract:
        return "n/a"

    parts = [getattr(contract, "symbol", "")]
    expiry = getattr(contract, "lastTradeDateOrContractMonth", "")
    if expiry:
        parts.append(str(expiry))
    strike = getattr(contract, "strike", 0)
    right = getattr(contract, "right", "")
    if strike or right:
        parts.append(f"{float(strike):.1f}{right}")
    exchange = getattr(contract, "exchange", "")
    if exchange:
        parts.append(exchange)
    return " ".join(part for part in parts if part)


def _attach_debug_handlers(ib: IB, label: str) -> None:
    def on_error(req_id, error_code, error_string, contract):
        message = (
            f"[{_ts()}] IBKR error"
            f" label={label}"
            f" reqId={req_id}"
            f" code={error_code}"
            f" msg={error_string}"
        )
        if contract:
            message += f" contract={_contract_summary(contract)}"
        print(message)

    def on_disconnected():
        print(f"[{_ts()}] IBKR disconnected label={label}")

    def on_connected():
        print(f"[{_ts()}] IBKR connected label={label}")

    ib.errorEvent += on_error
    ib.disconnectedEvent += on_disconnected
    ib.connectedEvent += on_connected

def _load_config() -> dict:
    config_path = Path(__file__).parent / "config" / "pmcc_config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


@contextmanager
def connect(
    client_id: int = 11,
    market_data_type: int = 3,
    readonly: bool = True,
    timeout: float = 20.0,
    debug: bool = False,
):
    """
    Context manager for IBKR connections. Reads host/port from config.

    market_data_type: 1=live (requires subscription), 3=delayed, 4=delayed-frozen
    Use delayed (3) unless you have a live data subscription for the instrument.
    readonly: use read-only API mode for pricing/portfolio helpers so the
    gateway does not expect order/execution sync during connection.
    timeout: seconds to allow IBKR's initial sync to complete.

    Usage:
        with connect(client_id=12) as ib:
            ...
    """
    cfg = _load_config().get("connection", {})
    host = cfg.get("host", "127.0.0.1")
    port = cfg.get("port", 4001)

    ib = IB()
    try:
        if debug:
            print(
                f"[{_ts()}] IBKR connect start"
                f" host={host} port={port} clientId={client_id}"
                f" readonly={readonly} marketDataType={market_data_type}"
                f" timeout={timeout}"
            )
            _attach_debug_handlers(ib, label=f"{host}:{port}/cid={client_id}")
        ib.connect(host, port, clientId=client_id, readonly=readonly, timeout=timeout)
        if debug:
            accounts = []
            try:
                accounts = list(ib.managedAccounts())
            except Exception:
                pass
            print(
                f"[{_ts()}] IBKR connect ok"
                f" connected={ib.isConnected()} accounts={accounts or 'n/a'}"
            )
        ib.reqMarketDataType(market_data_type)
        if debug:
            print(f"[{_ts()}] IBKR requested marketDataType={market_data_type}")
        yield ib
    except Exception as exc:
        print(
            f"[{_ts()}] IBKR connect failure"
            f" host={host} port={port} clientId={client_id}"
            f" type={type(exc).__name__} msg={exc}"
        )
        raise
    finally:
        if ib.isConnected():
            if debug:
                print(f"[{_ts()}] IBKR disconnect host={host} port={port} clientId={client_id}")
            ib.disconnect()


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------

def get_spot(ib: IB, symbol: str, debug: bool = False, allow_close_fallback: bool = False) -> float:
    """Get current price for a stock. Raises if IBKR cannot provide a usable spot."""
    underlying = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(underlying)
    [ticker] = ib.reqTickers(underlying)
    ib.sleep(1)
    price = ticker.marketPrice()
    if math.isnan(price) or price <= 0:
        if allow_close_fallback and not math.isnan(ticker.close) and ticker.close > 0:
            price = ticker.close
        else:
            raise ValueError(
                f"Missing IBKR spot for {symbol}; "
                "get_spot is strict and will not fall back to close."
            )
    if debug:
        print(
            f"[{_ts()}] spot"
            f" symbol={symbol}"
            f" bid={ticker.bid} ask={ticker.ask} last={ticker.last}"
            f" close={ticker.close} marketPrice={ticker.marketPrice()}"
            f" marketDataType={getattr(ticker, 'marketDataType', 'n/a')}"
        )
    return price


@dataclass
class OptionQuote:
    symbol: str
    strike: float
    expiry: str
    right: str
    bid: float
    ask: float
    mid: float
    last: float
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float

    @property
    def has_market(self) -> bool:
        """True if we have a live two-sided quote."""
        return self.bid > 0 and self.ask > 0

    @property
    def spread(self) -> float:
        return self.ask - self.bid if self.has_market else float("inf")

    @property
    def spread_pct(self) -> float:
        return self.spread / self.mid if self.mid > 0 else float("inf")


@dataclass
class QuoteHealth:
    """
    Structured market-data health for a single contract.

    This is broader than OptionQuote so callers can inspect spot, quote, and
    greek availability in one place.
    """

    symbol: str
    sec_type: str
    expiry: str
    strike: float
    right: str
    exchange: str
    market_data_type: int
    qualified: bool
    bid: float
    ask: float
    last: float
    close: float
    market_price: float
    mid: float
    spot: float
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    has_spot: bool
    has_two_sided_quote: bool
    has_greeks: bool
    status: str
    reason: str
    contract_summary: str


@dataclass
class OptionChainInfo:
    """
    Option chain metadata returned from reqSecDefOptParams.
    """

    symbol: str
    exchange: str
    trading_class: str
    multiplier: str
    expirations: tuple[str, ...]
    strikes: tuple[float, ...]
    underlying_con_id: int

    @property
    def has_contracts(self) -> bool:
        return bool(self.expirations) and bool(self.strikes)


def _safe_float(val, default: float = 0.0) -> float:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    return float(val)


def _safe_int(val, default: int = 0) -> int:
    try:
        if val is None:
            return default
        if isinstance(val, float) and math.isnan(val):
            return default
        return int(val)
    except Exception:
        return default


def get_option_quotes(
    ib: IB,
    symbol: str,
    specs: list[tuple[float, str, str]],
    settle_secs: float = 2.0,
    debug: bool = False,
) -> list[OptionQuote]:
    """
    Fetch quotes for a list of option specs.

    specs: list of (strike, expiry_YYYYMMDD, right) tuples
        e.g. [(145, "20280121", "C"), (150, "20280121", "C")]

    Returns quotes in same order as specs. Quotes with no data
    will have bid/ask = 0 — use quote.has_market to check.
    """
    contracts = []
    for strike, expiry, right in specs:
        contracts.append(Option(symbol, expiry, strike, right, "SMART"))

    contracts = ib.qualifyContracts(*contracts)
    tickers = ib.reqTickers(*contracts)
    ib.sleep(settle_secs)

    quotes = []
    for t in tickers:
        bid = _safe_float(t.bid)
        ask = _safe_float(t.ask)
        last = _safe_float(t.last)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else last

        greeks = t.modelGreeks
        iv = _safe_float(greeks.impliedVol if greeks else None)
        delta = _safe_float(greeks.delta if greeks else None)
        gamma = _safe_float(greeks.gamma if greeks else None)
        theta = _safe_float(greeks.theta if greeks else None)
        vega = _safe_float(greeks.vega if greeks else None)

        quotes.append(OptionQuote(
            symbol=symbol,
            strike=t.contract.strike,
            expiry=t.contract.lastTradeDateOrContractMonth,
            right=t.contract.right,
            bid=bid, ask=ask, mid=mid, last=last,
            iv=iv, delta=delta, gamma=gamma, theta=theta, vega=vega,
        ))
        if debug:
            print(
                f"[{_ts()}] option"
                f" contract={symbol} {t.contract.lastTradeDateOrContractMonth}"
                f" {t.contract.strike:.1f}{t.contract.right}"
                f" bid={bid} ask={ask} last={last} mid={mid}"
                f" iv={iv} delta={delta} gamma={gamma}"
                f" theta={theta} vega={vega}"
                f" marketDataType={getattr(t, 'marketDataType', 'n/a')}"
            )

    return quotes


def get_option_chains(
    ib: IB,
    symbol: str,
    exchange: str = "SMART",
    debug: bool = False,
) -> list[OptionChainInfo]:
    """
    Return option-chain metadata for a symbol.

    This wraps reqSecDefOptParams and normalizes the chain into a typed
    dataclass so callers can inspect real expirations and strikes.
    """
    underlying = Stock(symbol, "SMART", "USD")
    qualified = ib.qualifyContracts(underlying)
    if not qualified:
        raise ValueError(f"Could not qualify underlying contract for {symbol}.")
    underlying = qualified[0]
    chains = ib.reqSecDefOptParams(
        underlying.symbol,
        "",
        underlying.secType,
        underlying.conId,
    )

    infos: list[OptionChainInfo] = []
    for chain in chains:
        if exchange and chain.exchange != exchange:
            continue
        infos.append(OptionChainInfo(
            symbol=symbol,
            exchange=chain.exchange,
            trading_class=chain.tradingClass,
            multiplier=str(chain.multiplier),
            expirations=tuple(sorted(str(exp) for exp in chain.expirations)),
            strikes=tuple(sorted(float(strike) for strike in chain.strikes)),
            underlying_con_id=_safe_int(getattr(chain, "underlyingConId", 0)),
        ))

    infos.sort(key=lambda info: (info.exchange, info.trading_class, info.multiplier))

    if debug:
        print(
            f"[{_ts()}] chain"
            f" symbol={symbol}"
            f" exchange={exchange}"
            f" chains={len(infos)}"
        )

    return infos


def get_smart_option_chain(
    ib: IB,
    symbol: str,
    debug: bool = False,
) -> OptionChainInfo:
    """
    Return the primary SMART option chain for a symbol.
    """
    chains = get_option_chains(ib, symbol, exchange="SMART", debug=debug)
    if not chains:
        raise ValueError(f"No SMART option chain found for {symbol}.")
    return chains[0]


def select_chain_strikes(
    chain: OptionChainInfo,
    center_strike: float,
    span_steps: int = 6,
    step: float | None = None,
) -> list[float]:
    """
    Build a strike list clipped to the actual chain.

    If step is omitted, infer it from the smallest positive increment in the
    available chain strikes.
    """
    available = list(chain.strikes)
    if not available:
        return [float(center_strike)]

    if step is None:
        deltas = []
        for prev, curr in zip(available, available[1:]):
            diff = round(curr - prev, 8)
            if diff > 0:
                deltas.append(diff)
        step = min(deltas) if deltas else 5.0

    start = center_strike - span_steps * step
    end = center_strike + span_steps * step

    selected = [
        strike
        for strike in available
        if start - 1e-9 <= strike <= end + 1e-9
    ]

    if center_strike in available and center_strike not in selected:
        selected.append(center_strike)
        selected.sort()

    return selected


def inspect_contract_market_data(
    ib: IB,
    contract: Contract,
    settle_secs: float = 2.0,
    market_data_type: int | None = None,
) -> QuoteHealth:
    """
    Inspect a contract's market-data readiness in a structured way.

    This is generic preflight for pricing tools. It never raises just because
    the book is empty; instead it returns a status and reason for callers to
    surface or branch on.
    """
    qualified = False
    ticker = None
    try:
        qualified_contracts = ib.qualifyContracts(contract)
        qualified = bool(qualified_contracts)
        if qualified_contracts:
            contract = qualified_contracts[0]
    except Exception:
        qualified = False

    bid = ask = last = close = market_price = mid = 0.0
    spot = iv = delta = gamma = theta = vega = 0.0
    has_two_sided_quote = False
    has_greeks = False
    has_spot = False
    status = "unavailable"
    reason = "contract_not_qualified" if not qualified else "no_market_data"

    try:
        [ticker] = ib.reqTickers(contract)
        ib.sleep(settle_secs)

        bid = _safe_float(getattr(ticker, "bid", None))
        ask = _safe_float(getattr(ticker, "ask", None))
        last = _safe_float(getattr(ticker, "last", None))
        close = _safe_float(getattr(ticker, "close", None))
        market_price = _safe_float(ticker.marketPrice())
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else market_price

        greeks = getattr(ticker, "modelGreeks", None)
        if greeks:
            iv = _safe_float(getattr(greeks, "impliedVol", None))
            delta = _safe_float(getattr(greeks, "delta", None))
            gamma = _safe_float(getattr(greeks, "gamma", None))
            theta = _safe_float(getattr(greeks, "theta", None))
            vega = _safe_float(getattr(greeks, "vega", None))
            spot = _safe_float(getattr(greeks, "undPrice", None))

        has_two_sided_quote = bid > 0 and ask > 0
        has_greeks = bool(greeks)
        has_spot = spot > 0 or market_price > 0 or close > 0

        if has_two_sided_quote and has_greeks:
            status = "ready"
            reason = "two_sided_quote_and_greeks"
        elif has_two_sided_quote:
            status = "quoted"
            reason = "two_sided_quote_no_greeks"
        elif has_spot:
            status = "spot_only"
            reason = "spot_available_no_two_sided_quote"
        else:
            status = "unavailable"
            reason = "empty_quote_and_greeks"
    except Exception as exc:
        status = "unavailable"
        reason = f"{type(exc).__name__}:{exc}"

    if market_data_type is None:
        market_data_type = _safe_int(getattr(ticker, "marketDataType", None), 0) if ticker is not None else 0

    expiry = getattr(contract, "lastTradeDateOrContractMonth", "") if getattr(contract, "secType", "") == "OPT" else ""
    strike = float(getattr(contract, "strike", 0.0))
    right = getattr(contract, "right", "")
    exchange = getattr(contract, "exchange", "")

    return QuoteHealth(
        symbol=getattr(contract, "symbol", ""),
        sec_type=getattr(contract, "secType", ""),
        expiry=expiry,
        strike=strike,
        right=right,
        exchange=exchange,
        market_data_type=int(market_data_type),
        qualified=qualified,
        bid=bid,
        ask=ask,
        last=last,
        close=close,
        market_price=market_price,
        mid=mid,
        spot=spot,
        iv=iv,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        has_spot=has_spot,
        has_two_sided_quote=has_two_sided_quote,
        has_greeks=has_greeks,
        status=status,
        reason=reason,
        contract_summary=_contract_summary(contract),
    )


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@dataclass
class Position:
    symbol: str
    sec_type: str
    right: str
    strike: float
    expiry: str
    dte: int | None
    qty: int
    avg_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    cost_basis: float
    pct_return: float
    con_id: int
    currency: str = "USD"
    local_avg_cost: float = 0.0
    local_market_price: float = 0.0


@dataclass
class OpenOrder:
    order_id: int
    perm_id: int
    order_ref: str
    symbol: str
    sec_type: str
    expiry: str
    strike: float
    right: str
    action: str
    order_type: str
    tif: str
    quantity: int
    limit_price: float
    status: str
    filled: float
    remaining: float
    client_id: int = 0


@dataclass
class AccountMetric:
    account: str
    tag: str
    value: str
    currency: str


@dataclass
class FillEvent:
    order_id: int
    perm_id: int
    client_id: int
    order_ref: str
    exec_id: str
    symbol: str
    sec_type: str
    expiry: str
    strike: float
    right: str
    side: str
    shares: float
    price: float
    time: str
    commission: float
    realized_pnl: float
    currency: str


import yfinance as yf

_FX_CACHE = {"USD": 1.0}

def _get_fx_rate(currency: str) -> float:
    if currency in _FX_CACHE:
        return _FX_CACHE[currency]
    rate = 1.0
    if currency:
        try:
            if currency == "JPY":
                tkr = yf.Ticker("JPY=X") # USD/JPY, so 1 USD = X JPY. Rate to USD is 1/X
                hist = tkr.history(period="1d")
                if not hist.empty:
                    rate = 1.0 / hist["Close"].iloc[-1]
            else:
                tkr = yf.Ticker(f"{currency}USD=X")
                hist = tkr.history(period="1d")
                if not hist.empty:
                    rate = float(hist["Close"].iloc[-1])
        except Exception:
            pass
    _FX_CACHE[currency] = rate
    return rate

def get_model_greeks(ib: IB, contracts: list[Contract], timeout: int = 5) -> dict[int, float]:
    """
    Fetch IBKR's internal model pricing (modelGreeks.optPrice) for a list of option contracts.
    
    Returns a dictionary mapping the contract's conId to its model price.
    Returns float('nan') for contracts where the model price could not be retrieved within the timeout.
    """
    ib.qualifyContracts(*contracts)
    tickers = ib.reqTickers(*contracts)
    
    # Wait for modelGreeks to populate
    for _ in range(timeout * 2): # Check every 0.5 seconds
        if all(t.modelGreeks for t in tickers):
            break
        ib.sleep(0.5)
        
    results = {}
    for t in tickers:
        con_id = t.contract.conId
        if t.modelGreeks and getattr(t.modelGreeks, 'optPrice', None) is not None:
            results[con_id] = float(t.modelGreeks.optPrice)
        else:
            results[con_id] = float('nan')
            
    return results

def get_portfolio(ib: IB, symbols: list[str] | None = None) -> list[Position]:
    """
    Fetch all positions with P&L from IBKR.

    Optionally filter by symbol list.
    Returns Position dataclass instances sorted by symbol/expiry/strike.
    """
    portfolio_items = ib.portfolio()
    today = datetime.now()

    positions = []
    for item in portfolio_items:
        c = item.contract
        sym = c.symbol

        if symbols and sym not in symbols:
            continue

        dte = None
        expiry = ""
        if c.secType == "OPT":
            expiry = c.lastTradeDateOrContractMonth
            try:
                dte = (datetime.strptime(expiry, "%Y%m%d") - today).days
            except ValueError:
                pass

        qty = int(item.position)
        
        fx_rate = _get_fx_rate(c.currency)
        
        # item.marketValue is already converted to base currency (USD) by IBKR usually,
        # but averageCost, unrealizedPNL, realizedPNL are often in local currency.
        # Let's ensure standardizing to USD.
        avg_cost = item.averageCost * fx_rate
        market_price = _safe_float(item.marketPrice) * fx_rate
        market_value = item.marketValue * fx_rate
        
        unrealized_pnl = item.unrealizedPNL * fx_rate
        realized_pnl = item.realizedPNL * fx_rate
        
        # IBKR averageCost: for stocks it's per-share, for options it's
        # already total cost per contract (avg_cost_per_share * multiplier).
        # So cost_basis = averageCost * abs(qty) for both.
        cost_basis = avg_cost * abs(qty)

        pct_return = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0

        positions.append(Position(
            symbol=sym,
            sec_type=c.secType,
            right=getattr(c, "right", ""),
            strike=float(getattr(c, "strike", 0)),
            expiry=expiry,
            dte=dte,
            qty=qty,
            avg_cost=round(avg_cost, 4),
            market_price=round(market_price, 4),
            market_value=round(market_value, 2),
            unrealized_pnl=round(unrealized_pnl, 2),
            realized_pnl=round(realized_pnl, 2),
            cost_basis=round(cost_basis, 2),
            pct_return=round(pct_return, 2),
            con_id=c.conId,
            currency=c.currency,
            local_avg_cost=round(item.averageCost, 4),
            local_market_price=round(_safe_float(item.marketPrice), 4),
        ))

    positions.sort(key=lambda p: (p.symbol, p.sec_type, p.expiry, p.strike))
    return positions


def get_open_orders(ib: IB, symbols: list[str] | None = None) -> list[OpenOrder]:
    """
    Fetch currently open orders from IBKR.

    Optionally filter by symbol list.
    """
    # Pull account-wide open orders so reads from a different clientId still
    # see working orders placed earlier by the executor or the phone.
    ib.reqAllOpenOrders()
    ib.sleep(1.0)

    orders = []
    for trade in ib.openTrades():
        contract = trade.contract
        symbol = getattr(contract, "symbol", "")

        if symbols and symbol not in symbols:
            continue

        expiry = ""
        if getattr(contract, "secType", "") == "OPT":
            expiry = getattr(contract, "lastTradeDateOrContractMonth", "")

        orders.append(OpenOrder(
            order_id=trade.order.orderId,
            perm_id=trade.order.permId,
            order_ref=getattr(trade.order, "orderRef", "") or "",
            symbol=symbol,
            sec_type=getattr(contract, "secType", ""),
            expiry=expiry,
            strike=float(getattr(contract, "strike", 0.0)),
            right=getattr(contract, "right", ""),
            action=trade.order.action,
            order_type=trade.order.orderType,
            tif=trade.order.tif,
            quantity=int(trade.order.totalQuantity),
            limit_price=_safe_float(getattr(trade.order, "lmtPrice", None)),
            status=trade.orderStatus.status,
            filled=_safe_float(trade.orderStatus.filled),
            remaining=_safe_float(trade.orderStatus.remaining),
            client_id=int(getattr(trade.order, "clientId", 0) or 0),
        ))

    orders.sort(key=lambda o: (o.symbol, o.expiry, o.strike, o.order_id))
    return orders


def cancel_open_orders(
    order_ids: set[int] | None = None,
    symbols: set[str] | None = None,
    settle_secs: float = 1.0,
) -> list[OpenOrder]:
    """
    Cancel matching open orders across client IDs.

    IBKR isolates orders by clientId, so cancellation must reconnect as the
    originating client. This helper centralizes that workflow.

    order_ids: optional set of specific order ids to cancel.
    symbols: optional set of symbols whose open orders should be cancelled.
    Returns the matched open orders targeted for cancellation.
    """
    if not order_ids and not symbols:
        raise ValueError("cancel_open_orders requires order_ids and/or symbols.")

    cfg = _load_config().get("connection", {})
    host = cfg.get("host", "127.0.0.1")
    port = cfg.get("port", 4001)
    discovery_client_id = cfg.get("client_id_portfolio", 4)

    discovery = IB()
    matched: list[OpenOrder] = []
    by_client: dict[int, list[int]] = {}
    try:
        discovery.connect(host, port, clientId=discovery_client_id, readonly=False)
        discovery.reqAllOpenOrders()
        discovery.sleep(settle_secs)

        for order in get_open_orders(discovery):
            if order_ids and order.order_id not in order_ids:
                continue
            if symbols and order.symbol not in symbols:
                continue
            matched.append(order)
            by_client.setdefault(order.client_id, []).append(order.order_id)
    finally:
        if discovery.isConnected():
            discovery.disconnect()

    for client_id, client_order_ids in by_client.items():
        ib = IB()
        try:
            ib.connect(host, port, clientId=client_id, readonly=False)
            open_orders = {o.orderId: o for o in ib.openOrders()}
            for order_id in client_order_ids:
                order = open_orders.get(order_id)
                if order:
                    ib.cancelOrder(order)
            ib.sleep(settle_secs)
        finally:
            if ib.isConnected():
                ib.disconnect()

    return matched


def get_account_summary(
    ib: IB,
    tags: set[str] | None = None,
    currencies: set[str] | None = None,
) -> list[AccountMetric]:
    """
    Fetch account summary metrics from IBKR.

    tags: optional set of summary tag names to keep.
    currencies: optional set of currencies to keep, e.g. {"USD", "BASE"}.
    """
    metrics = []
    for row in ib.accountSummary():
        if tags and row.tag not in tags:
            continue
        if currencies and row.currency not in currencies:
            continue
        metrics.append(AccountMetric(
            account=row.account,
            tag=row.tag,
            value=row.value,
            currency=row.currency,
        ))

    metrics.sort(key=lambda m: (m.currency, m.tag))
    return metrics


def get_recent_fills(ib: IB, symbols: list[str] | None = None) -> list[FillEvent]:
    """
    Fetch recent execution fills from IBKR.

    Optionally filter by symbol list.
    """
    fills = []
    for fill in ib.fills():
        contract = fill.contract
        symbol = getattr(contract, "symbol", "")
        if symbols and symbol not in symbols:
            continue

        expiry = ""
        if getattr(contract, "secType", "") == "OPT":
            expiry = getattr(contract, "lastTradeDateOrContractMonth", "")

        execution = fill.execution
        cr = fill.commissionReport
        fills.append(FillEvent(
            order_id=execution.orderId,
            perm_id=execution.permId,
            client_id=execution.clientId,
            order_ref=getattr(execution, "orderRef", "") or "",
            exec_id=execution.execId,
            symbol=symbol,
            sec_type=getattr(contract, "secType", ""),
            expiry=expiry,
            strike=float(getattr(contract, "strike", 0.0)),
            right=getattr(contract, "right", ""),
            side=execution.side,
            shares=_safe_float(execution.shares),
            price=_safe_float(execution.price),
            time=str(execution.time),
            commission=_safe_float(cr.commission),
            realized_pnl=_safe_float(cr.realizedPNL),
            currency=cr.currency or getattr(contract, "currency", ""),
        ))

    fills.sort(key=lambda f: (f.time, f.order_id, f.exec_id))
    return fills


_FILL_LEDGER = Path(__file__).parent / "config" / "fill_ledger.json"


def persist_fills(fills: list[FillEvent], path: Path = _FILL_LEDGER) -> int:
    """Append new fills to the local ledger, deduped by exec_id.

    Returns the number of newly added fills.
    """
    existing: dict[str, dict] = {}
    if path.exists():
        existing = {f["exec_id"]: f for f in json.loads(path.read_text())}

    added = 0
    for fill in fills:
        if fill.exec_id not in existing:
            existing[fill.exec_id] = asdict(fill)
            added += 1

    if added:
        all_fills = sorted(existing.values(), key=lambda f: (f["time"], f["exec_id"]))
        path.write_text(json.dumps(all_fills, indent=2) + "\n")

    return added


def load_fill_ledger(
    path: Path = _FILL_LEDGER,
    symbol: str | None = None,
    side: str | None = None,
) -> list[FillEvent]:
    """Load persisted fills from the ledger, optionally filtered."""
    if not path.exists():
        return []

    fills = []
    for row in json.loads(path.read_text()):
        if symbol and row["symbol"] != symbol:
            continue
        if side and row["side"] != side:
            continue
        fills.append(FillEvent(**row))
    return fills
