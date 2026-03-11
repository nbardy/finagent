# Repo Layout

The repo is now organized around three buckets:

- `helpers/`
  Pure reusable libraries and shared types. These files should stay importable and testable without acting like ad hoc scripts.

- `stock_tooling/`
  Generic per-symbol tools. These are the scripts that accept stock names, price structures, score scenarios, or dump JSON artifacts.

- `one_off_scripts/`
  Orchestration entrypoints. These compose helpers plus stock tooling into a specific live workflow.

- `custom_scripts/`
  Repo-specific extensions that lean on the typed core utilities but own their own workflow.

- `research_sessions/`
  Local generated research workspaces with source captures, analysis notes, and final reports.

Conventions:

- Put new pricing, ranking, state, and reusable JSON-building logic in `helpers/`.
- Put reusable CLIs like `price_*`, `planner_*`, `watch_*`, and scenario analyzers in `stock_tooling/`.
- Put workflow runners like urgent event deployment scripts in `one_off_scripts/`.
- Put repo-specific longer-lived automation in `custom_scripts/`.
- Keep top-level files only as compatibility shims or root infra entrypoints.
- Keep generated research output in `research_sessions/`, not mixed into source folders.

Examples:

- [helpers/urgent_hedge.py](/Users/nicholasbardy/git/ikbr_trader/helpers/urgent_hedge.py)
- [helpers/urgent_hedge_types.py](/Users/nicholasbardy/git/ikbr_trader/helpers/urgent_hedge_types.py)
- [stock_tooling/portfolio_scenario_ev.py](/Users/nicholasbardy/git/ikbr_trader/stock_tooling/portfolio_scenario_ev.py)
- [stock_tooling/price_probe.py](/Users/nicholasbardy/git/ikbr_trader/stock_tooling/price_probe.py)
- [stock_tooling/planner_weekly.py](/Users/nicholasbardy/git/ikbr_trader/stock_tooling/planner_weekly.py)
- [one_off_scripts/run_urgent_hedge.py](/Users/nicholasbardy/git/ikbr_trader/one_off_scripts/run_urgent_hedge.py)
- [custom_scripts/research_session.py](/Users/nicholasbardy/git/ikbr_trader/custom_scripts/research_session.py)
