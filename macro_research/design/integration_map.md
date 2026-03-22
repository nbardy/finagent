# Integration Map: macro_research ↔ ikbr_trader

How the macro research system connects to every existing module.

---

## 1. Data Inputs: What macro_research needs from the repo

### From `ibkr.py` — Live market data

| Function | What it gives us | Use in macro research |
|----------|-----------------|----------------------|
| `get_portfolio()` | All positions with P&L, greeks, DTE | Full portfolio context for thesis generation |
| `get_spot(symbol)` | Current price for any symbol | Anchor data for forecasts |
| `get_option_quotes(symbol, specs)` | IV, greeks, bid/ask | Implied vol as sentiment indicator |
| `get_account_summary()` | NetLiq, buying power, margin | Position sizing constraints |
| `get_open_orders()` | Pending orders | Avoid proposing duplicate trades |
| `get_recent_fills()` | Recent executions | Context for "what we just did" |

**Critical insight**: `ibkr.py` requires an IBKR Gateway connection. Macro
research should work WITHOUT a live connection (using cached/yfinance data)
but produce BETTER results WITH one.

### From `config/` — Persistent state

| File | What it contains | Use in macro research |
|------|-----------------|----------------------|
| `portfolio_state.json` | EWY PMCC inventory ONLY | NOT sufficient for macro context |
| `pmcc_config.json` | Connection params, strategy settings | Connection details for live data |
| `regime_state.json` | CRISIS/HIGH_VOL/LOW_VOL/NORMAL + VIX data | Regime context for thesis generation |

**Gap**: There's no `full_portfolio_snapshot.json`. The portfolio.py only
saves PMCC-specific state. Macro research needs a full-portfolio exporter.

### From `yfinance` (already a dependency)

Broad market data without IBKR connection:
- SPY, QQQ, TLT, EWY, VIX — prices and fundamentals
- Sector ETF prices for rotation analysis
- Historical data for returns/vol calculation

### From `helpers/urgent_hedge_types.py` — Reusable types

| Type | Reuse |
|------|-------|
| `MacroScenario` | Directly usable for macro thesis scenario modeling |
| `MacroScenarioSet` | Container for thesis-driven scenarios with probabilities |
| `PortfolioBook` | Portfolio representation for scenario pricing |

These types are ALREADY the right abstraction. A macro thesis produces
scenarios; those scenarios can be priced against the portfolio using
the existing `helpers/scenario_pricing.py` pipeline.

---

## 2. Output Paths: Where macro_research writes to

### Direct outputs (new)

```
macro_research/{date}/{run_id}/
  thesis.md              — the thesis
  data_context.json      — injected data (not hallucinated)
  forecast.json          — probability intervals
  proposed_trades.json   — trade recommendations
  kill_conditions.md     — falsifiability criteria
```

### Bridged outputs (existing paths)

| macro_research output | Bridge to | Existing consumer |
|----------------------|-----------|-------------------|
| proposed_trades.json | `orders/{date}/macro_thesis_{slug}.json` | `executor.py` |
| scenarios from forecast.json | `MacroScenarioSet` | `helpers/urgent_hedge.py` |
| thesis + scenarios | scenario input JSON | `scenario_analyzer.py` |
| macro regime assessment | `config/regime_state.json` | `regime_detector.py`, `main.py` |

### The executor bridge

macro_research proposes trades like:
```json
{"ticker": "TLT", "direction": "long", "entry": {"type": "limit", "price": 87.0}}
```

executor.py expects:
```json
{
  "contract": {"secType": "STK", "symbol": "TLT", "exchange": "SMART", "currency": "USD"},
  "action": "BUY",
  "tranches": [{"quantity": 100, "lmtPrice": 87.0}]
}
```

A `macro_to_executor()` converter bridges the gap. This is a thin function,
not a new module.

---

## 3. The `custom_scripts/research_session.py` precedent

THIS IS THE MOST IMPORTANT FILE. It already does what we want:

```python
def do_research(topic, ticker, x_username, research_prompt):
    """3-turn Codex research:
       1. Collect sources + loose notes
       2. Synthesize analysis files
       3. Write conclusions + final_report.md
    """
```

It uses `codex -p "..."` for multi-turn research, writes to structured
directories under `research_sessions/`, and records thread IDs for
resumability.

**This is the execution model we should follow.** Not the anthropic SDK.
Not raw `claude -p`. The research_session.py pattern of:
1. Build a prompt from templates + context
2. Shell out to `codex -p` (or `claude -p`)
3. Write structured output to a directory
4. Record metadata for resumability

### What research_session.py does right

- Multi-turn: 3 separate Codex invocations, each building on prior output
- Structured output: `loose_notes/`, `documents/`, `analysis/`, `conclusions/`
- Metadata: `session.json` with thread_id, turn history, timestamps
- Context injection: latest tweet, X account config, custom prompt
- Resumability: thread_id allows continuing a research session

### What research_session.py could do better

- No data pre-fetching (relies on Codex to find data via web)
- No schema validation on outputs
- No integration with executor or scenario analyzer
- The 3-turn structure is hardcoded, not configurable

---

## 4. The `helpers/urgent_hedge_types.py` connection

The macro thesis → scenario → portfolio impact pipeline already exists:

```
MacroScenario
  label: str                    # "rate_shock_up_100bp"
  horizon_days: int             # 90
  spot_move_pct: float          # -0.15
  vol_shift: float              # +0.10
  probability: float            # 0.25

MacroScenarioSet
  thesis: str                   # "Fed holds through 2025"
  scenarios: tuple[MacroScenario, ...]
  reference_spot: float
  risk_free_rate: float
```

A macro thesis literally IS a `MacroScenarioSet`. The forecast intervals
map directly to `MacroScenario` objects:

```
Forecast interval:
  [-0.20, -0.10], probability=0.35, "10Y > 5%, tech reprices"

MacroScenario:
  label="rate_shock_up", horizon_days=90,
  spot_move_pct=-0.15 (midpoint), vol_shift=+0.05,
  probability=0.35
```

Once we have this mapping, we can:
1. Run `option_lines_future_value()` to price the current portfolio under each scenario
2. Run `evaluate_candidate()` to score potential hedges
3. Run `build_execution_bundle()` to create executable hedge proposals

**This is the integration attempt 1 missed entirely.** The types and
pipeline already exist. Macro research just needs to produce
`MacroScenarioSet` as one of its outputs.

---

## 5. The `scenario_analyzer.py` connection

The scenario analyzer takes:
```json
{
  "symbol": "SPY",
  "budget": 10000,
  "spot": 5100,
  "iv": 0.18,
  "scenarios": [
    {"label": "rate_cut", "move": 0.10, "probability": 0.25},
    {"label": "base", "move": 0.02, "probability": 0.45},
    {"label": "rate_shock", "move": -0.15, "probability": 0.30}
  ],
  "instruments": [
    {"label": "Stock", "type": "stock"},
    {"label": "ATM LEAP", "type": "call", "strike_pct": 1.0, "expiry": "20280121"}
  ]
}
```

And outputs a return matrix across instruments and scenarios with
expected values, probability of loss, best/worst cases.

A macro thesis can generate exactly this input format. The flow:
1. macro_research generates thesis + forecast intervals
2. Convert forecast intervals to scenario_analyzer input
3. Run scenario_analyzer to compare instrument strategies
4. Include the return matrix in the research output

---

## 6. The `regime_detector.py` connection

The regime detector outputs:
```json
{
  "state": "NORMAL",
  "vix": 18.5,
  "vix3m": 20.2,
  "rv30": 0.14,
  "iv_rv_spread": 0.04,
  "backwardation": false,
  "action": "SELL_WEEKLY"
}
```

This should be an INPUT to macro research, not an output. The current
regime constrains which trades make sense:
- CRISIS: don't propose new longs, consider hedges
- HIGH_VOL: vol selling opportunities, but be careful with direction
- NORMAL: standard thesis-driven trades
- LOW_VOL: cheap hedges, consider tail risk protection

---

## 7. Full data flow (attempt 2 architecture)

```
                    ┌─────────────────────────┐
                    │   PRE-FETCH (Python)     │
                    │                          │
                    │  yfinance → broad market  │
                    │  ibkr.py → portfolio     │
                    │  regime_detector → regime │
                    │                          │
                    │  Writes: data_context.json│
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │  GENERATE (claude -p)    │
                    │                          │
                    │  Reads: philosophy.md    │
                    │         researcher.md    │
                    │         data_context.json│
                    │         task prompt      │
                    │                          │
                    │  Writes: thesis.md       │
                    │          forecast.json   │
                    │          scenarios.json  │
                    │          trades.json     │
                    │          kill_conds.md   │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │  POST-PROCESS (Python)   │
                    │                          │
                    │  forecast → MacroScenarios│
                    │  trades → executor format │
                    │  scenarios → analyzer run │
                    │                          │
                    │  Writes:                 │
                    │   scenario_matrix.json   │
                    │   portfolio_impact.json  │
                    │   executor_ready.json    │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │  REVIEW (claude -p)      │
                    │                          │
                    │  Reads: everything above │
                    │  Writes: summary.md      │
                    │         critique.md      │
                    └─────────────────────────┘
```

Four phases:
1. **Pre-fetch**: Python script gathers real data (no hallucination)
2. **Generate**: Claude writes the thesis (reasoning is the product)
3. **Post-process**: Python converts outputs to existing formats
4. **Review**: Claude reads everything and writes a summary/critique

Phases 1 and 3 are Python (deterministic, fast, typed).
Phases 2 and 4 are Claude (reasoning, slow, creative).

This keeps the LLM doing what it's good at (reasoning) and Python doing
what it's good at (data fetching, format conversion, computation).

---

## 8. What needs to be built (minimal scope)

### New files

| File | Purpose | Effort |
|------|---------|--------|
| `custom_scripts/macro_thesis.py` | Orchestrator: pre-fetch → claude -p → post-process | Medium |
| `custom_scripts/fetch_macro_data.py` | Pre-fetch broad market + portfolio data | Small |
| `custom_scripts/macro_to_executor.py` | Convert proposed trades to executor format | Small |
| `prompts/philosophy.md` | Adapted from quant-ai-advisor shared-base | Small (copy+edit) |
| `prompts/macro_researcher.md` | Thesis generation instructions | Small |
| `prompts/macro_reviewer.md` | Review/critique instructions | Small |

### Existing files to modify

| File | Change | Why |
|------|--------|-----|
| `portfolio.py` | Add `full_snapshot()` that exports ALL positions | Need full portfolio, not just PMCC |
| `helpers/urgent_hedge_types.py` | Add `from_forecast_intervals()` on MacroScenarioSet | Bridge forecast → scenarios |

### Nothing else changes

The executor, scenario analyzer, regime detector, ibkr module, option
pricing — none of these need modification. The macro research system
produces data in their existing input formats.
