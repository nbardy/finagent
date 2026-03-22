# Attempt 2: Design Sketch

## Core insight

The repo already has all the pieces. Macro research isn't a new system —
it's an orchestration layer that connects existing modules via Claude.

```
fetch_macro_data.py  →  data_context.json
claude -p            →  thesis.md, forecast.json, trades.json
post_process         →  scenario_matrix.json, executor_ready.json
claude -p            →  summary.md
```

---

## Execution model: `claude -p` / `codex -p`

Following the `custom_scripts/research_session.py` precedent:

```python
# In custom_scripts/macro_thesis.py

import subprocess

def run_claude(prompt: str, output_dir: Path) -> str:
    """Shell out to claude CLI. Inherits user's CLAUDE.md, MCP servers, tools."""
    result = subprocess.run(
        ["claude", "-p", prompt, "--allowedTools", "Write,Read,Glob,Grep"],
        capture_output=True, text=True, cwd=str(output_dir),
    )
    return result.stdout
```

Or for codex:
```python
def run_codex(prompt: str, output_dir: Path) -> str:
    result = subprocess.run(
        ["codex", "-p", prompt, "--full-auto"],
        capture_output=True, text=True, cwd=str(output_dir),
    )
    return result.stdout
```

No SDK. No API key management. No new dependencies.

---

## Phase 1: Pre-fetch (`fetch_macro_data.py`)

Gathers real data and writes `data_context.json`:

```python
import yfinance as yf
import json
from pathlib import Path
from datetime import datetime

BROAD_MARKET = ["SPY", "QQQ", "TLT", "EWY", "GLD", "VIX"]
SECTOR_ETFS = ["XLF", "XLK", "XLE", "XLV", "XLI", "XLU"]

def fetch_macro_snapshot() -> dict:
    snapshot = {"fetched_at": datetime.now().isoformat(), "data": {}}

    # Broad market prices + key metrics
    for sym in BROAD_MARKET:
        t = yf.Ticker(sym)
        info = t.info
        snapshot["data"][sym] = {
            "price": info.get("regularMarketPrice"),
            "prev_close": info.get("regularMarketPreviousClose"),
            "day_change_pct": info.get("regularMarketChangePercent"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "50d_ma": info.get("fiftyDayAverage"),
            "200d_ma": info.get("twoHundredDayAverage"),
        }

    # Yield proxies (from TLT, SHY, IEF)
    # VIX term structure (from VIX, VIX3M)
    # etc.

    return snapshot
```

**With IBKR connection** (optional, richer):
```python
from ibkr import connect, get_portfolio, get_account_summary

def fetch_portfolio_context() -> dict:
    with connect(client_id=17, readonly=True) as ib:
        positions = get_portfolio(ib)
        summary = get_account_summary(ib)
    return {
        "positions": [asdict(p) for p in positions],
        "account": summary,
    }
```

**With regime detector**:
```python
import json
regime_path = Path("config/regime_state.json")
if regime_path.exists():
    snapshot["regime"] = json.loads(regime_path.read_text())
```

Output: `{run_dir}/data_context.json` — real numbers, sourced, timestamped.

---

## Phase 2: Generate thesis (`claude -p`)

Prompt composed from files:

```bash
cat prompts/philosophy.md prompts/macro_researcher.md > /tmp/system.md
# Inject data context
echo "## CURRENT DATA" >> /tmp/system.md
cat {run_dir}/data_context.json >> /tmp/system.md
# Inject task
echo "## TASK" >> /tmp/system.md
echo "Generate a macro thesis about: {focus}" >> /tmp/system.md

claude -p "$(cat /tmp/system.md)" \
  --allowedTools Write,Read \
  --output-dir {run_dir}
```

Claude writes files to `{run_dir}/`:
- `thesis.md` — INPUTS/OUTPUT/SENSITIVITY + kill conditions
- `forecast.json` — probability intervals mapped to inputs
- `proposed_trades.json` — specific trade recommendations
- `reasoning.md` — the CoT (this IS the stdout, captured)

The prompt instructs Claude to write these files. Claude's stdout
is the chain of thought — captured to `reasoning.md`.

### Key prompt design

**Philosophy** stays constant (adapted from quant-ai-advisor shared-base):
- First principles, not narratives
- Banned language
- Source hierarchy
- Falsifiability requirement

**Researcher** instructions (per run):
- Read data_context.json FIRST
- Write thesis.md with INPUTS/OUTPUT/SENSITIVITY structure
- Write forecast.json with 3-5 intervals per horizon
- Write proposed_trades.json only after thesis + forecast
- Write kill_conditions.md with explicit invalidation criteria
- Every number must cite data_context.json or state your assumption

**No JSON-only constraint.** Let Claude write markdown for the thesis
and JSON for structured data. Each file type uses the format that
makes sense for its content.

---

## Phase 3: Post-process (Python)

Convert Claude's output to existing formats:

### 3a. Forecast → MacroScenarioSet

```python
from helpers.urgent_hedge_types import MacroScenario, MacroScenarioSet

def forecast_to_scenarios(forecast: dict, reference_spot: float) -> MacroScenarioSet:
    scenarios = []
    for iv in forecast["intervals"]:
        lo, hi = iv["interval"]
        midpoint = (lo + hi) / 2
        scenarios.append(MacroScenario(
            label=iv["description"][:40],
            horizon_days=90,  # from forecast horizon
            spot_move_pct=midpoint,
            vol_shift=0.0,  # could estimate from move magnitude
            probability=iv["probability"],
        ))
    return MacroScenarioSet(
        thesis=forecast.get("notes", ""),
        scenarios=tuple(scenarios),
        reference_spot=reference_spot,
        risk_free_rate=0.045,
    )
```

### 3b. Proposed trades → executor format

```python
def trade_to_executor(trade: dict) -> dict:
    action = "BUY" if trade["direction"] == "long" else "SELL"
    contract = {
        "secType": "STK",
        "symbol": trade["ticker"],
        "exchange": "SMART",
        "currency": "USD",
    }
    # Handle options legs if present
    if trade.get("legs"):
        # Convert to BAG contract...
        pass

    return {
        "contract": contract,
        "action": action,
        "tif": "GTC",
        "tranches": [{
            "quantity": 100,  # default, user adjusts
            "lmtPrice": trade.get("entry", {}).get("price", 0),
            "note": f"macro_thesis: {trade.get('thesis_summary', '')[:40]}",
        }],
    }
```

### 3c. Run scenario analyzer

```python
from scenario_analyzer import analyze

def run_scenarios(forecast: dict, spot: float, budget: float):
    config = {
        "symbol": "SPY",
        "budget": budget,
        "spot": spot,
        "iv": 0.18,
        "scenarios": [
            {"label": iv["description"][:30],
             "move": (iv["interval"][0] + iv["interval"][1]) / 2,
             "probability": iv["probability"]}
            for iv in forecast["intervals"]
        ],
        "instruments": [
            {"label": "Stock", "type": "stock"},
            {"label": "ATM LEAP", "type": "call", "strike_pct": 1.0, "expiry": "20280121"},
        ],
    }
    return analyze(config)
```

### 3d. Portfolio impact assessment

```python
from helpers.scenario_pricing import option_lines_future_value

def assess_portfolio_impact(scenarios: MacroScenarioSet, portfolio_book):
    """Price current portfolio under each thesis scenario."""
    results = {}
    for scenario in scenarios.scenarios:
        pnl = option_lines_future_value(portfolio_book.positions, scenario)
        results[scenario.label] = pnl
    return results
```

---

## Phase 4: Review (`claude -p`)

Second Claude invocation reads everything and writes a summary:

```bash
claude -p "You are reviewing a macro research run in {run_dir}/.
Read ALL files. Write summary.md with:
1. Thesis quality assessment
2. Forecast calibration check (do probabilities make sense?)
3. Kill condition completeness
4. Trade recommendations vs portfolio fit
5. What's missing or weak

Then write critique.md with aggressive pushback on weak reasoning.

Rules: only discuss what's in the files. If something is missing, say so.
Do not generate analysis. You are a reviewer, not a researcher." \
  --allowedTools Read,Write,Glob
```

---

## Folder structure

```
macro_research/
  prompts/
    philosophy.md           # constant, adapted from quant-ai-advisor
    macro_researcher.md     # thesis generation instructions
    macro_reviewer.md       # review instructions
    banned_words.md         # extended banned language list
  {YYYY-MM-DD}/
    {run_id}/               # short slug like "rates_001"
      data_context.json     # pre-fetched real data
      thesis.md             # INPUTS/OUTPUT/SENSITIVITY
      forecast.json         # probability intervals
      proposed_trades.json  # trade recommendations
      kill_conditions.md    # falsifiability criteria
      reasoning.md          # CoT captured from stdout
      # Post-processed:
      scenario_matrix.json  # from scenario_analyzer
      portfolio_impact.json # from scenario_pricing
      executor_ready.json   # from macro_to_executor
      # Reviewed:
      summary.md            # Claude's summary
      critique.md           # Claude's pushback
```

ISO dates. Flat within the day. Human-readable run IDs.

---

## CLI interface

```bash
# Full pipeline
uv run python custom_scripts/macro_thesis.py --focus "US rates" --run-id rates_001

# Just pre-fetch (no Claude)
uv run python custom_scripts/fetch_macro_data.py --output macro_research/2025-03-10/rates_001/

# Just generate (data already fetched)
uv run python custom_scripts/macro_thesis.py --data macro_research/2025-03-10/rates_001/data_context.json

# Just post-process (thesis already generated)
uv run python custom_scripts/macro_thesis.py --post-process macro_research/2025-03-10/rates_001/

# Just review
uv run python custom_scripts/macro_thesis.py --review macro_research/2025-03-10/rates_001/

# Multiple theses in parallel
uv run python custom_scripts/macro_thesis.py --focus "rates" --focus "china" --focus "energy" --parallel
```

Each `--focus` becomes a separate `claude -p` invocation running in parallel.

---

## What this design gets right vs attempt 1

| Issue from critique | How attempt 2 fixes it |
|-------------------|----------------------|
| SDK instead of CLI | `subprocess.run(["claude", "-p", ...])` |
| JSON-only kills CoT | Markdown for prose, JSON for structured data |
| N-thesis in one shot | One thesis per invocation, parallel |
| No data fetching | Pre-fetch phase with yfinance + IBKR |
| Over-engineered types | Plain files, post-process to existing types |
| Monolithic prompt | Decomposed into philosophy/researcher/data/task |
| Portfolio = PMCC only | Full portfolio export via IBKR |
| No integration | Bridges to executor, scenario analyzer, hedge system |
| Bad folder names | ISO dates, flat structure, readable run IDs |
| No error handling | Each phase independent, partial results survive |
| No review workflow | Explicit review phase with Claude |

---

## Open questions for the user

1. Should parallel theses share data_context.json or each fetch independently?
2. Is `codex -p` preferred over `claude -p`? (codex has web access)
3. Should we support IBKR-offline mode (yfinance only)?
4. How many theses per run? (I'd default to 1, user specifies focus)
5. Should proposed trades auto-write to `orders/{date}/` or require manual review?
6. Should the review phase auto-run or be opt-in?
