# Photonics Execution And Orders
**Recorded:** 2026-03-12 03:56
**Scope:** Live photonics sleeve work, Soitec routing, after-hours stock buys, current holdings, and resting orders.

## Main Decisions

- Treat photonics as a sleeve built over days or weeks with a mix of near-tape bids and crash bids.
- Do not chase Soitec after the recent squeeze-like move.
- Keep Paris `SOI` pullback orders working.
- Add to `AXTI` after hours because it is trading with momentum and the user wanted more immediate exposure.
- Buy `TSEM` after hours as an additional semiconductor/photonics-adjacent position.

## Tradable Instrument Conclusions

### Soitec

- `SOI` on `SMART`, primary `SBF`, currency `EUR` is the clean tradable line in this IBKR setup.
- `SLOIF` did not qualify in this IBKR setup.
- `SLOIY` did qualify, but it is an unsponsored ADR wrapper rather than the Paris ordinary share.
- The lower `SLOIY` price is explained by the ADR ratio rather than by a bad quote.

### AXTI And TSEM Session Behavior

- `AXTI` is tradable after hours in IBKR and also lists `OVERNIGHT` as a valid venue.
- `TSEM` is tradable after hours in IBKR and also lists extended session hours.
- The repo's default executor config does not send stock orders with `outsideRth=true`, so after-hours buys were submitted directly through IBKR instead of through the default executor path.

## Files Created

- `orders/2026-03-11/soitec_buy_20k.json`
- `orders/2026-03-12/photonics_add_100k_limits.json`
- `orders/2026-03-12/photonics_soi_axti_add_20k.json`
- `orders/2026-03-12/iqe_add_10k_limits.json`
- `orders/2026-03-12/5210_add_10pct_20pct_10k_each.json`
- `orders/2026-03-11/tsem_afterhours_buy_20k.json`
- `orders/2026-03-11/axti_afterhours_add_5k.json`

## Orders Actually Sent

Via `executor.py`:

- `orders/2026-03-12/photonics_soi_axti_add_20k.json`
- `orders/2026-03-12/iqe_add_10k_limits.json`
- `orders/2026-03-12/5210_add_10pct_20pct_10k_each.json`

Submitted directly through IBKR because after-hours stock buys needed `outsideRth=true`:

- `orders/2026-03-11/tsem_afterhours_buy_20k.json`
- `orders/2026-03-11/axti_afterhours_add_5k.json`

## Confirmed Fills

- `AXTI` `70` shares at `47.5`
- `TSEM` `166` shares at `123.0`
- `AXTI` `105` shares at `47.7`

No confirmed fills yet for:

- `SOI`
- `IQE`
- `AAOI`
- `5210`

## Current Photonics / Related Holdings

At the end of the thread, live holdings were:

- `AAOI`: `67`
- `AXTI`: `175`
- `IQE`: `49,000`
- `5210`: `400`
- `SOI`: `0`
- `TSEM`: `166`

## Current Resting Orders

- `AAOI`: `67 @ 111`
- `AXTI`: `195 @ 38`, `195 @ 39`, `72 @ 46`, `74 @ 44.5`
- `IQE`: `11,000 @ 23p`, `11,000 @ 22p`, `11,000 @ 21p`, `7,800 @ 19.9p`, `8,400 @ 18.5p`, `9,100 @ 17.0p`
- `SOI`: `54 @ 54 EUR`, `55 @ 53 EUR`, `54 @ 52 EUR`
- `5210`: `600 @ 2800`, `600 @ 2500`, `100 @ 2750`, `100 @ 2550`, `100 @ 2350`

Approximate pending photonics exposure after the final AXTI fill:

- about `USD 79k` equivalent

## Practical State At End Of Thread

- The sleeve has real live exposure now rather than just staged files.
- `SOI` is set up as pullback accumulation rather than a chase.
- `AXTI` was increased both through a regular-session fill and an after-hours fill.
- `TSEM` was added in after hours.
- The account still has a large live resting photonics buy stack under the market.
