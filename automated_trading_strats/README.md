# Automated Trading Strategies

Tracked strategy definitions live here. Generated runs, scratch outputs, and local experimentation files under each strategy directory stay gitignored unless explicitly whitelisted.

Current tracked files per strategy:

- `README.md`
- `strategy.md`
- `strategy_manifest.json`

Tooling hook:

```bash
uv run python one_off_scripts/show_signature.py custom_scripts.automated_trading_strats save_strategy_note
```

CLI hook:

```bash
uv run python -m custom_scripts.automated_trading_strats --strategy whale_wake_cross_sectional_screener --print-manifest
```
