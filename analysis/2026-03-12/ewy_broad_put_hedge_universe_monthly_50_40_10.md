# ewy_broad_put_hedge_universe_monthly_50_40_10

Spot: `130.37`
Candidates: `384`
Budget target: `25000`
Base book: Current live EWY option book excluding the existing Apr10 135/120 put hedge; includes current short-call sleeve.

## Scenarios

- `50%` Choppy month flat | days `31` | spot `130.37` | vol `+0.00`
- `40%` Down 8% over month | days `31` | spot `119.94` | vol `+0.01`
- `10%` Rally 8% over month | days `31` | spot `140.8` | vol `-0.05`

## Top 15

1. `Add + 2026-04-10/2026-04-24 120P cal x238` | type `put_calendar_overlay` | entry `24990` | overlay EV `59043` | combined EV `64083` | downside cover `71.4%`
2. `Add + 2026-04-10/2026-04-24 130P cal x185` | type `put_calendar_overlay` | entry `24975` | overlay EV `51819` | combined EV `56858` | downside cover `15.5%`
3. `Add + 2026-04-10/2026-04-24 125P cal x200` | type `put_calendar_overlay` | entry `25000` | overlay EV `49397` | combined EV `54436` | downside cover `38.2%`
4. `Add + 2026-04-10/2026-04-17 120P cal x357` | type `put_calendar_overlay` | entry `24990` | overlay EV `47132` | combined EV `52171` | downside cover `72.7%`
5. `Add + 2026-04-10/2026-04-17 135P cal x455` | type `put_calendar_overlay` | entry `25025` | overlay EV `46230` | combined EV `51269` | downside cover `9.1%`
6. `Add + 2026-04-10/2026-04-17 130P cal x278` | type `put_calendar_overlay` | entry `25020` | overlay EV `45999` | combined EV `51039` | downside cover `8.8%`
7. `Add + 2026-04-10/2026-04-24 135P cal x227` | type `put_calendar_overlay` | entry `24970` | overlay EV `40664` | combined EV `45704` | downside cover `7.7%`
8. `Add + 2026-03-27 135/130 x143` | type `put_spread_overlay` | entry `25025` | overlay EV `36680` | combined EV `41719` | downside cover `28.8%`
9. `Add + 2026-04-10/2026-04-24 140P cal x278` | type `put_calendar_overlay` | entry `25020` | overlay EV `35383` | combined EV `40423` | downside cover `3.9%`
10. `Add + 2026-04-10/2026-05-15 130P cal x77` | type `put_calendar_overlay` | entry `25025` | overlay EV `31915` | combined EV `36955` | downside cover `11.4%`
11. `Add + 2026-04-10/2026-05-15 120P cal x85` | type `put_calendar_overlay` | entry `25075` | overlay EV `31532` | combined EV `36572` | downside cover `33.7%`
12. `Add + 2026-04-10/2026-05-15 125P cal x81` | type `put_calendar_overlay` | entry `25110` | overlay EV `30889` | combined EV `35929` | downside cover `22.4%`
13. `Add + 2026-04-10/2026-04-17 125P cal x263` | type `put_calendar_overlay` | entry `24985` | overlay EV `27921` | combined EV `32961` | downside cover `26.3%`
14. `Add + 2026-04-02/2026-04-10 150P cal x625` | type `put_calendar_overlay` | entry `25000` | overlay EV `25468` | combined EV `30507` | downside cover `88.6%`
15. `Add + 2026-04-02 135/130 x116` | type `put_spread_overlay` | entry `24940` | overlay EV `25114` | combined EV `30153` | downside cover `20.5%`
