# 2026-03-23 Stratoforge Consolidation And Modeling Status

## Summary

This session moved Stratoforge from thesis-aware candidate generation into a scored, documented, and more production-usable toolchain.

The major changes landed across four areas:

1. scoring and model policy
2. calibration speed and reuse
3. benchmark coverage
4. canonical entrypoints and output shape

## Current Modeling Stack

- `SSVI` is the canonical same-time surface fit.
- `Bates` is the primary structural repricer when it passes fit gating.
- `Heston` remains the transitional structural fallback.
- `BS` is the fallback / executable sanity anchor.
- `VG` and `MJD` are available but are not default consensus participants unless they fit well enough.

The scorer now reports model policy explicitly and records the models actually used in each scenario breakdown.

## Implemented Speed Work

- Heston/VG hot-path pricing was optimized.
- `calibrate_heston()` moved from the old scalar `L-BFGS-B` path to bounded `least_squares(trf)`.
- calibration cache support was added in `config/calibration_cache.json`
- warm starts from the latest cached fit of the same model were added
- exact cache hits now bypass recalibration entirely

## Observed Runtime Results

- scored SPY thesis, cold cache: about `22.2s`
- scored SPY thesis, warm exact-cache-hit rerun: about `1.24s`
- Heston cold calibration on the SPY 25-quote slice: about `2.6s`

The cache is the dominant practical speed win so far.

## Benchmark Findings

### Heston Solver

- `least_squares(trf)` beat the old Heston solver path materially while preserving fit quality.

### Heston Subset Sensitivity

- `5` quotes generalized badly
- `10-15` quotes looked like the best Heston speed/accuracy tradeoff

### Bates Subset Sensitivity

- `10` quotes was faster but degraded validation fit materially
- `15` quotes was close in fit to the full slice but was not faster on the measured run
- result: do not change the default Bates quote count yet

### Bates Solver Benchmark

- `linear` loss was slightly faster than `soft_l1` with essentially identical RMSE
- `calibrate_bates()` now uses the `linear` setting

### Fixed-Grid Prototype

Fixed-grid Heston/Bates pricers were added alongside the current `quad()` reference path.

On the isolated comparison benchmark:

- Heston fixed-grid speedup: about `1.62x`
- Bates fixed-grid speedup: about `2.70x`
- observed pricing errors on the benchmark grid were extremely small

These paths are not yet wired into calibration or scoring by default.

## Canonical Tooling Path

Canonical scored entrypoint:

- `custom_scripts/run_stratoforge.py`

Backward-compatible wrapper kept:

- `custom_scripts/score_strategy_universe.py`

The canonical entrypoint should be the default reference in future notes and docs.

## Output Shape

Scored payloads now include:

- `calibration_summary`
- `surface_summary`
- `model_policy`
- per-candidate `scenario_breakdown`
- per-scenario `models_used` and `model_values`

This means forecast outputs now expose the pricing model policy instead of leaving it implicit.

## Next High-Value Work

The next serious move is no longer small solver tuning.

Highest-value next step:

- wire the fixed-grid Heston/Bates paths into calibration and scoring behind a feature flag
- compare calibration RMSE parity and end-to-end ranking parity before any default switch

Lower-value work for now:

- more quote-subset tuning
- more small solver tweaks

## Files To Look At

- `custom_scripts/run_stratoforge.py`
- `stratoforge/stratoforge/scoring.py`
- `stratoforge/stratoforge/pricing/calibrate.py`
- `stratoforge/stratoforge/pricing/calibration_cache.py`
- `stratoforge/stratoforge/pricing/heston.py`
- `stratoforge/stratoforge/pricing/bates.py`
