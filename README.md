# FinAgent

A typed Python framework for algorithmic options trading with Interactive Brokers.

## Features

- **IBKR Gateway integration** -- portfolio sync, order execution, fill tracking with deduped ledger
- **Multi-model option pricing** -- Black-Scholes, Heston, Variance Gamma, Merton Jump Diffusion
- **Live calibration** -- fit model parameters against observed option chains before pricing
- **Strategy search** -- stratoforge submodule for scanning and scoring strategy universes
- **Scenario analysis** -- hedge evaluation with book/hedge/combined reporting
- **PMCC bot** -- automated Poor Man's Covered Call short-call management
- **Agent-friendly architecture** -- typed core modules with CLI signature inspection
- **Codex skills** -- guided workflows under `.codex/skills/`

## Quick Start

Prerequisites: Python 3.12+, [uv](https://github.com/astral-sh/uv), IB Gateway with API access enabled.

```bash
git clone --recurse-submodules https://github.com/nbardy/finagent.git
cd finagent
uv sync
```

Start IB Gateway (default port 4001), then:

```bash
uv run python portfolio.py          # sync portfolio snapshot
uv run python executor.py --file orders/2026-03-10/example.json  # submit proposals
uv run python main.py               # run PMCC bot cycle
```

## Project Structure

```
ibkr.py                  IBKR connection, quotes, portfolio, orders, fills
executor.py              Order proposal submission with price-unit guards
stratoforge/pricing/          BS, Heston, VG, MJD models + calibration
stock_tooling/           Planners, scenario analysis, watch rules
helpers/                 Shared dataclasses for hedges, scenarios, execution
stratoforge/             Strategy forge library (git submodule)
custom_scripts/          Repo-local extensions built on the typed core
config/                  Runtime config (pmcc_config.json, watch_rules.json)
orders/{YYYY-MM-DD}/     Generated trade proposals (local, gitignored)
analysis/{YYYY-MM-DD}/   Scenario matrices and model output (local, gitignored)
.codex/skills/           Repo-local Codex skill definitions
```

## Key Commands

```bash
# Inspect any typed function signature
uv run python one_off_scripts/show_signature.py ibkr connect
uv run python one_off_scripts/show_signature.py stratoforge.pricing.heston heston_price

# Calibrate option pricing model against live chain
uv run python stratoforge/pricing/calibrate.py

# Run tests
uv run pytest
```

## Extending

Put new automation in `custom_scripts/`. Import and reuse the typed core modules
(`ibkr`, `option_pricing`, `stock_tooling`, `helpers`) rather than duplicating
broker or pricing logic.

## Safety

This repo can generate and submit live orders. Treat every generated proposal as
a draft until you verify it. Margin, routing, and product availability assumptions
can be wrong with stale data. Nothing here is investment advice.

## License

This project is currently unlicensed. No LICENSE file is provided.
