# Patterns, Gaps, and Design Notes

Working notes from deep-diving both repos.

---

## The research_session.py precedent is the real starting point

`custom_scripts/research_session.py` already solves 80% of the problem:
- Multi-turn Codex research with structured output directories
- Session manifest with thread_id for resumability
- Context injection (latest tweet, account config)
- Three-phase execution: collect → synthesize → conclude

The macro thesis system should be a SIBLING of research_session.py, not
a reimagining. Same patterns, different prompt + different data sources.

```
custom_scripts/
  research_session.py    # existing: deep research on a topic
  macro_thesis.py        # new: macro thesis generation
  fetch_macro_data.py    # new: pre-fetch data for macro context
```

Both follow the same structure:
1. Assemble context
2. Shell out to codex/claude
3. Write structured output
4. Record metadata

---

## The MacroScenario bridge is the killer feature

What makes this more than "Claude writes a blog post about macro":

```
Macro thesis  →  forecast intervals  →  MacroScenarioSet
                                              ↓
                                    scenario_pricing.py
                                              ↓
                                    portfolio P&L per scenario
                                              ↓
                                    "If this thesis is right,
                                     your portfolio loses $42K"
```

This is the value prop. Not "here's a macro view" but "here's a macro
view AND here's what it means for YOUR portfolio AND here's what to
do about it."

The pipeline:
1. Claude generates thesis with forecast intervals
2. Python converts intervals to `MacroScenario` objects
3. `option_lines_future_value()` prices the portfolio under each scenario
4. `scenario_analyzer.analyze()` compares instrument strategies
5. `build_execution_bundle()` creates executable hedge proposals

All of steps 2-5 exist today. Step 1 is what we're building.

---

## What quant-ai-advisor gets wrong that we shouldn't copy

### 1. The 2715-line index.ts monolith

The entire backend — data providers, cache, state management, tool registry,
harness logic, SSE streaming — is one file. This is a maintenance nightmare.
For ikbr_trader, each concern is already its own module. Keep it that way.

### 2. Presenter can't push back

The Presenter is a "translator" that can only read state. If the Researcher
produced a bad thesis, the Presenter faithfully presents it. There's no
quality gate between research and presentation.

In our system, the Review phase (phase 4) IS the quality gate. The reviewer
reads all files and writes critique.md. If the critique is damning, the user
can regenerate.

### 3. Portfolio is just ticker → count

quant-ai-advisor's portfolio is `{"AAPL": 100, "GOOGL": 50}`. No cost basis,
no options positions, no greeks, no P&L. ikbr_trader has rich Position objects
with all of this. We should use the full Position data.

### 4. No scenario pricing

quant-ai-advisor generates forecasts but never prices them against the
portfolio. The forecast is decorative — it tells you probabilities but not
dollar impact. Our system bridges this gap via the existing scenario_pricing
module.

### 5. OpenRouter multi-model abstraction

quant-ai-advisor supports DeepSeek, Gemini, Kimi, GPT-5 via OpenRouter.
This adds complexity. We use `claude -p` which is always Claude. Model
selection is a flag (`--model opus`), not an abstraction layer.

### 6. Supabase as state store

A database for what should be files. The state is read at start, mutated,
and written back. Files do this naturally. Git does this with history.
No database needed.

---

## What quant-ai-advisor gets right that we MUST copy

### 1. Analysis only exists if persisted

"If you don't call set_thesis, there is no thesis."

For us: "If you don't write thesis.md, there is no thesis."

The model MUST write files. Stdout reasoning is captured but is not the
deliverable. The files ARE the deliverable.

### 2. Dependency chain enforcement

Data → thesis → forecast → trades. You can't skip steps.

For us: the prompt says "you must read data_context.json before writing
thesis.md" and "you must write thesis.md before forecast.json" and "you
must write forecast.json before proposed_trades.json."

### 3. Forecast intervals mapped to inputs

The single best idea. Every probability interval maps to specific input
assumptions, not "bull/bear/base" narratives.

### 4. INPUTS/OUTPUT/SENSITIVITY thesis structure

Forces quantitative rigor. Without this structure, you have not done
analysis.

### 5. Banned language enforcement

Eliminates vibes. Forces specificity. Extend for macro.

### 6. Kill conditions as required output

Falsifiability is not optional. Every thesis must state what would
invalidate it.

### 7. Leading vs lagging indicator awareness

The model should explicitly identify which of its inputs are leading
(predictive) vs lagging (confirmatory). A thesis built entirely on
lagging indicators is a thesis about the past.

---

## Data context schema

What `data_context.json` should contain:

```json
{
  "fetched_at": "2025-03-10T14:30:00Z",
  "sources": {
    "yfinance": ["SPY", "QQQ", "TLT", "VIX", "EWY", "GLD"],
    "ibkr": true,
    "regime": true
  },

  "broad_market": {
    "SPY": {"price": 5100, "change_1d": -0.3, "change_1m": 2.1, "change_3m": -1.5, "pe": 21.2, "200d_ma": 4950},
    "QQQ": {"price": 440, ...},
    "TLT": {"price": 88.50, ...},
    "GLD": {"price": 2150, ...}
  },

  "volatility": {
    "VIX": 18.5,
    "VIX3M": 20.2,
    "backwardation": false,
    "SPY_rv30": 0.14,
    "VIX_percentile_1y": 35
  },

  "rates_proxy": {
    "TLT_price": 88.50,
    "TLT_yield_approx": 4.55,
    "SHY_price": 82.10,
    "IEF_price": 94.20,
    "curve_slope_TLT_SHY": -0.15
  },

  "regime": {
    "state": "NORMAL",
    "action": "SELL_WEEKLY",
    "vix": 18.5,
    "backwardation": false
  },

  "portfolio": {
    "net_liq": 875000,
    "cash": 73000,
    "buying_power": 150000,
    "positions": [
      {"symbol": "AAOI", "qty": 67, "market_value": 4200, "pnl": -800, "pct": -16.0},
      {"symbol": "IQE", "qty": 49000, "market_value": 12000, "pnl": -3000},
      {"symbol": "EWY", "sec_type": "OPT", "qty": 50, "strike": 140, "expiry": "20280121"},
      {"symbol": "CODA", "qty": 1817, "market_value": 25000}
    ],
    "sector_exposure": {
      "tech": 0.35,
      "korea": 0.40,
      "defense": 0.15,
      "cash": 0.10
    }
  }
}
```

This gives the model REAL data to reason over. Every number is sourced.
No hallucination possible for anything in this file.

---

## Prompt file drafts

### prompts/philosophy.md (sketch)

```markdown
# Quantitative Research Philosophy

## Identity

You are a quantitative macro researcher. You build investment views from
data, not from narratives.

## Method

1. START with data in data_context.json — these are real, current numbers
2. BUILD axioms: "If X stays at Y, then Z follows because..."
3. CHAIN axioms into a model: Axiom 1 + Axiom 2 → Conclusion
4. IDENTIFY sensitivities: which inputs drive the conclusion?
5. COMPARE to market pricing: where is the gap?

## Rules

- Every claim must cite a number from data_context.json or state
  "ASSUMPTION: [what you're assuming and why]"
- Every thesis needs INPUTS → OUTPUT → SENSITIVITY structure
- Every thesis needs kill conditions (what would invalidate it)
- Forecast intervals map to input assumptions, not scenarios

## Banned Language

Never use: extreme, attractive, compelling, strong, weak, solid,
robust, deteriorating, improving (without numbers), headwinds,
tailwinds, uncertainty (without specifying what), mixed signals,
cautiously optimistic, risk-off, risk-on, priced in (without
implied probability), consensus expects (cite the actual number),
soft landing, hard landing (specify GDP growth and unemployment).

Instead: "SPY P/E 21.2x vs 10y median 18x" or "10Y yield 4.55%
implies equity risk premium of 3.0% vs 20y avg of 4.5%"
```

### prompts/macro_researcher.md (sketch)

```markdown
# Macro Thesis Generation

## Your Task

Read data_context.json. Generate ONE macro thesis.

## Output Files

Write these files in order. Each depends on the previous.

### 1. thesis.md

Structure:

    # [Title]

    ## Thesis Statement
    One paragraph summary.

    ## INPUTS
    - [Input 1]: [value] (source: data_context.json / ASSUMPTION)
    - [Input 2]: [value] (source: ...)

    ## MODEL
    Chain your axioms:
    - If [Input 1] + [Input 2] → [Conclusion 1]
    - If [Conclusion 1] + [Input 3] → [Conclusion 2]
    - Therefore: [Final output with numbers]

    ## OUTPUT
    - Fair value / target: [X]
    - Current level: [Y]
    - Implied gap: [Z%]

    ## SENSITIVITY
    - Most sensitive to: [which input]
    - If [input] changes by [amount]: [new output]
    - Second most sensitive: [input], impact: [amount]

    ## Kill Conditions
    This thesis is INVALIDATED if:
    1. [Specific condition with number and timeframe]
    2. [Another condition]

    ## Review Date: [date]

### 2. forecast.json

    {
      "asset": "what this forecast applies to",
      "horizons": {
        "3m": {
          "intervals": [
            {
              "interval": [-0.20, -0.10],
              "probability": 0.25,
              "description": "Which inputs cause this return range"
            }
          ],
          "logit_commentary": "Why these probabilities"
        },
        "6m": { ... }
      }
    }

Probabilities per horizon must sum to ~1.0.

### 3. proposed_trades.json

    {
      "trades": [
        {
          "ticker": "TLT",
          "direction": "long",
          "asset_type": "etf",
          "thesis_summary": "One line",
          "rationale": "Full paragraph with entry/exit logic",
          "entry": {"type": "limit", "price": 87.0},
          "stop_loss": "TLT < 82",
          "profit_target": "TLT > 98",
          "risk_reward": "1:2",
          "timeframe": "3-6 months",
          "position_size_rationale": "Why this much"
        }
      ]
    }

Only write this AFTER thesis.md and forecast.json exist.

## Rules
- Read data_context.json FIRST
- Cite specific numbers from it
- State assumptions explicitly
- Do not invent data not in data_context.json
- Write files in order: thesis.md → forecast.json → proposed_trades.json
```

---

## Open design questions

### 1. codex vs claude for generation

`codex -p` has web search capability. This matters for macro research
because the model might want to look up recent FOMC minutes or
employment data that isn't in data_context.json.

`claude -p` has tool access (Read, Write, Glob, Grep) and inherits
CLAUDE.md context.

Possible approach: use `codex -p` for generation (web access for
data enrichment) and `claude -p` for review (tool access for reading
files).

### 2. One thesis vs many

Attempt 1 tried to generate N theses in one shot. Attempt 2 says one
thesis per invocation. But should the orchestrator run N in parallel?

Proposal: `--focus` accepts multiple values. Each becomes a separate
`claude -p` invocation. They share data_context.json but produce
independent theses.

```bash
uv run python custom_scripts/macro_thesis.py \
  --focus "US rates trajectory" \
  --focus "China property resolution" \
  --focus "energy transition capex"
```

Three parallel invocations, three thesis directories, one shared data file.

### 3. Should proposed_trades.json be executor-compatible directly?

Two options:
a) Claude writes abstract trades, Python converts to executor format
b) Claude writes executor-compatible JSON directly

Option (a) is cleaner — Claude focuses on what to trade and why,
Python handles the IBKR-specific formatting (secType, exchange,
currency, tranche structure).

Option (b) risks Claude getting the format wrong and introduces
coupling between the thesis prompt and executor internals.

Go with (a).

### 4. Review phase: auto or manual?

Options:
a) Review runs automatically after generation
b) User explicitly runs `--review` when ready
c) Both: auto-review with option to re-review

Go with (a) by default. The review is cheap (one claude -p call) and
catches obvious issues. User can always re-review manually.

### 5. How does this connect to the future dashboard?

The file-based output is designed to be dashboard-friendly:
- Each run is a directory with known file names
- JSON files are structured for rendering
- Markdown files are human-readable
- The schema is implicit but consistent

A future dashboard (TUI, web, or Claude-native) reads the same files.
No format change needed.

---

## Comparison table: quant-ai-advisor vs attempt 2

| Aspect | quant-ai-advisor | attempt 2 |
|--------|-----------------|-----------|
| Runtime | Supabase Edge Function (Deno) | Python script → claude CLI |
| State store | Supabase JSONB | Files on disk |
| LLM | OpenRouter (multi-model) | claude/codex CLI |
| Data fetching | FMP + Alpha Vantage via tools | yfinance + IBKR pre-fetched |
| State persistence | Tool calls (set_thesis, etc) | File writes (thesis.md, etc) |
| Streaming | SSE events | stdout capture |
| UI | React + shadcn StatePanel | Terminal + markdown files |
| Resumability | Conversation DB + state | Directory + re-run |
| Review | Presenter phase (translator) | Review phase (critic) |
| Portfolio pricing | None | scenario_pricing.py |
| Trade execution | None (only proposals) | Bridges to executor.py |
| Scenario analysis | None | scenario_analyzer.py |
| Hedge proposals | None | urgent_hedge.py |
| Regime awareness | None | regime_detector.py |

The key advantage of attempt 2: it DOES something with the analysis.
quant-ai-advisor generates a thesis and displays it. We generate a thesis,
price it against the portfolio, compare instrument strategies, and
produce executable trade proposals.

---

## Risk: LLM output parsing

The biggest risk in this design is: Claude writes thesis.md, forecast.json,
proposed_trades.json — but what if the JSON is invalid? What if the thesis
is missing the SENSITIVITY section?

Mitigations:
1. Keep structured output (JSON) small and simple. Thesis is markdown
   (doesn't need parsing), forecast is a small JSON (3-5 intervals),
   trades is a small JSON.
2. Post-process validates before proceeding. If forecast.json is invalid,
   skip scenario pricing and flag it in the review.
3. The review phase explicitly checks for completeness.
4. If a file is missing, post-process logs it and continues with what
   exists. Partial results are better than no results.

This is fundamentally better than attempt 1's "parse one giant JSON blob"
approach. If forecast.json fails but thesis.md is good, we still have a
thesis. In attempt 1, a single malformed JSON character kills everything.
