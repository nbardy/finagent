# ewy_live_hedge_universe_weekly_35_40_15_10

Spot: `131.71`
Candidates: `54`
Base book: current live EWY book excluding existing Apr10 135/120 hedge; current short-call sleeve retained.

## Scenarios

- `35%` Bottom Apr02 then rebound by earnings | days `21` | spot `123.81` | vol `+0.03`
- `40%` Bottom Apr10 then rebound by earnings | days `29` | spot `122.49` | vol `+0.02`
- `15%` Choppy hold into earnings window | days `29` | spot `131.71` | vol `+0.01`
- `10%` Early squeeze higher before earnings | days `29` | spot `142.25` | vol `-0.05`

## Top 10

1. `Add + 2026-04-02/2026-04-17 130P cal x156` | type `put_calendar_overlay` | entry `24960` | overlay EV `35663` | combined EV `57520` | downside cover `92.9%`
2. `Add + 2026-04-02/2026-04-10 130P cal x263` | type `put_calendar_overlay` | entry `24985` | overlay EV `30207` | combined EV `52064` | downside cover `93.9%`
3. `Add + 2026-04-10/2026-05-15 135P cal x88` | type `put_calendar_overlay` | entry `25080` | overlay EV `22090` | combined EV `43947` | downside cover `34.5%`
4. `Add + 2026-04-10/2026-05-15 110P cal x99` | type `put_calendar_overlay` | entry `24998` | overlay EV `14983` | combined EV `36840` | downside cover `49.3%`
5. `Add + 2026-04-02 150/130 x19` | type `put_spread_overlay` | entry `24510` | overlay EV `11055` | combined EV `32912` | downside cover `28.6%`
6. `Add + 2026-04-10 145/130 x29` | type `put_spread_overlay` | entry `25375` | overlay EV `10873` | combined EV `32730` | downside cover `37.8%`
7. `Add + 2026-04-10/2026-05-15 140P cal x81` | type `put_calendar_overlay` | entry `25110` | overlay EV `10838` | combined EV `32695` | downside cover `3.7%`
8. `Add + 2026-04-10 145/120 x21` | type `put_spread_overlay` | entry `25515` | overlay EV `10565` | combined EV `32422` | downside cover `42.1%`
9. `Add + 2026-04-10 145/125 x23` | type `put_spread_overlay` | entry `24955` | overlay EV `10458` | combined EV `32315` | downside cover `40.4%`
10. `Add + 2026-04-10 140/130 x44` | type `put_spread_overlay` | entry `24860` | overlay EV `9890` | combined EV `31747` | downside cover `39.6%`
