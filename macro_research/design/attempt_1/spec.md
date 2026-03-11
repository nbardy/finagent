# Attempt 1: Macro Research Generator — Spec

## What was built

Three Python files that form a "macro thesis generator" pipeline:

### 1. `macro_types.py` — Domain types

Frozen dataclasses adapted from quant-ai-advisor's TypeScript `QuantState`:

- `ForecastInterval(interval, probability, description)` — one probability bucket
- `Forecast(horizon, intervals, logit_commentary, notes)` — probabilistic return forecast
- `Thesis(title, body, time_horizon_months, confidence, key_drivers)` — INPUTS/OUTPUT/SENSITIVITY model
- `MacroFact(label, detail, source, tags)` — one macro data point with provenance
- `OptionLeg(type, strike, expiration, action, contracts)` — single options leg
- `ProposedTrade(ticker, asset_type, direction, thesis_summary, description, ...)` — trade recommendation
- `MacroResearchOutput` — aggregator that holds thesis + facts + forecasts + trades + CoT, with `.save(dir)` method

`MacroResearchOutput.save()` writes:
- `research.json` — full structured output
- `chain_of_thought.md` — raw reasoning
- `portfolio_context.json` — portfolio snapshot
- `summary.md` — human-readable markdown

### 2. `macro_prompts.py` — Prompt framework

A `PHILOSOPHY` constant adapted from quant-ai-advisor's `shared-base.ts`:
- First-principles quantitative identity
- Banned language list (no vibes words)
- Leading vs lagging indicator awareness
- Probabilistic reasoning rules

A `build_research_prompt()` function that assembles:
- Philosophy preamble
- Portfolio context (if provided)
- Focus area (if provided)
- Task instructions: generate N independent theses
- Output format: strict JSON schema with CoT field

### 3. `macro_research.py` — Main orchestrator

- Loads portfolio from `portfolio_state.json` (default) or specified path
- Calls Claude via `anthropic` Python SDK
- Parses JSON response into `MacroResearchOutput` objects
- Writes to `macro_research/day_{mon_dd_yyyy}/{HH_MM_SS}_{uuid}/thesis_N_{slug}/`
- Generates an `index.json` linking all theses

CLI interface:
```
uv run python macro_research.py
uv run python macro_research.py --focus "rates" --theses 5 --model claude-opus-4-6
```

## Architecture diagram

```
User runs macro_research.py
    |
    v
load_portfolio() --> portfolio_state.json
    |
    v
build_research_prompt() --> giant prompt string
    |
    v
call_claude() --> anthropic SDK --> Claude API --> response text
    |
    v
extract_json() --> parse JSON from response
    |
    v
parse_response() --> list[MacroResearchOutput]
    |
    v
MacroResearchOutput.save() --> macro_research/day_.../thesis_N/
```

## What it adapted from quant-ai-advisor

| quant-ai-advisor | attempt_1 |
|-----------------|-----------|
| `shared-base.ts` PHILOSOPHY | `macro_prompts.py` PHILOSOPHY constant |
| `researcher.ts` execution sequence | Merged into `build_research_prompt()` output format |
| `quant.ts` TypeScript interfaces (Thesis, Forecast, etc.) | `macro_types.py` frozen dataclasses |
| Supabase edge function + SSE streaming | Replaced with single `anthropic.Anthropic()` API call |
| React StatePanel UI | Replaced with markdown summary file |
| Tool-driven state persistence (set_thesis, set_forecast_*) | Replaced with "output JSON in one shot" |

## Invocation model

Single-shot: one big prompt, one big JSON response, write to disk. No interactivity, no streaming, no tool use.
