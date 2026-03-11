# ewy_live_hedge_universe_monthly_50_40_10

Spot: `131.71`
Candidates: `54`
Base book: current live EWY book excluding existing Apr10 135/120 hedge; current short-call sleeve retained.

## Scenarios

- `50%` Choppy month flat | days `31` | spot `131.71` | vol `+0.00`
- `40%` Down 8% over month | days `31` | spot `121.17` | vol `+0.01`
- `10%` Rally 8% over month | days `31` | spot `142.25` | vol `-0.05`

## Top 10

1. `Add + 2026-04-10/2026-05-15 135P cal x88` | type `put_calendar_overlay` | entry `25080` | overlay EV `31589` | combined EV `52207` | downside cover `11.7%`
2. `Add + 2026-04-02/2026-04-17 130P cal x156` | type `put_calendar_overlay` | entry `24960` | overlay EV `28353` | combined EV `48971` | downside cover `33.8%`
3. `Add + 2026-04-10/2026-05-15 140P cal x81` | type `put_calendar_overlay` | entry `25110` | overlay EV `16410` | combined EV `37028` | downside cover `1.2%`
4. `Add + 2026-04-10 145/130 x29` | type `put_spread_overlay` | entry `25375` | overlay EV `12290` | combined EV `32908` | downside cover `14.2%`
5. `Add + 2026-04-10 140/130 x44` | type `put_spread_overlay` | entry `24860` | overlay EV `10978` | combined EV `31596` | downside cover `15.0%`
6. `Add + 2026-04-02 150/130 x19` | type `put_spread_overlay` | entry `24510` | overlay EV `10184` | combined EV `30802` | downside cover `10.6%`
7. `Add + 2026-04-10 145/125 x23` | type `put_spread_overlay` | entry `24955` | overlay EV `9517` | combined EV `30135` | downside cover `16.5%`
8. `Add + 2026-04-10 145/120 x21` | type `put_spread_overlay` | entry `25515` | overlay EV `8606` | combined EV `29224` | downside cover `18.1%`
9. `Add + 2026-04-10 135/130 x91` | type `put_spread_overlay` | entry `25025` | overlay EV `8144` | combined EV `28762` | downside cover `16.1%`
10. `Add + 2026-04-17 140/130 x47` | type `put_spread_overlay` | entry `24910` | overlay EV `7761` | combined EV `28379` | downside cover `13.9%`
