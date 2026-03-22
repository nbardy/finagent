# FinAgent

A typed Python framework for algorithmic options trading with Interactive Brokers. Built to be operated by AI coding agents (Claude Code, Codex, Gemini CLI) — you describe your thesis in plain English, the agent prices it, builds proposals, and submits orders.

## Install

```bash
git clone --recurse-submodules https://github.com/nbardy/finagent.git
cd finagent
uv sync
```

Start [IB Gateway](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php) with API access enabled (default port 4001).

Then open your agent of choice inside the repo:

```bash
claude          # Claude Code
codex           # OpenAI Codex CLI
gemini          # Gemini CLI
```

## What you can ask

The whole point is to talk to the agent in natural language. The codebase gives it typed tools for pricing, portfolio, and execution. Here are real examples:

### Thesis-driven pricing

> "I think the Iran situation will cause a 5% pullback over 2 weeks, with a 20% chance of a 10% crash and maybe a 30% chance it resolves early with a 2% bounce. Price me some put spreads on SPY."

The agent will:
1. Build a `ThesisSchema` with your scenario branches and probabilities
2. Calibrate pricing models against the live SPY option chain
3. Run stratoforge to enumerate and score candidate structures
4. Return ranked strategies with EV, max loss, and Greeks under each scenario

### Portfolio and execution

> "Show me my current portfolio with P&L."

```bash
PYTHONPATH=. uv run python stock_tooling/get_portfolio.py
```

> "I want to sell covered calls against my EWY LEAPs. Find the best strikes for this week."

> "Submit the photonics order file from yesterday."

```bash
uv run python executor.py --file orders/2026-03-10/photonics_stocks.json
```

### Hedging

> "I need crash protection for my book. Compare put spreads vs calendars vs long puts, assuming a 7% drawdown over 5 days."

The agent uses `helpers/urgent_hedge.py` to build, price, and rank hedge candidates, reporting book/hedge/combined P&L.

### Research

> "Research the semiconductor supply chain exposure to Taiwan. Pull recent filings and analyst notes, then write a report."

The agent creates a workspace in `research_sessions/` and writes structured findings.

## Project Structure

```
ibkr.py                  IBKR connection, quotes, portfolio, orders, fills
executor.py              Order proposal submission with price-unit guards
main.py                  PMCC bot — automated short-call management
stratoforge/             Strategy search engine (git submodule)
stratoforge/pricing/     BS, Heston, VG, MJD models + calibration
stock_tooling/           Planners, scenario analysis, watch rules
helpers/                 Shared typed dataclasses for hedges and execution
custom_scripts/          Extensions built on the typed core
config/                  Runtime config (connection, strategy params)
.codex/skills/           Guided workflow definitions
```

## Key Commands

```bash
# Sync portfolio snapshot
uv run python portfolio.py

# Run PMCC bot cycle
uv run python main.py

# Inspect any function signature (agent-friendly)
uv run python one_off_scripts/show_signature.py ibkr get_open_orders
uv run python one_off_scripts/show_signature.py stratoforge.pricing.heston heston_price

# Calibrate pricing models against live chain
uv run python stratoforge/pricing/calibrate.py

# Run tests
uv run pytest
```

## How it works

The codebase follows a **types-as-control-flow** architecture:

- **Canonical domain types** encode the full semantic space (contracts, theses, scenarios, setups)
- **One thin dispatcher** per variant dimension selects a handler
- **One clean handler per type** with zero structural branching
- **No silent fallbacks** — invalid data produces typed errors, never plausible defaults

This makes the codebase agent-friendly: an AI agent can inspect type signatures, understand the domain via types alone, and compose tools without needing to read implementation details.

## Extending

Put new automation in `custom_scripts/`. Import and reuse the typed core modules (`ibkr`, `stratoforge`, `stock_tooling`, `helpers`) rather than duplicating broker or pricing logic.

Personal trading scripts (session-specific, ticker-hardcoded) go in `bespoke/` which is gitignored.

## Safety

This repo can generate and submit live orders to Interactive Brokers. Treat every generated proposal as a draft until you verify it. Margin, routing, and product availability assumptions can be wrong with stale data.

Nothing here is investment advice.

## License

MIT
