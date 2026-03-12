# TODO

## Now

- Add a thesis-registry backfill tool for pre-existing IBKR holdings and open orders.
  - Create a CLI that polls current positions, open orders, and recent fills from IBKR.
  - Identify any rows that do not resolve to a local thesis in `config/thesis_registry.db`.
  - Support attaching a descriptive rationale to existing stock, option, and BAG holdings after the fact.
  - Write or update `thesis_id`, `orderRef`, and order-event links locally without inventing local position state.
  - Keep IBKR as the source of truth for live portfolio state; SQLite stays as the rationale/enrichment layer only.
  - Add tests for instrument matching and thesis lookup fallback behavior.
- Add an API-first tweet provider for `get_users_latest_tweet()`.
  - Prefer the official X API.
  - Keep the current Codex/browser path as a fallback only.
  - Add local config/env support for bearer-token auth.
- Harden `custom_scripts/research_session.py` against long-running Codex sessions and partial failures.
- Add a downloader pass that saves filings, statements, and articles with normalized filenames and source metadata.
- Add tests for research-session path creation, Codex event parsing, session manifest updates, and CLI subcommands.

## Next

- Add a small provider abstraction for research inputs:
  - tweet source
  - filing/article fetcher
  - document normalizer
- Add a payment plan for agent-run research tools:
  - no agent-purchased subscriptions
  - pre-approved credits or budgeted API usage only
  - x402 treated as a payment rail, not a product model
- If x402 is used, implement prepaid credit bundles in our own system ledger.
  - Metronome is optional, not required.
  - Prefer internal balance tracking and top-up thresholds over raw per-call settlement for tiny requests.

## Later

- Add a stock-side accumulation/execution skill for ladder design, pending-notional audits, and session-aware routing.
- Decide whether `research_sessions/` should stay local-only forever or get a tracked template/example subfolder.
