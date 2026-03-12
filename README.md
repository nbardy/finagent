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
- `research_sessions/{timestamp}_{topic}/`
  Local deep-research workspaces with notes, source captures, analysis, and a final report
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
- a stock research orchestrator that drives Codex and saves artifacts into a session folder

The repo already includes a research scaffold at [`custom_scripts/research_session.py`](custom_scripts/research_session.py).
It can:

- create a timestamped research session tree
- ask Codex to research in multiple turns and capture the `thread_id`
- optionally fetch the latest public X/Twitter post for a user
- resolve tracked X/Twitter accounts from `config/x_accounts.json`
- print named X/Twitter account lists from the CLI
- organize outputs into `loose_notes/`, `documents/`, `analysis/`, `conclusions/`, and `final_report.md`
- run latest-tweet lookup by itself without creating a research session

Examples:

```bash
uv run python custom_scripts/research_session.py research TSEM --ticker TSEM --prompt "Research Tower Semiconductor after the recent move. Focus on foundry demand, margins, valuation, and risks." --x-user towersemi
uv run python custom_scripts/research_session.py research TSEM --ticker TSEM --x-account citrini
uv run python custom_scripts/research_session.py latest-tweet towersemi --output-dir agent_notes/towersemi_latest_tweet
uv run python custom_scripts/research_session.py latest-tweet --account nick_reece
uv run python custom_scripts/research_session.py list-x-accounts --list citrini_affiliates
```

There is also an X cashtag polling helper at [`custom_scripts/x_ticker_watch.py`](custom_scripts/x_ticker_watch.py).
It can:

- poll a tracked account list or explicit account set
- persist a local dedupe state so hourly polling does not reprocess the same post URLs
- extract `$TICKER` mentions from new source posts
- fetch recent related X/Twitter posts for each extracted ticker
- bound each nested X query with a timeout so the hourly poll fails with caveats instead of hanging forever
- write JSON and markdown summaries into `analysis/{today}/`

Examples:

```bash
uv run python custom_scripts/x_ticker_watch.py
uv run python custom_scripts/x_ticker_watch.py --list citrini_affiliates --limit-per-account 8 --related-limit 6
uv run python custom_scripts/x_ticker_watch.py --account citrini --account nick_reece --output analysis/2026-03-12/citrini_watch.json
uv run python custom_scripts/x_ticker_watch.py --query-timeout-seconds 120
```

For hourly polling, schedule the single-run command:

```bash
0 * * * * cd /Users/nicholasbardy/git/ikbr_trader && /usr/bin/env uv run python custom_scripts/x_ticker_watch.py
```

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
uv run python one_off_scripts/show_signature.py custom_scripts.research_session do_research
uv run python one_off_scripts/show_signature.py custom_scripts.research_session get_users_latest_tweet
```

This is the fastest repo-native way to inspect the core API surface before writing a new `custom_scripts/` tool.

## Config

Tracked, public-safe config files:

- [`config/pmcc_config.json`](config/pmcc_config.json)
- [`config/probe_config.example.json`](config/probe_config.example.json)
- [`config/watch_rules.json`](config/watch_rules.json)
- [`config/x_accounts.json`](config/x_accounts.json)

Local-only files are ignored:

- `config/probe_config.json`
- `config/portfolio_state.json`
- `config/regime_state.json`
- `config/portfolio_dump.json`
- `config/x_ticker_watch_state.json`
- generated `orders/`
- generated `analysis/`
- generated `research_sessions/`
- local Codex runtime config

If you need a local probe config:

```bash
cp config/probe_config.example.json config/probe_config.json
```

## Generated Files

This repo treats live proposals, analysis output, portfolio dumps, and research sessions as local artifacts rather than source code.

That means:

- `orders/` is for local generated order JSON
- `analysis/` is for local generated model output
- `research_sessions/` is for local research workspaces
- `agent_notes/` is for tracked operating notes and retrospectives

`research_sessions/` stays ignored by default because it can accumulate large, messy source captures.

## Safety

- This repo can generate and submit live orders.
- Margin, liquidity, and routing assumptions can be wrong if you use stale data.
- IBKR API permissions, exchange hours, and product availability vary by account and venue.
- Treat every generated order as draft until you verify it.

Nothing in this repo is investment advice.
