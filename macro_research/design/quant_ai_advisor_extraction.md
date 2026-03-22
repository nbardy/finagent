# quant-ai-advisor: Complete Idea Extraction

A deep analysis of every reusable idea, pattern, and design decision from
the quant-ai-advisor codebase, evaluated for applicability to ikbr_trader's
macro research system.

---

## Table of Contents

1. [The Central Thesis: Analysis = State Mutation](#1-the-central-thesis)
2. [Prompt Architecture: Separation of Concerns](#2-prompt-architecture)
3. [The Philosophy Prompt: Epistemic Discipline](#3-the-philosophy-prompt)
4. [The Researcher Phase: Tool-Driven Persistence](#4-the-researcher-phase)
5. [The Presenter Phase: Translation, Not Generation](#5-the-presenter-phase)
6. [The Unified Mode: Single-Pass Agentic Loop](#6-the-unified-mode)
7. [Forecast Intervals: Probabilities Mapped to Inputs](#7-forecast-intervals)
8. [Thesis Structure: INPUTS/OUTPUT/SENSITIVITY](#8-thesis-structure)
9. [Banned Language: Anti-Vibes Enforcement](#9-banned-language)
10. [Tool Registry: Schema-Validated Dispatch](#10-tool-registry)
11. [Multi-Provider Data Fetching](#11-multi-provider-data)
12. [QuantState: The Single Source of Truth](#12-quantstate)
13. [SSE Streaming: Real-Time Tool Visibility](#13-sse-streaming)
14. [The StatePanel UI: Structured Analysis Display](#14-statepanel-ui)
15. [Incremental Progress: Checkpoints and Continue](#15-incremental-progress)
16. [Falsifiability: Kill Conditions as First-Class Data](#16-falsifiability)
17. [ProposedTrade: Structured Trade Recommendations](#17-proposed-trades)
18. [MacroFacts: Provenance-Tagged Data Points](#18-macro-facts)
19. [Stock Metrics Bundle: Comprehensive Instrument Profile](#19-stock-metrics)
20. [Options Chain Integration](#20-options-chain)
21. [Cache Layer: TTL + Deduplication](#21-cache-layer)
22. [Conversation Persistence: Resumable Analysis](#22-conversation-persistence)
23. [Source Hierarchy: Facts vs Opinions](#23-source-hierarchy)
24. [Time Horizon Awareness](#24-time-horizon)
25. [The Two-Phase Harness vs Single-Pass Trade-offs](#25-harness-tradeoffs)
26. [Applicability Map: What to Take, What to Leave](#26-applicability-map)

---

## 1. The Central Thesis: Analysis = State Mutation {#1-the-central-thesis}

The single most important idea in quant-ai-advisor, and the one attempt 1
completely missed:

> If you don't call `set_thesis`, there is no thesis. Writing analysis in
> prose accomplishes nothing — it doesn't persist.

The system treats the LLM as a *state machine operator*. The model doesn't
produce a document — it produces a sequence of state mutations via tool calls.
Each tool call is validated, persisted to a database, and visible to both
the UI and subsequent reasoning steps.

This means:
- **Partial results are valid.** If the model runs 3 of 5 tools before
  hitting a limit, the first 3 results exist in state. Nothing is lost.
- **Results are structured by construction.** The `set_thesis` tool has a
  schema. The thesis can't be malformed because the tool validates it.
- **The model can't hide work.** If it writes a brilliant analysis in prose
  but doesn't call `set_thesis`, the analysis doesn't exist. This forces
  the model to do the structured work, not just narrate.
- **State is inspectable.** At any point during execution, you can read
  the state and see exactly what's been established: thesis, forecasts,
  trades, facts. No ambiguity.

### How this applies to ikbr_trader

When using `claude -p` for macro research, we should structure the output
as a series of file writes, not as one monolithic document. Each "tool"
becomes a file:
```
macro_research/2025-03-10/run_001/
  thesis.md           # written first
  macro_facts.json    # written second
  forecast_3m.json    # written third
  forecast_6m.json    # written fourth
  proposed_trades.json # written last (requires thesis + forecasts)
```

If the model writes `thesis.md` and then crashes, we still have the thesis.
The equivalent of `set_thesis` is "write a file." The equivalent of QuantState
is "the directory."

This also means `claude -p` should be invoked with `--allowedTools Write`
so it can write files incrementally, not produce one big output.

---

## 2. Prompt Architecture: Separation of Concerns {#2-prompt-architecture}

quant-ai-advisor uses 5 prompt files:

| File | Purpose | Lines | When Used |
|------|---------|-------|-----------|
| `shared-base.ts` | Philosophy, epistemology, banned language, model structure | 184 | Always |
| `researcher.ts` | Execution sequence, tool usage rules, output rules | 142 | Researcher phase |
| `presenter.ts` | Translation rules, what to read, what to say | ~150 | Presenter phase |
| `unified.ts` | Combined researcher+presenter for single-pass | 83 | Single-pass mode |
| `tool-guide.ts` | Documentation for all tools | 92 | Researcher + unified |

The key insight: the *identity* (who you are) is separated from the *task*
(what to do this turn) and the *tools* (what you can use). This means:
- The philosophy doesn't change between phases
- The researcher prompt can focus purely on execution mechanics
- The presenter prompt can focus purely on communication
- The tool guide is a reference, not instruction

### What attempt 1 got wrong

It jammed everything into one `build_research_prompt()` function that
concatenates philosophy + task + schema + rules. The model gets a wall
of text where identity instructions blend into output format requirements.

### How to apply this to CLI-based research

Decompose into files on disk:

```
prompts/
  philosophy.md       # identity, epistemology, banned language
  researcher.md       # execution instructions for thesis generation
  data_context.md     # assembled per-run with current data
  task.md             # "generate a macro thesis about X"
```

Then compose them:
```bash
cat prompts/philosophy.md prompts/researcher.md data_context.md task.md | claude -p -
```

Or use `claude -p` with `--system-prompt` if it supports that. The point
is: the philosophy file is written once and reused across all research
invocations. The task file changes per run.

---

## 3. The Philosophy Prompt: Epistemic Discipline {#3-the-philosophy-prompt}

The shared-base prompt is 184 lines of epistemic discipline. The key sections
and why each matters:

### 3.1 First-Principles Model Building

```
Step 1: Identify Fundamental Drivers
  What actually determines this company's value?
  - Revenue: units × price, or users × ARPU, or transactions × take rate
  - Margins: gross margin trajectory, operating leverage, scale effects
  - Capital efficiency: ROIC, reinvestment rate, capital intensity
  - Duration: how long can growth/margins persist? moat strength?

Step 2: Establish Axioms
  Axioms are conditional statements you believe to be true:
  - "If EV adoption reaches X%, then battery demand will be Y GWh"
  - "This company's gross margin should converge to Z% at scale"

Step 3: Compose Into a Model
  Chain axioms: Axiom 1 + Axiom 2 → Revenue → + Margin axiom → Earnings

Step 4: Identify Key Sensitivities
  Which axioms matter most?

Step 5: Compare to Market Price
  Only after building your model, compare to current price.
```

**Why this matters for macro research**: Most LLM-generated "macro analysis"
is vibes. "The economy is slowing due to tight monetary policy." This
framework forces specificity: *which* economy, *how much* slowing, *what*
metrics show it, *what* would change if rates drop 50bp.

The axiom structure is powerful for macro because it creates falsifiable
chains:
- "If the 10Y stays above 4.5% for 6 months, then mortgage origination
  drops below X, then housing starts fall to Y, then GDP growth slows
  to Z%"
- Each link is testable. If mortgage origination doesn't drop despite
  high rates, the chain is broken and the thesis needs revision.

### 3.2 Source Hierarchy

```
Facts (extract and use):
- Earnings numbers, revenue, margins, guidance
- Product launches, FDA approvals, regulatory decisions
- Macro data: rates, inflation, employment figures

Opinions (ignore entirely):
- Analyst price targets and ratings
- "Why the stock moved today"
- Bullish/bearish interpretations

Source Hierarchy:
1. SEC filings: 10-K, 10-Q, 8-K, proxy statements
2. Company earnings releases and guidance
3. Financial press (extract facts, discard analysis)
```

**Why this matters**: LLMs are trained on a massive corpus of financial
opinions. Without this constraint, they'll reproduce consensus narratives.
The source hierarchy forces the model to cite *data*, not *analysis about
data*.

For macro research specifically, the source hierarchy should be adapted:
1. Federal Reserve publications (FOMC minutes, Beige Book)
2. BLS/BEA data releases (NFP, CPI, GDP)
3. Treasury/Fed data (yield curves, bank reserves)
4. Financial press (extract facts only)

### 3.3 Leading vs Lagging Indicators

```
Lagging: reported earnings, last quarter's revenue
Leading: pipeline, bookings, customer acquisition cost trends
```

For macro, this translates to:
- **Lagging**: GDP (quarterly, revised multiple times), unemployment rate
  (monthly, backward-looking)
- **Leading**: ISM new orders, initial jobless claims, yield curve slope,
  credit spreads, housing permits, consumer confidence surveys
- **Coincident**: industrial production, retail sales, personal income

The prompt should explicitly list which indicators are leading vs lagging
for macro analysis, because the model will otherwise treat all data as
equally informative.

---

## 4. The Researcher Phase: Tool-Driven Persistence {#4-the-researcher-phase}

The researcher prompt establishes a strict execution sequence:

```
1. FETCH — get_instrument_features(symbol)
2. SEARCH — max 2 searches for facts not in state
3. SET_THESIS — MANDATORY, must contain INPUTS/OUTPUT/SENSITIVITY
4. SET_FORECAST — MANDATORY before any trade proposal
5. ADD_PROPOSED_BUY — only after thesis + forecasts exist
6. EXIT
```

This sequence encodes *dependencies*: you can't set a thesis without data,
you can't forecast without a thesis, you can't propose trades without
forecasts.

### The "output rules" constraint

```
Your text output should be MINIMAL or NONE.
- Brief status if useful: "Fetching IONQ data..."
- NO conversational responses (Presenter does that)
- NO analysis in prose (call set_thesis)
- NO probability tables in text (call set_forecast_*)
```

This is the key constraint: the researcher is *not allowed to talk*.
Its only job is to mutate state via tools. This prevents the failure
mode where the model writes a brilliant 2000-word analysis in prose
but forgets to call `set_thesis`, leaving the Presenter with nothing.

### How to apply this to CLI-based research

In a `claude -p` context, we don't have separate phases. But we can
encode the dependency chain in the prompt:

```markdown
## Execution Order

You MUST create files in this order. Each step depends on the previous.

1. Write `data_snapshot.json` — current macro data points you're using
2. Write `thesis.md` — your thesis with INPUTS/OUTPUT/SENSITIVITY
3. Write `forecast.json` — probabilistic forecasts with input-driven intervals
4. Write `trades.json` — proposed trades (ONLY after thesis + forecast exist)
```

The file system IS the state. The dependency chain is: "file X must exist
before you write file Y."

---

## 5. The Presenter Phase: Translation, Not Generation {#5-the-presenter-phase}

The presenter prompt is 150 lines of "you are a translator":

```
Think of yourself as a news anchor reading a teleprompter. You don't write
the news — you read it. If the teleprompter is blank, you say "nothing to
report," not make something up.
```

And the decision tree:
```
1. Check stockInformation[ticker] → if NO: "I don't have data. Say 'continue'."
2. Check thesis → if NO: "Data gathered. Say 'continue' to build model."
3. Check forecasts → if NO: "Thesis set. Say 'continue' for probability forecasts."
4. Check proposedBuys → if NO: "Analysis complete. Say 'continue' for trades."
```

### Why this matters

The Presenter prevents confabulation. If the Researcher didn't fetch data,
the Presenter says "no data" instead of making up numbers. If the Researcher
didn't set a thesis, the Presenter says "no thesis" instead of improvising one.

This is the opposite of typical LLM chatbot behavior, where the model will
always produce *something* even if it has nothing substantive to say.

### How to apply this

In the CLI-based system, the "presenter" is Claude reading back the research
files and explaining them. This happens naturally: the user can ask Claude
to read `thesis.md` and summarize it, and Claude will see exactly what's
there (and nothing more).

But the principle — *never generate analysis that isn't grounded in
persisted state* — should be encoded in the review prompt:

```markdown
## Review Instructions

You are reviewing a macro research run. The research files are in {dir}.
Read ALL files before responding.

Rules:
- Only discuss what's IN the files. Don't add your own analysis.
- If a file is missing (e.g. no forecast.json), say so explicitly.
- If the thesis is incomplete (missing SENSITIVITY section), flag it.
- Your job is to explain and critique what's there, not to fill gaps.
```

---

## 6. The Unified Mode: Single-Pass Agentic Loop {#6-the-unified-mode}

The unified prompt combines researcher + presenter for a single-pass
experience:

```
You are operating in single-pass mode: you gather data, build analysis,
AND communicate with the user all in one continuous conversation.

Key Behaviors:
- You CAN and SHOULD use tools while also responding conversationally
- Stream your thinking — tell the user what you're doing as you do it
- After fetching data, IMMEDIATELY persist insights
```

### Trade-offs

**Single-pass pros:**
- Lower latency (one model call, not two)
- More natural conversation feel
- Model can course-correct mid-analysis based on what it finds

**Single-pass cons:**
- Model may stream conclusions before data is ready
- Harder to enforce "no prose analysis" rule
- If the model talks while working, the conversation gets noisy
- Tool calls interspersed with text make the output harder to parse

**Two-phase pros:**
- Clean separation of work from communication
- Researcher can focus purely on data + analysis
- Presenter gives a polished, complete summary
- Easier to enforce structured output

**Two-phase cons:**
- Higher latency (two full model calls)
- Full research history must be passed to Presenter
- If Researcher omits something, Presenter can't fix it

### How to apply this

For CLI-based research, the natural model is two-phase:
1. `claude -p "generate thesis"` → writes files (researcher)
2. `claude -p "review thesis in {dir}"` → reads files, explains (presenter)

But we could also do single-pass:
```bash
claude -p "Generate a macro thesis about X. Write your analysis to
macro_research/2025-03-10/run_001/. Explain your reasoning as you go."
```

The single-pass approach is simpler for the user (one command) but
produces noisier output. For macro research where the CoT is the product,
single-pass might actually be better — the user gets to see the
reasoning process, not just the conclusion.

---

## 7. Forecast Intervals: Probabilities Mapped to Inputs {#7-forecast-intervals}

This is one of the most valuable innovations in quant-ai-advisor:

```
❌ BAD:
{ interval: [-0.50, -0.20], probability: 0.45, description: "Bearish case" }

✓ GOOD:
{ interval: [-0.60, -0.30], probability: 0.35,
  description: "Revenue <$100M by 2025. Market reprices to 15x = $1.5B.
               Current $19B implies -70%." }
```

Each probability interval is mapped to *specific input assumptions*, not
vague scenarios. This means:
- The forecast is falsifiable (if revenue comes in at $150M, the -70% scenario
  is invalidated)
- The probabilities are grounded (you can debate whether revenue <$100M
  is 35% likely, not whether "bearish" is 45% likely)
- The forecast decomposes into testable components

### The interval structure

```typescript
intervals: [
  { interval: [-0.50, -0.30], probability: 0.15, description: "..." },
  { interval: [-0.30, -0.10], probability: 0.35, description: "..." },
  { interval: [-0.10, 0.10], probability: 0.30, description: "..." },
  { interval: [0.10, 0.30], probability: 0.15, description: "..." },
  { interval: [0.30, 0.50], probability: 0.05, description: "..." },
]
```

Rules:
- 3-5 intervals covering the probability space
- Probabilities sum to ~1.0
- Returns as decimals: -0.20 = -20%, 0.15 = +15%
- Each interval maps to specific input assumptions
- Different time horizons (1m, 3m, 6m) can have different distributions

### Logit commentary

```
logit_commentary: "I'm weighting the -30% to -10% interval at 35% because
the recent earnings miss + management's guidance cut suggest revenue
deceleration, but the installed base provides a floor."
```

This field explains *why* the probabilities are what they are. It's meta-
reasoning about the distribution, not about the scenarios. This is valuable
because it surfaces the model's uncertainty about its own uncertainty.

### How to apply this

For macro research, intervals should cover asset-class-level returns, not
single-stock returns:

```json
{
  "asset": "US_EQUITIES",
  "horizon": "6m",
  "intervals": [
    {
      "interval": [-0.20, -0.10],
      "probability": 0.20,
      "description": "Fed holds at 5.5%, 10Y above 5%. Earnings growth
                       decelerates to 3% y/y. Multiple compression to 17x."
    },
    {
      "interval": [-0.10, 0.05],
      "probability": 0.35,
      "description": "One rate cut in H2. Earnings grow 6%. 10Y settles
                       at 4.5%. Multiple holds at 19x."
    }
  ]
}
```

The forecast.json file in each research run should follow this structure
exactly.

---

## 8. Thesis Structure: INPUTS/OUTPUT/SENSITIVITY {#8-thesis-structure}

Every valuation/analysis MUST follow:

```
INPUTS (with sources):
- [Input 1]: [value] (source: [where this came from])
- [Input 2]: [value] (source: [your assumption, why])

OUTPUT:
- Fair value: $[X] or range $[X-Y]
- Current price: $[Z]
- Implied gap: [%]

SENSITIVITY:
- Most sensitive to: [which input]
- If [input] changes by [amount], fair value moves by [$]
```

The prompt is explicit: "Without this structure, you have not done analysis."

### Why this works

It forces the model to:
1. **Cite its inputs** — no handwaving about "current conditions"
2. **Be quantitative** — actual numbers, not adjectives
3. **Identify what matters** — the sensitivity section reveals which
   assumptions drive the conclusion
4. **Be falsifiable** — if Input 1 changes, the output changes predictably

### For macro research specifically

Macro theses should follow a modified version:

```
INPUTS:
- Fed funds rate: 5.25-5.50% (source: FOMC, Jan 2025)
- 10Y Treasury: 4.55% (source: Treasury.gov, Mar 10 2025)
- Core PCE y/y: 2.8% (source: BEA, Feb 2025 release)
- ISM Manufacturing: 47.8 (source: ISM, Feb 2025)
- S&P 500 EPS (trailing): $235 (source: FactSet)
- S&P 500 fwd P/E: 21x (source: FactSet)

MODEL:
- If core PCE stays above 2.5% through Q3, Fed holds rates through 2025
- If rates hold, 10Y likely stays 4.3-4.8% (term premium + no cuts)
- At 10Y = 4.5%, equity risk premium compresses to 3.0%
- At ERP 3.0%, fair P/E = 18-19x
- At $235 EPS × 18.5x = SPX fair value ~4350
- Current SPX: ~5100
- Implied gap: -15%

SENSITIVITY:
- Most sensitive to: core PCE trajectory
- If PCE drops to 2.3%: Fed cuts 2x, 10Y drops to 3.8%, fair P/E 20x,
  SPX fair value 4700 (gap narrows to -8%)
- If PCE rises to 3.2%: Fed holds or hikes, 10Y to 5.2%, fair P/E 16x,
  SPX fair value 3760 (gap widens to -26%)
```

This is what the thesis.md file should look like. The model should be
prompted to produce this structure, not just "write a macro thesis."

---

## 9. Banned Language: Anti-Vibes Enforcement {#9-banned-language}

```
NEVER use these words:
- "extreme" / "excessive" / "stretched" / "bubble"
- "attractive" / "compelling" / "interesting"
- "strong" / "weak" / "solid" / "robust"
- "deteriorating" / "improving" (without numbers)

NEVER use these phrases:
- "investors are worried about..."
- "the market expects..."
- "sentiment has shifted..."

INSTEAD be specific:
- "P/S 225x vs sector median 8x"
- "Fair value $4B vs current $19B"
- "Model requires 24x revenue growth to justify"
```

### Why this is brilliant

These words are "analysis-flavored noise." They sound analytical but convey
no information. "Valuations are stretched" — compared to what baseline?
By how much? On what metric? "Strong earnings" — how strong? vs consensus?
vs last quarter? vs 5-year average?

The banned word list forces the model out of its default register (which
is to produce plausible-sounding financial commentary) and into a specific,
quantitative register.

### Extended banned list for macro

For macro research, add:
- "headwinds" / "tailwinds" (meaningless metaphors)
- "uncertainty" (without specifying: uncertainty about WHAT, measured HOW)
- "mixed signals" (specify which signals say what)
- "cautiously optimistic" (oxymoron, means nothing)
- "risk-off" / "risk-on" (narrative labels for complex flows)
- "priced in" (without specifying the implied probability)
- "consensus expects" (cite the actual consensus number)
- "soft landing" / "hard landing" (specify: GDP growth of X%, unemployment of Y%)

### Implementation

The banned language section should live in the philosophy prompt file,
not in the task prompt. It's a persistent constraint, not a per-run
instruction.

For CLI-based research, it could also be a post-processing check:
```bash
# Check for banned words in the output
grep -i -w "extreme\|attractive\|strong\|bubble\|headwinds" thesis.md
```

---

## 10. Tool Registry: Schema-Validated Dispatch {#10-tool-registry}

The backend has a tool registry pattern:

```typescript
const toolRegistry: Record<string, ToolHandler> = {
  search: {
    schema: SearchArgsSchema,     // Zod validation
    handler: async (state, args) => { ... },
    persists: false,
  },
  set_thesis: {
    schema: ThesisArgsSchema,
    handler: async (state, args) => {
      state = setThesis(state, args);
      return { state, result: { status: 'success' } };
    },
    persists: true,
  },
};
```

Each tool has:
- A Zod schema that validates arguments before execution
- A handler that receives validated args + current state
- A `persists` flag indicating whether state should be saved after
- Return type of `{ state, result }` — mutated state + result for LLM

### The dispatch loop

```
Loop:
  1. Call LLM with tools available
  2. Parse tool calls from response
  3. For each tool call:
     a. Validate args with schema
     b. Execute handler
     c. If persists, save state to DB
     d. Emit SSE event (tool_use → tool_complete)
  4. Append tool results to LLM history
  5. Continue loop if tools were called, else exit
```

### How to apply this

In a CLI context, "tools" are file writes. But the validation pattern
is still useful. We could have a schema file that describes what each
output file should contain:

```json
// schemas/thesis.schema.json
{
  "required_sections": ["INPUTS", "OUTPUT", "SENSITIVITY"],
  "required_fields": {
    "title": "string",
    "confidence": "low|medium|high",
    "time_horizon_months": "integer",
    "key_drivers": "string[]"
  }
}
```

And a validation script that checks the output:
```bash
uv run python validate_research.py macro_research/2025-03-10/run_001/
```

This replaces Zod validation with post-hoc file validation, which fits
the CLI-based workflow better.

---

## 11. Multi-Provider Data Fetching {#11-multi-provider-data}

quant-ai-advisor implements a priority-based multi-provider system:

```typescript
interface DataProvider {
  name: string;
  priority: number;
  isConfigured(): boolean;
  getQuote?(symbol): Promise<QuoteData>;
  getHistorical?(symbol, start, end): Promise<HistoricalBar[]>;
  getFundamentals?(symbol): Promise<FundamentalsData>;
  getOptionsChain?(symbol, expiration?): Promise<OptionsChainData>;
}
```

Providers:
1. FMP (Financial Modeling Prep) — Priority 1: quotes, fundamentals
2. Alpha Vantage — Priority 2: quotes, historical, **options** (exclusive)

Fallback logic: try Provider 1, if it fails, try Provider 2, with
exponential backoff (3 retries, 1s initial delay).

### How to apply this

ikbr_trader already has IBKR as a data source via `ibkr.py`. For macro
research, we need additional sources:

1. **IBKR** (via ib-insync): live prices, options chains, account data
2. **Yahoo Finance** (via yfinance, already a dependency): broad market
   data, fundamentals, historical
3. **FRED** (Federal Reserve Economic Data): macro indicators (rates,
   GDP, employment, inflation)

The macro research system should pre-fetch relevant data before prompting:

```python
# data_fetcher.py
def fetch_macro_snapshot():
    """Fetch current macro data from multiple sources."""
    snapshot = {}

    # From yfinance
    snapshot["spy_price"] = yf.Ticker("SPY").info["regularMarketPrice"]
    snapshot["vix"] = yf.Ticker("^VIX").info["regularMarketPrice"]
    snapshot["tlt_price"] = yf.Ticker("TLT").info["regularMarketPrice"]

    # From FRED (if available)
    # snapshot["fed_funds"] = fred.get_series("FEDFUNDS").iloc[-1]
    # snapshot["ten_year"] = fred.get_series("DGS10").iloc[-1]

    # From IBKR (if connected)
    # snapshot["portfolio"] = get_portfolio_snapshot()

    return snapshot
```

This snapshot gets injected into the prompt as concrete data the model
can reason over, eliminating the hallucination problem.

---

## 12. QuantState: The Single Source of Truth {#12-quantstate}

The QuantState type is the backbone:

```typescript
interface QuantState {
  thesis: Thesis | null;
  currentMacroFacts: MacroFact[];
  currentPortfolio: Portfolio | null;
  proposedBuys: ProposedTrade[];
  stockInformation: Record<string, StockResearch>;
  optionsChains: Record<string, OptionsChain>;
  forecasts: {
    oneMonth: Forecast | null;
    threeMonth: Forecast | null;
    sixMonth: Forecast | null;
  };
}
```

State flows: DB → memory → tool mutations → DB → SSE → client.

### The "state as directory" pattern

For the CLI-based system, the directory IS the state:

```
run_001/
  thesis.md              ← thesis field
  macro_facts.json       ← currentMacroFacts
  portfolio_context.json ← currentPortfolio
  forecast_3m.json       ← forecasts.threeMonth
  forecast_6m.json       ← forecasts.sixMonth
  proposed_trades.json   ← proposedBuys
  data/
    spy.json             ← stockInformation["SPY"]
    ewy.json             ← stockInformation["EWY"]
```

To "read state," Claude reads the directory. To "write state," it writes
files. The directory listing IS the state inspection.

This is simpler than a database, fits CLI workflows, and is git-friendly
(you can commit research runs).

---

## 13. SSE Streaming: Real-Time Tool Visibility {#13-sse-streaming}

The SSE event stream gives the client visibility into what's happening:

```
event: tool_use     → "Model is fetching IONQ data"
event: tool_complete → "Data fetched successfully"
event: content      → "Streaming analysis text"
event: state_update → "State changed, re-render UI"
event: done         → "Analysis complete"
```

### How to apply this

For CLI-based research, the equivalent is stdout. If using `claude -p`,
the output streams to the terminal. The user sees the model's reasoning
in real-time.

For a future dashboard, we could capture this stream:
```bash
claude -p "$(cat prompt.md)" 2>&1 | tee run_001/stream.log
```

The stream log becomes a replayable record of the analysis process.

---

## 14. The StatePanel UI: Structured Analysis Display {#14-statepanel-ui}

The StatePanel renders QuantState in organized sections:

1. **Proposed Trades** (top priority, green border)
   - Direction arrow + ticker + strategy badge
   - Options legs formatted as "+1 21 $85C"
   - Metrics grid: Price, Entry, R:R, Max Loss, Timeframe
   - Collapsible full rationale

2. **Investment Thesis**
   - Title + confidence badge + time horizon
   - Key drivers as tags
   - Full markdown body

3. **Probabilistic Forecasts**
   - Per-horizon cards (1m, 3m, 6m)
   - Interval bars with colored probability indicators
   - Red ↓ for negative, green ↑ for positive, gray for mixed
   - Description text per interval

4. **Macro Facts**
   - Label + detail + source
   - Tags for categorization

5. **Stock Research**
   - Per-ticker cards with metrics
   - Sections: Valuation, Risk, Positioning, Financial Health
   - Collapsed notes with timestamps

### How to apply this

For a future CLI dashboard, the `summary.md` file should mirror this
layout. But more importantly, the individual JSON files should be
structured so that a dashboard can read them:

```python
# read_research.py — load a research run for display
def load_run(run_dir: Path) -> dict:
    result = {}
    if (run_dir / "thesis.md").exists():
        result["thesis"] = (run_dir / "thesis.md").read_text()
    if (run_dir / "forecast_3m.json").exists():
        result["forecast_3m"] = json.loads(...)
    # etc.
    return result
```

The dashboard doesn't need to be React — it could be a terminal UI
(rich/textual), a static HTML page, or just Claude reading the files.

---

## 15. Incremental Progress: Checkpoints and Continue {#15-incremental-progress}

The researcher prompt includes checkpoints:

```
| Done | State | Next |
|------|-------|------|
| Data fetched | stockInformation populated | Build thesis |
| Thesis built | thesis set | Set forecasts |
| Forecasts set | forecasts.* populated | Propose trade |

If approaching tool limits: persist what you've done, exit.
Presenter tells user to "continue."
```

This is powerful because it means:
- The model can do partial work and save it
- The user can resume where the model left off
- Each step is independently valuable

### How to apply this

For CLI-based research, checkpoints are files:
```
# After step 1: data fetched
ls run_001/  →  data/spy.json data/ewy.json

# After step 2: thesis written
ls run_001/  →  data/ thesis.md

# After step 3: forecasts added
ls run_001/  →  data/ thesis.md forecast_3m.json

# After step 4: trades proposed
ls run_001/  →  data/ thesis.md forecast_3m.json proposed_trades.json
```

If the model crashes after step 2, we have data + thesis. We can
resume with a prompt like:
```bash
claude -p "Continue the research in run_001/. Thesis exists.
Next: generate forecasts."
```

This is much better than the attempt 1 approach where everything or
nothing is produced.

---

## 16. Falsifiability: Kill Conditions as First-Class Data {#16-falsifiability}

From the philosophy prompt:

```
Every model must have explicit kill conditions:
- "If Q2 bookings come in below X, the growth axiom is broken"
- "If gross margin doesn't improve to Y% by [date], scale economics thesis fails"

A model without falsification criteria is not a model — it's a hope.
```

### Why this matters enormously for macro research

Macro theses are notoriously unfalsifiable. "The economy will slow" — when?
By how much? What would prove you wrong? Without kill conditions, a macro
thesis is just a mood.

The thesis.md file should include an explicit section:

```markdown
## Kill Conditions

This thesis is INVALIDATED if any of the following occur:

1. Core PCE drops below 2.3% for two consecutive months
   → Disinflation faster than expected, Fed will cut, thesis breaks
2. ISM Manufacturing rises above 52 for three months
   → Manufacturing recovery contradicts slowdown thesis
3. 10Y yield drops below 3.8% without Fed action
   → Market already pricing the thesis, no edge left
4. S&P 500 earnings growth accelerates to >10% y/y
   → Earnings overcoming rate drag, multiple compression thesis breaks

## Review Date: 2025-06-10
If none of these triggers have fired by this date, reassess all assumptions.
```

This should be a required section in every thesis. The model should be
prompted to generate it, and the review workflow should check whether
any kill conditions have fired.

---

## 17. ProposedTrade: Structured Trade Recommendations {#17-proposed-trades}

The quant-ai-advisor's ProposedTrade type:

```typescript
interface ProposedTrade {
  ticker: string;
  assetType: 'stock' | 'option' | 'etf';
  direction: 'long' | 'short';
  optionsStrategy?: string;
  legs?: OptionLeg[];
  entryPoints: EntryPoint[];
  marketContext: MarketContext;      // underlying price, IV at time of rec
  stopLoss?: string;
  profitTarget?: string;
  maxLoss?: string;
  riskReward?: string;
  positionSize?: string;
  timeframe?: string;
  thesis_summary: string;
  description: string;
}
```

Notable: `marketContext` captures the market state at the time of the
recommendation. This allows later review to see how the trade was priced
when proposed vs current.

### How to apply this

The proposed_trades.json should include market context AND integrate
with ikbr_trader's existing trade format:

```json
{
  "proposed_at": "2025-03-10T14:30:00Z",
  "thesis_ref": "thesis.md",
  "trades": [
    {
      "ticker": "TLT",
      "direction": "long",
      "asset_type": "etf",
      "rationale": "Duration play on rate cuts. If core PCE drops to 2.3%...",
      "market_context": {
        "price": 88.50,
        "spy_price": 5100,
        "vix": 18.5,
        "ten_year": 4.55
      },
      "entry": {"type": "limit", "price": 87.00},
      "stop_loss": "TLT < 82 (10Y > 5.0%)",
      "profit_target": "TLT > 98 (10Y < 3.8%)",
      "risk_reward": "1:2",
      "timeframe": "3-6 months",
      "ibkr_compatible": {
        "action": "BUY",
        "contract": {
          "symbol": "TLT",
          "secType": "STK",
          "exchange": "SMART",
          "currency": "USD"
        },
        "orderType": "LMT",
        "lmtPrice": 87.00
      }
    }
  ]
}
```

The `ibkr_compatible` section bridges to the executor. This is the
integration attempt 1 was missing entirely.

---

## 18. MacroFacts: Provenance-Tagged Data Points {#18-macro-facts}

```typescript
interface MacroFact {
  id: string;
  timestamp_iso: string;
  label: string;
  detail: string;
  source?: string;
  tags?: string[];
}
```

Example:
```json
{
  "label": "Fed Funds Rate",
  "detail": "5.25-5.50% target range, unchanged since July 2023",
  "source": "FOMC Statement, Jan 2025",
  "tags": ["rates", "monetary-policy", "fed"]
}
```

### Why provenance matters

When the model says "rates are at 5.25-5.50%," is that from its training
data (potentially stale) or from a real-time source? The `source` field
forces attribution. If the source is "FOMC Statement, Jan 2025" we know
it's from a specific, verifiable document. If the source is "training data"
or empty, we know to be suspicious.

### How to apply this

The macro_facts.json file should be populated BEFORE the thesis is written.
Data first, analysis second. The data fetcher produces macro_facts.json,
then the model reads it and produces thesis.md:

```bash
# Step 1: fetch current data
uv run python fetch_macro_data.py > macro_research/run_001/macro_facts.json

# Step 2: generate thesis using the data
claude -p "Read macro_facts.json, then write thesis.md" \
  --allowedTools Read,Write
```

This ensures the model works with real data, not hallucinated data.

---

## 19. Stock Metrics Bundle: Comprehensive Instrument Profile {#19-stock-metrics}

The StockMetrics type is 70+ fields organized into sections:

```
Price:       price, bid, ask
Trailing:    1m/3m/6m/12m returns, excess returns, realized vol, drawdown
Valuation:   P/E, fwd P/E, P/B, P/S, EV/EBITDA, div yield, market cap
Quality:     revenue, growth, margins (gross/op/net), ROE, ROA, D/E
Risk:        beta, vol 30D/90D, correlation to benchmark
Forward:     analyst targets, ratings, next earnings, fwd EPS
Positioning: short interest, short ratio, institutional/insider ownership
Health:      cash, FCF, operating CF, current ratio, quick ratio
```

### How to apply this

ikbr_trader already has `get_portfolio.py` that fetches position data from
IBKR, and `yfinance` as a dependency. The metrics bundle pattern is useful
for pre-fetching instrument data before research:

```python
def fetch_instrument_bundle(symbol: str) -> dict:
    """Fetch comprehensive metrics for one instrument."""
    info = yf.Ticker(symbol).info
    return {
        "symbol": symbol,
        "price": info.get("regularMarketPrice"),
        "valuation": {
            "pe": info.get("trailingPE"),
            "fwd_pe": info.get("forwardPE"),
            "ps": info.get("priceToSalesTrailing12Months"),
            "market_cap": info.get("marketCap"),
        },
        "quality": {
            "revenue": info.get("totalRevenue"),
            "revenue_growth": info.get("revenueGrowth"),
            "op_margin": info.get("operatingMargins"),
            "net_margin": info.get("profitMargins"),
        },
        # etc.
    }
```

This feeds into the data/ subdirectory of each research run.

---

## 20. Options Chain Integration {#20-options-chain}

quant-ai-advisor fetches and caches options chains:

```typescript
interface OptionsChain {
  symbol: string;
  underlyingPrice: number;
  fetchedAt: string;
  expirationDates: string[];
  expirations: OptionsExpiration[];
}
```

The UI shows calls/puts side by side with ATM highlighting.

### How to apply this

ikbr_trader already has `ibkr.py:get_option_quotes()` and the
`stratoforge/pricing/` module. For macro research, options data is relevant
for:
- Implied volatility as a sentiment indicator
- Put/call ratios as positioning data
- VIX term structure for crisis detection
- Skew as a tail risk indicator

The research system should be able to fetch IV surfaces for key
instruments (SPY, QQQ, TLT, EWY) and include them in the data
context.

---

## 21. Cache Layer: TTL + Deduplication {#21-cache-layer}

```
Cache TTL:
  Quotes: 3 hours
  Options: 3 hours
  Historical: 6 hours

Features:
  - In-flight deduplication (if same key requested while fetching, wait)
  - Auto-upsert on expiration
  - Keyed by (symbol, cache_type)
```

### How to apply this

For the CLI-based system, caching can be file-based:
```
.cache/
  macro_data/
    spy_2025-03-10.json    # expires after 3 hours
    vix_2025-03-10.json
    ewy_2025-03-10.json
```

The data fetcher checks cache freshness before fetching:
```python
cache_file = Path(f".cache/macro_data/{symbol}_{date}.json")
if cache_file.exists():
    age = time.time() - cache_file.stat().st_mtime
    if age < 3 * 3600:  # 3 hours
        return json.loads(cache_file.read_text())
# fetch fresh
```

---

## 22. Conversation Persistence: Resumable Analysis {#22-conversation-persistence}

quant-ai-advisor stores conversations in Supabase with full state:

```sql
conversations:
  id, state (JSONB), portfolio_id, created_at, updated_at

messages:
  id, conversation_id, role, content, payload (JSONB)
```

The state is loaded at the start of each turn and saved after each
state-mutating tool call. This means:
- The user can close the browser and come back
- The analysis resumes from exactly where it left off
- Multiple conversations can exist with different analyses

### How to apply this

For CLI-based research, the directory IS the conversation. Resuming
means pointing at the same directory:

```bash
# First run: starts fresh
claude -p "Generate macro thesis" --output run_001/

# Resume: reads existing files, continues
claude -p "Continue analysis in run_001/. Add forecasts." --allowedTools Read,Write
```

The "conversation history" is the set of files in the directory. Claude
reads them to understand what's been done, then adds to them.

This is actually BETTER than a database for this use case because:
- Files are human-readable
- Files are git-trackable
- Files can be edited manually
- No database dependency

---

## 23. Source Hierarchy: Facts vs Opinions {#23-source-hierarchy}

```
Facts (extract and use):
- Earnings numbers, revenue, margins, guidance
- Product launches, regulatory decisions
- Macro data: rates, inflation, employment

Opinions (ignore entirely):
- Analyst price targets and ratings
- "Why the stock moved today"
- Bullish/bearish interpretations
```

### Extended for macro research

```
FACTS (use these):
- FOMC statements, dot plots, meeting minutes
- BLS data: NFP, CPI, PPI, unemployment rate
- BEA data: GDP, PCE, personal income
- Treasury data: yield curve, TIC flows
- ISM surveys (the index numbers, not the commentary)
- Corporate earnings (aggregate, not individual)
- Trade data: imports, exports, trade balance

OPINIONS (ignore these):
- Fed commentary by non-voting members
- "Wall Street strategist" year-end targets
- Bank research notes predicting rate paths
- Financial media narratives ("recession fears")
- Survey-based "expectations" (consumer sentiment)

PROCESS:
1. State the fact with source and date
2. Build an axiom from the fact
3. Chain axioms into a model
4. Never cite an opinion as evidence
```

---

## 24. Time Horizon Awareness {#24-time-horizon}

```
Days: noise, ignore
Weeks/Months: sentiment and flows, acknowledge but don't trade on
Quarters/Years: fundamentals compound, this is where edge lives
```

### For macro research

This maps to:
- **Noise (days-weeks)**: daily market moves, tweet storms, intraday
  volatility, flash crashes
- **Cycles (months-quarters)**: earnings seasons, FOMC meetings, data
  release calendars, options expiration clusters
- **Structural (years)**: demographic shifts, productivity trends, debt
  cycles, regulatory regimes, technology adoption curves

The thesis should explicitly declare its time horizon:
- "This is a 3-month tactical view based on the FOMC meeting cycle"
- "This is a 12-month structural view based on labor market dynamics"

And the trades should match the horizon. A 3-month thesis shouldn't
propose 2-year LEAPs. A 12-month structural view shouldn't propose
weekly options.

---

## 25. The Two-Phase Harness vs Single-Pass Trade-offs {#25-harness-tradeoffs}

### Two-Phase (Researcher → Presenter)

**Implementation**:
```
Phase 1 (max 5 iterations):
  - System: RESEARCHER_PROMPT
  - Tools enabled
  - No streaming to user
  - Loop until no tool calls

Phase 2 (single call):
  - System: PRESENTER_PROMPT
  - No tools
  - History includes all Phase 1 work
  - Stream response to user
```

**Best for**:
- Complex multi-step analysis
- When you want clean separation of reasoning from communication
- When output quality matters more than latency
- When the model tends to "talk before thinking"

### Single-Pass (Unified)

**Implementation**:
```
Loop (max 10 iterations):
  - System: UNIFIED_PROMPT
  - Tools enabled + streaming enabled
  - Model talks AND uses tools
  - Loop until no tool calls
```

**Best for**:
- Simple queries ("what's AAPL at?")
- Interactive exploration
- When the user wants to see work in progress
- Lower latency requirements

### For CLI-based macro research

The natural choice is **single-pass with file writes**. The model
reasons out loud (the output is the CoT) and writes files as it goes.
The user sees the reasoning in real-time via stdout.

But for batch generation (generating 5 theses overnight), two-phase
is better: the "researcher" writes files silently, then a separate
"reviewer" reads them and writes a summary.

```bash
# Single-pass (interactive)
claude -p "Generate a macro thesis about rates. Write files to run_001/."

# Two-phase (batch)
claude -p "$(cat researcher_prompt.md)" --output run_001/ --quiet
claude -p "Review the research in run_001/ and write summary.md" --output run_001/
```

---

## 26. Applicability Map: What to Take, What to Leave {#26-applicability-map}

### TAKE (high value, directly applicable)

| Idea | Why | Effort |
|------|-----|--------|
| INPUTS/OUTPUT/SENSITIVITY thesis structure | Forces quantitative rigor | Low (prompt change) |
| Forecast intervals mapped to inputs | Eliminates vibes-based probabilities | Low (prompt change) |
| Banned language list | Prevents analysis-flavored noise | Low (prompt change) |
| Kill conditions / falsifiability | Makes theses reviewable | Low (prompt change) |
| Source hierarchy (facts vs opinions) | Prevents narrative reproduction | Low (prompt change) |
| State-as-directory pattern | Files = state, simple and git-friendly | Medium (architecture) |
| Incremental file writes | Partial results survive failures | Medium (architecture) |
| Pre-fetched data context | Eliminates hallucinated macro data | Medium (new script) |
| Leading vs lagging indicator awareness | Improves thesis quality | Low (prompt change) |
| Dependency chain (data → thesis → forecast → trades) | Enforces analytical rigor | Low (prompt change) |

### ADAPT (good idea, needs modification)

| Idea | Original | Adapted |
|------|----------|---------|
| Tool registry | Zod-validated TypeScript handlers | File schema validation post-hoc |
| QuantState | In-memory JSONB state | Directory of files |
| Two-phase harness | Researcher + Presenter model calls | Generate + Review CLI invocations |
| SSE streaming | WebSocket events to React UI | stdout streaming + log capture |
| ProposedTrade type | TypeScript interface | JSON file with ibkr_compatible section |
| Multi-provider fallback | FMP → Alpha Vantage → backup | IBKR → yfinance → FRED |
| Cache layer | Supabase table with TTL | File-based cache with mtime check |
| Conversation persistence | Supabase conversations table | Directory-per-run, resume by path |

### LEAVE (not applicable or wrong fit)

| Idea | Why Leave It |
|------|-------------|
| React UI / shadcn components | We're building CLI tools, not a web app (for now) |
| Supabase backend | No need for a database; files are simpler |
| OpenRouter multi-model | We use claude/codex CLI, model selection is a flag |
| SSE event protocol | No web client to stream to |
| Portfolio table with CRUD | ikbr_trader gets portfolio from IBKR directly |
| Presenter phase constraint ("you can't think") | In CLI mode, all reasoning is visible |
| anthropic SDK | Use CLI tools instead |

### FUTURE (good for later, not now)

| Idea | When |
|------|------|
| StatePanel-style dashboard | When we build a TUI or web UI |
| Real-time tool badges | When we have a streaming UI |
| Conversation history sidebar | When we have multiple research sessions to compare |
| Options chain viewer | When we integrate options data into macro research |
| Portfolio selector | When we support multiple portfolio views |

---

## Appendix A: Prompt File Inventory

For reference, the exact prompt files from quant-ai-advisor and their
line counts:

```
prompts/shared-base.ts    184 lines   Philosophy + epistemology + banned language
prompts/researcher.ts     142 lines   Execution sequence + tool rules + output rules
prompts/presenter.ts      ~150 lines  Translation rules + decision tree
prompts/unified.ts         83 lines   Single-pass mode instructions
prompts/tool-guide.ts      92 lines   Tool documentation
```

Total prompt content: ~650 lines of carefully tuned instructions.

For ikbr_trader, the equivalent should be:
```
prompts/philosophy.md      ~100 lines  Adapted from shared-base
prompts/researcher.md      ~80 lines   File-write execution sequence
prompts/reviewer.md        ~50 lines   Read-and-explain instructions
prompts/banned_words.md    ~30 lines   Extended banned language list
```

Total: ~260 lines. Shorter because we don't need tool documentation
(Claude Code has its own tools) and we're using markdown instead of
TypeScript template strings.

---

## Appendix B: Type Comparison

### quant-ai-advisor types (TypeScript)

```
QuantState           — root state container
  Thesis             — title, body, confidence, key_drivers
  Forecast           — intervals[], logit_commentary
  ForecastInterval   — [min, max], probability, description
  ProposedTrade      — ticker, direction, legs, entry, stop, target
  OptionLeg          — type, strike, expiration, action, contracts
  EntryPoint         — type (market/limit/stop-limit), price, tranche
  MarketContext      — underlying price, bid, ask, IV
  MacroFact          — label, detail, source, tags
  Portfolio          — positions (ticker → count)
  StockMetrics       — 70+ fields in 7 sections
  StockResearch      — metrics + notes[]
  OptionsChain       — symbol, price, expirations[]
  ToolCallInfo       — id, tool, args, status
  Message            — role, content, toolCalls
```

### ikbr_trader equivalents (file-based)

```
run_directory/           — equivalent of QuantState
  thesis.md              — Thesis (markdown, structured)
  forecast_3m.json       — Forecast (JSON)
  forecast_6m.json       — Forecast (JSON)
  proposed_trades.json   — ProposedTrade[] (JSON, with ibkr_compatible)
  macro_facts.json       — MacroFact[] (JSON)
  portfolio_context.json — Portfolio snapshot from IBKR
  data/
    spy.json             — StockMetrics-equivalent
    ewy.json             — StockMetrics-equivalent
    macro_indicators.json — rates, VIX, yield curve
  stream.log             — equivalent of Message history
```

No TypeScript interfaces needed. No Python dataclasses needed. The schema
is implicit in the file format conventions, documented in the prompt files.

---

## Appendix C: The Most Important Sentences

Lines from quant-ai-advisor prompts that should be preserved verbatim
or near-verbatim in the ikbr_trader system:

1. "Build From Numbers, Not Narratives"
2. "If you don't call set_thesis, there is no thesis"
   → adapted: "If you don't write thesis.md, there is no thesis"
3. "Without this structure [INPUTS/OUTPUT/SENSITIVITY], you have not done analysis"
4. "A model without falsification criteria is not a model — it's a hope"
5. "Probability comes from model input uncertainty, not bull/bear scenarios"
6. "Each interval maps to MODEL INPUTS, not scenarios"
7. "Think of yourself as a news anchor reading a teleprompter"
   → for the review phase
8. "Leading: pipeline, bookings, CAC trends. You seek metrics that PREDICT"
9. "Facts: extract and use. Opinions: ignore entirely."
10. "INSTEAD be specific: P/S 225x vs sector median 8x"

---

## Appendix D: Error Patterns to Avoid

Things quant-ai-advisor does that we should NOT replicate:

1. **2715-line index.ts monolith** — the entire backend is one file.
   Bad for maintenance, bad for testing, bad for comprehension.

2. **Provider interface with 7 optional methods** — `getQuote?`,
   `getHistorical?`, `getFundamentals?`, `getOptionsChain?` — this
   is accidental optionality. Each provider should declare its
   capabilities as a type, not as optional methods.

3. **Hardcoded model list in the UI** — DeepSeek V3.2, Gemini 3 Pro,
   Kimi K2, GPT-5.2 are hardcoded in a dropdown. Should be config.

4. **Cache in a database table** — Supabase is not a cache. File-based
   caching with mtime is simpler and faster.

5. **Presenter can't flag issues** — if the Researcher made a bad
   thesis, the Presenter can only read it, not critique it. The
   "translator" metaphor is too strict. A review phase should be
   allowed to push back.

6. **No versioning** — QuantState is overwritten on each mutation.
   There's no history of state changes within a conversation. If the
   model overwrites a good thesis with a bad one, the good one is gone.
   File-based state naturally versions via git.

7. **Yahoo cache table still exists** — legacy table from a previous
   architecture, still in the schema but unused. Technical debt.

8. **SSE event parsing in Index.tsx** — 100+ lines of regex-based SSE
   parsing in a React component. Should be a hook or utility.

---

## Appendix E: Architecture Decision Records

Key decisions the quant-ai-advisor made and whether they apply:

### ADR-1: Two-phase vs single-pass

**Decision**: Support both, let user choose via dropdown.
**Reasoning**: Two-phase is better for complex analysis, single-pass for exploration.
**For ikbr_trader**: Support both. Default to single-pass for interactive use,
two-phase for batch generation.

### ADR-2: State in database vs in-memory

**Decision**: Database (Supabase JSONB).
**Reasoning**: Persistence across sessions, multi-device access.
**For ikbr_trader**: Files on disk. Persistence via filesystem, multi-session
via directory paths. Simpler, no database dependency.

### ADR-3: Multi-provider data

**Decision**: Abstract provider interface with priority fallback.
**Reasoning**: No single data source is reliable enough.
**For ikbr_trader**: Yes, but simpler — yfinance for most things, IBKR for
live positions and options, FRED for macro indicators. No need for a formal
provider registry; a few functions is fine.

### ADR-4: Tool-driven persistence

**Decision**: All analysis must go through tool calls; prose is discarded.
**Reasoning**: Prevents confabulation, ensures structured output.
**For ikbr_trader**: File-driven persistence. All analysis must be written
to files; stdout is for reasoning/CoT only. Same principle, different mechanism.

### ADR-5: Banned language

**Decision**: Hardcode a list of banned words in the prompt.
**Reasoning**: LLMs default to "analysis-flavored" language that conveys
no information. The ban forces specificity.
**For ikbr_trader**: Yes, adopt and extend. Add macro-specific banned terms.

### ADR-6: Forecast intervals (not scenarios)

**Decision**: 3-5 intervals with probability + input-driven description.
**Reasoning**: "Bull/bear/base" is arbitrary. Intervals mapped to inputs
are falsifiable and quantitative.
**For ikbr_trader**: Yes, adopt directly. This is the single best idea in
the whole system.

---

## Appendix F: The Validation Pattern (Zod in TypeScript, what to use in Python)

quant-ai-advisor validates every tool call argument with Zod schemas before
execution. This is critical because LLMs produce malformed tool calls
surprisingly often — wrong types, missing fields, extra fields, out-of-range
values.

### How it works in quant-ai-advisor

Each tool in the registry has a Zod schema:

```typescript
// Simplified from index.ts
const ThesisArgsSchema = z.object({
  title: z.string(),
  body: z.string(),
  time_horizon_months: z.number().int().min(1).max(120),
  confidence: z.enum(["low", "medium", "high"]),
  key_drivers: z.array(z.string()),
});

const ForecastArgsSchema = z.object({
  intervals: z.array(z.object({
    interval: z.tuple([z.number(), z.number()]),
    probability: z.number().min(0).max(1),
    description: z.string(),
  })),
  as_of: z.string().optional(),
  logit_commentary: z.string().optional(),
  notes: z.string().optional(),
});
```

The dispatch loop:
```typescript
for (const toolCall of toolCalls) {
  const tool = toolRegistry[toolCall.function.name];
  if (!tool) {
    // Return error to model: "Unknown tool"
    continue;
  }
  const parsed = tool.schema.safeParse(JSON.parse(toolCall.function.arguments));
  if (!parsed.success) {
    // Return validation error to model with details
    // Model can retry with corrected args
    continue;
  }
  const result = await tool.handler(state, parsed.data, context);
  // ...
}
```

Key points:
- `.safeParse()` doesn't throw — it returns `{ success, data, error }`
- Validation errors are sent BACK to the model as tool results
- The model can retry with corrected arguments
- This is self-healing: the model learns from its format mistakes

### The `add_proposed_buy` prerequisite check

This is particularly clever:

```typescript
set_thesis: {
  handler: async (state, args) => {
    state = setThesis(state, args);
    return { state, result: { status: 'success', message: 'Thesis updated' } };
  },
},

add_proposed_buy: {
  handler: async (state, args) => {
    // PREREQUISITE CHECK: thesis and forecasts must exist
    if (!state.thesis) {
      return {
        state,
        result: {
          status: 'error',
          message: 'Cannot add trade without thesis. Call set_thesis first.'
        }
      };
    }
    const hasAnyForecast = state.forecasts.oneMonth ||
                           state.forecasts.threeMonth ||
                           state.forecasts.sixMonth;
    if (!hasAnyForecast) {
      return {
        state,
        result: {
          status: 'error',
          message: 'Cannot add trade without forecasts. Call set_forecast_* first.'
        }
      };
    }
    // OK, proceed
    state = addProposedBuy(state, args);
    return { state, result: { status: 'success' } };
  },
},
```

The dependency chain is enforced at the tool level, not just in the prompt.
Even if the model ignores the prompt instruction to "set thesis before
proposing trades," the tool will reject the call and tell the model why.

### How to apply this in Python / file-based system

For the CLI-based approach, we can't validate tool calls in real-time
(Claude writes files directly). But we CAN validate post-hoc:

```python
# validate_research.py
import json
from pathlib import Path

def validate_run(run_dir: Path) -> list[str]:
    errors = []

    # Check thesis exists
    thesis_path = run_dir / "thesis.md"
    if not thesis_path.exists():
        errors.append("MISSING: thesis.md")
    else:
        content = thesis_path.read_text()
        if "## INPUTS" not in content:
            errors.append("thesis.md missing INPUTS section")
        if "## OUTPUT" not in content:
            errors.append("thesis.md missing OUTPUT section")
        if "## SENSITIVITY" not in content:
            errors.append("thesis.md missing SENSITIVITY section")
        if "## Kill Conditions" not in content:
            errors.append("thesis.md missing Kill Conditions section")

    # Check forecast
    forecast_path = run_dir / "forecast.json"
    if not forecast_path.exists():
        errors.append("MISSING: forecast.json")
    else:
        fc = json.loads(forecast_path.read_text())
        for horizon, data in fc.get("horizons", {}).items():
            intervals = data.get("intervals", [])
            if len(intervals) < 3:
                errors.append(f"forecast {horizon}: fewer than 3 intervals")
            prob_sum = sum(iv["probability"] for iv in intervals)
            if abs(prob_sum - 1.0) > 0.05:
                errors.append(f"forecast {horizon}: probabilities sum to {prob_sum:.2f}, not ~1.0")
            for iv in intervals:
                if not iv.get("description"):
                    errors.append(f"forecast {horizon}: interval {iv['interval']} has no description")

    # Check trades (only valid if thesis + forecast exist)
    trades_path = run_dir / "proposed_trades.json"
    if trades_path.exists():
        if not thesis_path.exists():
            errors.append("proposed_trades.json exists but thesis.md is missing")
        if not forecast_path.exists():
            errors.append("proposed_trades.json exists but forecast.json is missing")

    return errors
```

This validator runs in the post-process phase and flags issues. The
review phase then sees the validation results and can comment on them.

---

## Appendix G: The UI Component Patterns (for future dashboard)

Even though we're building CLI-first, the quant-ai-advisor UI patterns
are worth documenting for when we build a dashboard.

### Pattern 1: Forecast interval visualization

```typescript
// From StatePanel.tsx
const getRangeDisplay = (interval: [number, number]) => {
  const [low, high] = interval;
  const magnitude = (Math.abs(high - low) * 100).toFixed(1);
  const midpoint = (Math.abs((low + high) / 2) * 100).toFixed(1);
  const isNegative = high < 0;
  const isPositive = low > 0;
  return { magnitude, midpoint, isNegative, isPositive };
};
```

Each interval gets:
- A colored arrow (red down, green up, gray mixed)
- The midpoint percentage as the headline number
- The range width as context
- The probability as a badge
- The description as a tooltip/expandable

For a terminal dashboard, this could be:
```
3M Forecast:
  ↓ -15%  [25%]  10Y > 5%, tech reprices to 20x fwd PE
  → +2%   [45%]  Base case: one cut in H2, earnings grow 6%
  ↑ +12%  [20%]  Two cuts + AI capex acceleration
  ↑ +25%  [10%]  Three cuts + earnings breakout
```

### Pattern 2: Trade card with collapsible rationale

The ProposedTradeCard shows:
- Header: direction arrow + ticker + strategy badge
- Quick metrics: entry, stop, target, R:R, timeframe
- Collapsed section: full markdown rationale

For terminal output, this maps to:
```
LONG TLT (ETF) — 3-6mo — R:R 1:2
  Entry: $87.00 limit | Stop: $82 | Target: $98
  Rationale: Duration play on rate cuts. If core PCE drops...
```

### Pattern 3: Tool execution badges

The ToolUseIndicator renders each tool call as:
- Icon (colored by tool type)
- Status (spinner → checkmark → alert)
- Tool name + arg preview
- Tooltip with full JSON args

For CLI, this is the stdout stream:
```
[✓] Reading data_context.json
[✓] Writing thesis.md (1247 words)
[✓] Writing forecast.json (3 horizons, 12 intervals)
[✓] Writing proposed_trades.json (2 trades)
```

### Pattern 4: State-driven section visibility

StatePanel only shows sections that have data:
```typescript
{state.thesis && (
  <Card>
    <CardHeader>Investment Thesis</CardHeader>
    ...
  </Card>
)}
```

For the summary.md, same principle: only include sections that have content.
Don't write "## Proposed Trades\n\nNone." — just omit the section.

---

## Appendix H: The Streaming Architecture (for future use)

quant-ai-advisor uses Server-Sent Events for real-time updates. The
event protocol is:

```
event: content
data: {"text": "Looking at IONQ's metrics..."}

event: tool_use
data: {"id": "tc_123", "tool": "get_instrument_features", "args": {"symbol": "IONQ"}}

event: tool_complete
data: {"id": "tc_123", "tool": "get_instrument_features"}

event: state_update
data: {"state": {...}, "conversationId": "conv_456"}

event: done
data: {"conversationId": "conv_456", "state": {...}}
```

The client handles these with a buffered flush:
```typescript
// 50ms flush interval to avoid excessive re-renders
const flushInterval = setInterval(() => {
  if (buffer.length > 0) {
    setAssistantContent(prev => prev + buffer.join(''));
    buffer = [];
  }
}, 50);
```

### For future ikbr_trader dashboard

If we build a TUI (textual/rich) or web dashboard, we could capture
the `claude -p` stdout stream and parse it:

```python
import subprocess

proc = subprocess.Popen(
    ["claude", "-p", prompt],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, bufsize=1,
)

for line in proc.stdout:
    # Detect file writes: "Created /path/to/thesis.md"
    if "Created " in line or "Wrote " in line:
        emit_event("file_created", parse_path(line))
    else:
        emit_event("content", line)
```

The stream becomes an event source for the dashboard.

---

## Appendix I: State Mutation Functions (implementation reference)

The quant-ai-advisor state mutations are pure functions that return
modified state. This is good functional design:

```typescript
function setThesis(state: QuantState, args: ThesisArgs): QuantState {
  return {
    ...state,
    thesis: {
      title: args.title,
      body: args.body,
      time_horizon_months: args.time_horizon_months,
      confidence: args.confidence,
      key_drivers: args.key_drivers,
    },
  };
}

function addCurrentMacroFact(state: QuantState, args: MacroFactArgs): QuantState {
  const fact: MacroFact = {
    id: crypto.randomUUID(),
    timestamp_iso: args.timestamp_iso || new Date().toISOString(),
    label: args.label,
    detail: args.detail,
    source: args.source,
    tags: args.tags || [],
  };
  return {
    ...state,
    currentMacroFacts: [...state.currentMacroFacts, fact],
  };
}

function addProposedBuy(state: QuantState, args: TradeArgs): QuantState {
  const trade: ProposedTrade = {
    id: crypto.randomUUID(),
    timestamp_iso: new Date().toISOString(),
    ticker: args.ticker,
    assetType: args.asset_type || 'stock',
    direction: args.direction || 'long',
    optionsStrategy: args.options_strategy,
    legs: args.legs || [],
    entryPoints: args.entry_points || [],
    marketContext: args.market_context || { underlyingPrice: 0 },
    stopLoss: args.stop_loss,
    profitTarget: args.profit_target,
    maxLoss: args.max_loss,
    riskReward: args.risk_reward,
    positionSize: args.position_size,
    timeframe: args.timeframe,
    thesis_summary: args.thesis_summary,
    description: args.description,
  };
  return {
    ...state,
    proposedBuys: [...state.proposedBuys, trade],
  };
}
```

### For file-based state

In our system, "state mutation" is "write a file." But the pure-function
pattern is still useful for the post-process phase:

```python
def add_scenario_from_interval(
    scenario_set: MacroScenarioSet,
    interval: dict,
    horizon_days: int,
) -> MacroScenarioSet:
    """Pure function: returns new scenario set with added scenario."""
    lo, hi = interval["interval"]
    new_scenario = MacroScenario(
        label=interval["description"][:40],
        horizon_days=horizon_days,
        spot_move_pct=(lo + hi) / 2,
        vol_shift=0.0,
        probability=interval["probability"],
    )
    return MacroScenarioSet(
        thesis=scenario_set.thesis,
        scenarios=scenario_set.scenarios + (new_scenario,),
        reference_spot=scenario_set.reference_spot,
        risk_free_rate=scenario_set.risk_free_rate,
    )
```

Immutable types + pure functions = easy to test, easy to compose.

---

## Appendix J: The Pre-Fetch Baseline Pattern

quant-ai-advisor pre-fetches baseline data for new conversations:

```typescript
// Phase 0: Pre-fetch baseline if new conversation
if (!conversationId || messages.length === 0) {
  const baselineSymbols = ['SPY', 'QQQ', 'DIA', 'VIX', 'GLD', 'BND'];
  for (const symbol of baselineSymbols) {
    if (!state.stockInformation[symbol]) {
      const { bundle } = await getInstrumentFeaturesCached(
        { symbol, benchmarkSymbol: 'SPY' },
        supabaseClient,
      );
      state = setStockMetrics(state, symbol, bundle);
    }
  }
  await saveState(conversationId, state);
}
```

This ensures the model always has broad market context before the user
asks their first question. The model doesn't need to waste a tool call
fetching SPY data — it's already there.

### For ikbr_trader

This maps directly to `fetch_macro_data.py`. The pre-fetch is Phase 1
of the pipeline. It runs BEFORE Claude is invoked, so the data is real
and current. Claude reads it from data_context.json, never hallucinating.

The baseline symbols for macro research should be:
```python
BASELINE = {
    "equities": ["SPY", "QQQ", "IWM", "EFA", "EEM"],
    "rates": ["TLT", "IEF", "SHY", "HYG", "LQD"],
    "commodities": ["GLD", "USO", "DBA"],
    "volatility": ["^VIX"],
    "fx": ["UUP", "FXE", "FXY"],
}
```

Plus user-specific holdings (from IBKR portfolio) and any focus-area
tickers.

---

## Appendix K: Conversation History as Context

In quant-ai-advisor, the full conversation history (including tool calls
and results) is passed to the model on every turn. This means the model
can reference previous analysis:

"Earlier I set a thesis that IONQ is overvalued at $19B. The user now
asks about AMAT. I should check if AMAT is in the same sector and
whether the thesis applies."

### For file-based research

The equivalent is: Claude reads all files in the run directory before
writing new ones. If we want cross-thesis awareness (rare), we could
pass an index of previous runs:

```bash
# Tell Claude about previous research
echo "## PREVIOUS RESEARCH RUNS" >> /tmp/context.md
for dir in macro_research/2025-03-*/*/; do
  if [ -f "$dir/thesis.md" ]; then
    echo "### $(head -1 $dir/thesis.md)" >> /tmp/context.md
    head -5 "$dir/thesis.md" >> /tmp/context.md
  fi
done
```

But this is a future optimization, not a launch requirement.

---

## Appendix L: What "20K words" should cover that this doesn't yet

Areas this extraction hasn't fully explored:

1. **The FMP data assembly pipeline** — how 4 parallel API calls are
   merged into one StockMetrics bundle (important for our yfinance equivalent)

2. **The options chain UI interaction model** — how expiration selection
   triggers re-fetch and state update (relevant for future dashboard)

3. **The conversation sidebar logic** — how conversations are listed,
   labeled (thesis title or date), and selected (relevant for
   multi-run comparison)

4. **The portfolio entity CRUD** — create/select/delete portfolios,
   link to conversations (relevant if we want named portfolio views)

5. **The search tool implementation** — SERP API integration with
   result formatting (relevant if we use codex with web access)

6. **Error recovery patterns** — what happens when a tool fails mid-loop,
   how the model retries, how partial state is preserved

7. **The model selection dropdown** — how different models are configured
   with different token limits, temperatures, provider keys

These are lower priority for the macro research system but worth
documenting for the full dashboard build later.

---

## Appendix M: The research_session.py Pattern (ikbr_trader's own precedent)

While quant-ai-advisor is the external reference, ikbr_trader ALREADY has
a working multi-turn AI research system in `custom_scripts/research_session.py`.
This is arguably more relevant than quant-ai-advisor because it runs in
the same repo, uses the same tools, and follows the same conventions.

### Architecture

```python
def do_research(topic, *, ticker, research_prompt, x_username, ...):
    # 1. Create directory layout
    paths = _ensure_session_layout(topic, ticker)

    # 2. Optional: fetch latest tweet
    latest_tweet = get_users_latest_tweet(x_username, ...)

    # 3. Run 3 Codex turns, each building on previous
    prompts = [
        "Collect raw sources into loose_notes/",
        "Synthesize analysis into analysis/",
        "Write conclusions/ and final_report.md",
    ]
    for prompt in prompts:
        turn = _run_codex_turn(prompt=prompt, resume_thread_id=thread_id)
        thread_id = turn.thread_id
        _write_manifest(paths, turns=turns)  # save progress after each turn
```

### Key patterns to reuse

**1. `_run_codex_turn()` — the execution primitive**

```python
def _run_codex_turn(*, prompt, repo_root, resume_thread_id, full_auto):
    command = ["codex", "exec"]
    if resume_thread_id:
        command.extend(["resume", resume_thread_id])
    else:
        command.extend(["-C", str(repo_root)])
    if full_auto:
        command.append("--full-auto")
    command.extend(["--json", "-o", str(output_path)])
    command.append(prompt)

    process = subprocess.Popen(command, stdout=PIPE, stderr=PIPE, text=True)
    for raw_line in process.stdout:
        event = json.loads(raw_line)  # JSON-lines streaming
        if event.get("type") == "thread.started":
            thread_id = event["thread_id"]
    return CodexTurnResult(thread_id, prompt, last_message, stderr, exit_code, events)
```

This is the reusable execution primitive. It:
- Streams JSON events from codex stdout
- Captures the thread_id for resuming
- Saves the last message for structured output
- Handles errors with full context

**2. Manifest pattern — progress persistence**

After EACH turn, the manifest is rewritten:
```python
_write_manifest(paths, thread_id=thread_id, turns=turns, latest_tweet=latest_tweet)
```

This means if turn 2 of 3 fails, the manifest records:
- Turn 1: completed (thread_id, prompt, last_message)
- Turn 2: failed (no entry)
- Turn 3: not started

The user can resume from where it stopped.

**3. Structured output schema via `--output-schema`**

For the tweet fetcher, research_session.py uses Codex's structured output:
```python
schema = {
    "type": "object",
    "required": ["found", "username", "source_url", "posted_at", "text", "summary", "caveats"],
    "properties": {
        "found": {"type": "boolean"},
        "text": {"type": ["string", "null"]},
        ...
    },
}
turn = _run_codex_turn(prompt=prompt, output_schema=schema)
data = json.loads(turn.last_message)
```

This gives us validated JSON output without the "parse JSON from markdown"
hack that attempt 1 used. The `--output-schema` flag tells Codex to
validate the output against a JSON schema.

**4. Multi-turn with thread resumption**

The 3-turn structure uses `resume_thread_id` to continue the same Codex
conversation:
```python
for index, prompt in enumerate(prompts):
    turn = _run_codex_turn(
        prompt=prompt,
        resume_thread_id=thread_id if index > 0 else None,
    )
    thread_id = turn.thread_id
```

Turn 2 sees everything from turn 1 (files created, analysis done).
Turn 3 sees everything from turns 1 and 2. This is the Codex equivalent
of quant-ai-advisor's stateful conversation.

### What macro_thesis.py should borrow

| Pattern | How to use it |
|---------|--------------|
| `_run_codex_turn()` | Reuse directly (import from research_session) |
| Manifest with per-turn progress | Write manifest after each phase |
| `--output-schema` for structured data | Use for forecast.json, proposed_trades.json |
| Thread resumption | Resume for review phase (same context as generation) |
| `_ensure_session_layout()` | Adapt for macro research directory structure |
| `_write_request_brief()` | Write a brief documenting what was requested |

### What macro_thesis.py should do differently

| Aspect | research_session.py | macro_thesis.py |
|--------|-------------------|-----------------|
| Pre-fetch data | Only tweet | Full macro snapshot |
| Turn structure | 3 hardcoded turns | 2-4 configurable phases |
| Output format | Loose markdown | Structured (thesis.md + forecast.json + trades.json) |
| Post-processing | None | Convert to MacroScenarioSet, run scenario_analyzer |
| Review | None (final_report is the output) | Explicit review phase |
| Integration | Standalone | Bridges to executor, hedge system |

### The `run_structured_json_prompt` helper

research_session.py already has a helper for "get structured JSON from Codex":

```python
def run_structured_json_prompt(prompt, schema, *, repo_root, profile, full_auto):
    turn = _run_codex_turn(prompt=prompt, output_schema=schema, ...)
    return json.loads(turn.last_message), turn.thread_id
```

macro_thesis.py can use this for the forecast and trades phases:
```python
from custom_scripts.research_session import run_structured_json_prompt

forecast_schema = {
    "type": "object",
    "required": ["horizons"],
    "properties": {
        "horizons": {
            "type": "object",
            "properties": {
                "3m": { "type": "object", "properties": { "intervals": { ... } } },
                "6m": { ... }
            }
        }
    }
}

forecast, thread_id = run_structured_json_prompt(
    prompt="Based on the thesis in thesis.md, generate probabilistic forecasts...",
    schema=forecast_schema,
)
```

This gives us validated structured output without new code.

---

## Appendix N: Comparing the Three Systems

| | quant-ai-advisor | research_session.py | macro_thesis.py (proposed) |
|---|---|---|---|
| **Runtime** | Supabase Edge Function | Python + Codex CLI | Python + Claude/Codex CLI |
| **LLM** | OpenRouter (multi-model) | Codex | Claude or Codex |
| **State** | Supabase JSONB | Files on disk | Files on disk |
| **Persistence** | Tool calls (set_thesis) | File writes by Codex | File writes by Claude |
| **Structured output** | Tool call schemas (Zod) | `--output-schema` flag | `--output-schema` flag |
| **Multi-turn** | Agentic loop (max 10) | 3 sequential turns | 2-4 sequential phases |
| **Resumability** | conversation_id | thread_id | thread_id |
| **Data fetching** | In-model tools (FMP, AV) | In-model web search | Pre-fetched (Python) |
| **Post-processing** | None (state IS output) | None | Scenario pricing, executor bridge |
| **Review** | Presenter phase | None | Explicit review phase |
| **UI** | React StatePanel | Terminal output | Terminal + markdown files |

The proposed macro_thesis.py takes the best of both:
- quant-ai-advisor's epistemic discipline and structured output types
- research_session.py's execution model (Codex CLI, thread resumption, manifest)
- New: pre-fetched data, post-processing pipeline, integration with existing modules
