# Photonics, Margin, and Soitec Work Log
**Recorded:** 2026-03-12 02:44
**Scope:** Photonics accumulation plan, IBKR margin interpretation, Soitec routing, and live order state.

## Main Outcomes

- Confirmed current photonics sleeve and live broker state.
- Clarified IBKR account metrics: cash, available funds, buying power, excess liquidity, and margin usage.
- Created and refined a repo-local `ikbr-margin` skill under `skills/private/ikbr-margin/`.
- Staged and transmitted new photonics stock limit orders.
- Confirmed `SLOIF` is not tradable in this IBKR setup.
- Confirmed `SOI` on Paris is the clean Soitec route, while `SLOIY` is a U.S. unsponsored ADR representing half a share.
- Decided not to chase Soitec after the liquidity squeeze; keep Paris GTC pullback orders working.

## Margin / Account Findings

Key interpretation:
- `TotalCashValue` is actual cash.
- `AvailableFunds` is opening room under initial margin.
- `BuyingPower` is a margin-derived capacity number, not cash.
- `ExcessLiquidity` is the practical liquidation cushion.
- Positive cash means there is no current negative-cash margin loan.
- `GrossPositionValue` is inflated by the options book and is not the same thing as cash deployed into stock.

Important conclusions reached:
- The account still has cash.
- The user is not currently using negative-cash stock margin.
- Options are a major reason `NetLiquidation` and `GrossPositionValue` look large relative to stock market value.
- The user’s preferred leverage lens is `max(0, -cash) / stock market value`.

## Skill Work

Created:
- `skills/private/ikbr-margin/SKILL.md`
- `skills/private/ikbr-margin/references/ibkr-margin-metrics.md`

Refined:
- added look-ahead and full margin tags
- added common misreads section
- added guidance for answering "how much margin can I use comfortably?"

Validation:
- validated successfully with the local quick validator

## Files Created

- `orders/2026-03-11/soitec_buy_20k.json`
- `orders/2026-03-12/photonics_add_100k_limits.json`
- `orders/2026-03-12/photonics_soi_axti_add_20k.json`
- `orders/2026-03-12/iqe_add_10k_limits.json`
- `orders/2026-03-12/5210_add_10pct_20pct_10k_each.json`

## Orders Actually Submitted

Submitted with `executor.py`:

1. `orders/2026-03-12/photonics_soi_axti_add_20k.json`
2. `orders/2026-03-12/iqe_add_10k_limits.json`
3. `orders/2026-03-12/5210_add_10pct_20pct_10k_each.json`

## Confirmed Fills

Confirmed photonics fill:
- `AXTI` bought `70` shares at `47.5`

No confirmed fills yet for:
- `SOI`
- `IQE`
- `AAOI`
- `5210`

## Current Photonics Holdings

- `AAOI`: `67`
- `AXTI`: `70`
- `IQE`: `49,000`
- `5210`: `400`
- `SOI`: `0`

## Current Open Photonics Orders

- `AAOI`: `67 @ 111`
- `AXTI`: `195 @ 39`, `195 @ 38`, `72 @ 46`, `74 @ 44.5`
- `IQE`: `11,000 @ 23p`, `11,000 @ 22p`, `11,000 @ 21p`, `7,800 @ 19.9p`, `8,400 @ 18.5p`, `9,100 @ 17.0p`
- `SOI`: `54 @ 54 EUR`, `55 @ 53 EUR`, `54 @ 52 EUR`
- `5210`: `600 @ 2800`, `600 @ 2500`, `100 @ 2750`, `100 @ 2550`, `100 @ 2350`

Status notes:
- U.S. names showed `Submitted`
- London, Paris, and Tokyo names showed `PreSubmitted` while queued outside their active sessions

## Soitec Instrument Conclusion

Broker findings:
- `SOI` qualifies in IBKR as the Paris ordinary share
- `SLOIF` does not qualify in this IBKR setup
- `SLOIY` does qualify as `S.O.I.T.E.C.-UNSPON ADR`

Interpretation:
- `SOI` is the clean ordinary share route
- `SLOIY` is a legitimate ADR, but it is not the same unit
- `SLOIY` represents `0.5` ordinary share, which explains the lower price
- `SLOIF` may exist in public quote systems, but it is not usable here as currently configured

Trading decision:
- do not chase Soitec through the ADR
- leave the Paris GTC pullback ladder working
- treat the recent move as a potential liquidity squeeze / buzz-driven jump

## Working View Going Forward

- The photonics basket is set up to scale in over days or weeks.
- No urgent new filing is needed to maintain the current photonics plan.
- `AAOI` is the main name that may need a higher ladder later if faster fills are desired.
- The current `SOI` ladder is intentionally conservative and should remain live unless repriced later.

## Note On Conventions

The root `AGENTS.md` does not define an `agent_notes` filename convention.
Existing files use mixed naming styles.
This note adopts the requested format:
- `agent_notes/{datetime}_{topic}.md`
