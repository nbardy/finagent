# ewy_broad_put_hedge_universe_weekly_35_40_15_10

Spot: `130.37`
Candidates: `384`
Budget target: `25000`
Base book: Current live EWY option book excluding the existing Apr10 135/120 put hedge; includes current short-call sleeve.

## Scenarios

- `35%` Bottom Apr02 then rebound by earnings | days `21` | spot `122.55` | vol `+0.03`
- `40%` Bottom Apr10 then rebound by earnings | days `29` | spot `121.24` | vol `+0.02`
- `15%` Choppy hold into earnings window | days `29` | spot `130.37` | vol `+0.01`
- `10%` Early squeeze higher before earnings | days `29` | spot `140.8` | vol `-0.05`

## Top 15

1. `Add + 2026-04-10/2026-04-24 120P cal x238` | type `put_calendar_overlay` | entry `24990` | overlay EV `52097` | combined EV `58706` | downside cover `99.5%`
2. `Add + 2026-04-10/2026-04-24 125P cal x200` | type `put_calendar_overlay` | entry `25000` | overlay EV `43655` | combined EV `50264` | downside cover `71.3%`
3. `Add + 2026-04-10/2026-04-17 120P cal x357` | type `put_calendar_overlay` | entry `24990` | overlay EV `43337` | combined EV `49946` | downside cover `91.7%`
4. `Add + 2026-03-27 135/130 x143` | type `put_spread_overlay` | entry `25025` | overlay EV `38531` | combined EV `45140` | downside cover `56.1%`
5. `Add + 2026-03-27/2026-04-02 125P cal x357` | type `put_calendar_overlay` | entry `24990` | overlay EV `32860` | combined EV `39469` | downside cover `23.3%`
6. `Add + 2026-04-10/2026-04-17 135P cal x455` | type `put_calendar_overlay` | entry `25025` | overlay EV `31679` | combined EV `38288` | downside cover `5.9%`
7. `Add + 2026-04-10/2026-04-24 130P cal x185` | type `put_calendar_overlay` | entry `24975` | overlay EV `29230` | combined EV `35839` | downside cover `33.1%`
8. `Add + 2026-04-02/2026-04-10 130P cal x263` | type `put_calendar_overlay` | entry `24985` | overlay EV `29114` | combined EV `35723` | downside cover `51.0%`
9. `Add + 2026-04-10/2026-04-17 125P cal x263` | type `put_calendar_overlay` | entry `24985` | overlay EV `27963` | combined EV `34572` | downside cover `50.5%`
10. `Add + 2026-04-10/2026-05-15 120P cal x85` | type `put_calendar_overlay` | entry `25075` | overlay EV `27708` | combined EV `34317` | downside cover `50.4%`
11. `Add + 2026-04-10/2026-04-24 135P cal x227` | type `put_calendar_overlay` | entry `24970` | overlay EV `26446` | combined EV `33054` | downside cover `13.3%`
12. `Add + 2026-04-10/2026-05-15 125P cal x81` | type `put_calendar_overlay` | entry `25110` | overlay EV `26379` | combined EV `32988` | downside cover `41.9%`
13. `Add + 2026-04-02 135/130 x116` | type `put_spread_overlay` | entry `24940` | overlay EV `26064` | combined EV `32673` | downside cover `39.9%`
14. `Add + 2026-04-02/2026-04-17 130P cal x135` | type `put_calendar_overlay` | entry `24975` | overlay EV `25418` | combined EV `32027` | downside cover `35.9%`
15. `Add + 2026-04-10/2026-04-24 115P cal x179` | type `put_calendar_overlay` | entry `25060` | overlay EV `25309` | combined EV `31918` | downside cover `52.0%`
