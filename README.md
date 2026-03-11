# FinAgent

`ikbr_trader` is the codebase behind **FinAgent**, a repo-local Codex workspace for Interactive Brokers trading workflows.
It combines:

- IBKR-backed pricing and portfolio reads
- option modeling and hedge analysis
- broker-ready order proposal generation
- repo-local Codex skills under [`.codex/skills/`](.codex/skills/)
- typed core trading utilities that custom logic can build on

Open the repo in Codex, and you get **FinAgent**: a trading-focused AI workspace rather than a generic coding shell.

## What This Repo Is

This is not a fully autonomous trading bot.
It is a supervised trading workspace that helps with:

- portfolio inspection
- option pricing and hedge modeling
- stock and option order proposal generation
- execution discipline and fill management
- IBKR margin and liquidation-risk interpretation

## Quick Start

1. Install IB Gateway and make sure you can log in.
2. Clone this repo.
3. Open the repo root in a terminal.
4. Install Python dependencies with `uv`.
5. Run `codex` inside the repo.
6. Keep IB Gateway running while using live broker-backed tools.

Minimal flow:

```bash
git clone <your-repo-url>
cd ikbr_trader
uv sync
codex
```

If IB Gateway is running locally on the default host/port in [`config/pmcc_config.json`](config/pmcc_config.json), Codex can use the repo tooling and skills immediately.

In practice:

- install IB Gateway
- clone this repo
- run `codex` inside it
- and you have **FinAgent**

## Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv)
- IB Gateway
- Interactive Brokers account with API access enabled
- Codex CLI installed locally so `codex` works from the terminal

Recommended:

- start with paper trading
- use a dedicated IB Gateway session for API work
- review all generated orders before sending them

## Repository Layout

- `config/`
  Runtime config and examples
- `orders/{YYYY-MM-DD}/`
  Local generated trade proposals
- `analysis/{YYYY-MM-DD}/`
  Local generated scenario outputs and audits
- `custom_scripts/`
  Repo-local extension scripts and strategy-specific logic
- `option_pricing/`
  Pricing models and shared option logic
- `stock_tooling/`
  Planner, pricing, scenario, and watch tooling
- `one_off_scripts/`
  Small support scripts, including signature inspection helpers
- `.codex/skills/`
  Repo-local Codex skill definitions

See:

- [AGENTS.md](AGENTS.md)
- [REPO_LAYOUT.md](REPO_LAYOUT.md)
- [.codex/skills/SKILLS_INDEX.md](.codex/skills/SKILLS_INDEX.md)

## How To Extend

Put repo-specific custom logic in `custom_scripts/`.

The intended pattern is:

- ask your agent to write new logic in `custom_scripts/`
- keep one-off or strategy-specific logic there
- import and lean on the typed core utilities instead of re-implementing broker, pricing, or watch logic

Core utility modules to reuse:

- [`ibkr.py`](ibkr.py)
- [`option_pricing/`](option_pricing/)
- [`stock_tooling/`](stock_tooling/)
- [`helpers/`](helpers/)

Examples of good extensions:

- a new sector-specific deployment planner
- a custom stock ladder builder
- a new execution watcher
- a portfolio-specific overlay screener

### Inspect Function Signatures

To inspect a typed function from the terminal, use:

```bash
uv run python one_off_scripts/show_signature.py ibkr connect
```

Examples:

```bash
uv run python one_off_scripts/show_signature.py ibkr get_open_orders
uv run python one_off_scripts/show_signature.py stock_tooling.watch_rules load_watch_rules
uv run python one_off_scripts/show_signature.py option_pricing.probe build_probe_trades
```

This is the fastest repo-native way to inspect the core API surface before writing a new `custom_scripts/` tool.

## Config

Tracked, public-safe config files:

- [`config/pmcc_config.json`](config/pmcc_config.json)
- [`config/probe_config.example.json`](config/probe_config.example.json)
- [`config/watch_rules.json`](config/watch_rules.json)

Local-only files are ignored:

- `config/probe_config.json`
- `config/portfolio_state.json`
- `config/regime_state.json`
- `config/portfolio_dump.json`
- generated `orders/`
- generated `analysis/`
- `agent_notes/`
- local Codex runtime config

If you need a local probe config:

```bash
cp config/probe_config.example.json config/probe_config.json
```

## Generated Files

This repo treats live proposals, analysis output, portfolio dumps, and working notes as local artifacts rather than source code.

That means:

- `orders/` is for local generated order JSON
- `analysis/` is for local generated model output
- `agent_notes/` is for local operating notes

These paths are ignored for future work and should not be part of a public push.

## Safety

- This repo can generate and submit live orders.
- Margin, liquidity, and routing assumptions can be wrong if you use stale data.
- IBKR API permissions, exchange hours, and product availability vary by account and venue.
- Treat every generated order as draft until you verify it.

Nothing in this repo is investment advice.
