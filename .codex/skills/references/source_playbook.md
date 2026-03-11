# Source Playbook

Use this reference when a skill needs current external facts.

## Core Rule

Skills can encode:

- what to check
- which source to trust
- which local script to run

Skills do not replace the need to fetch current facts.

## Source Priority

### Executable pricing

Use:

1. IBKR

Do not use public web sources to set executable limits.

### Event dates

Use:

1. official IR / issuer pages
2. exchange calendars
3. third-party earnings calendars only as fallback

### ETF holdings and weights

Use:

1. issuer / fund sponsor pages
2. reputable holdings mirrors only as fallback

### News-driven macro inputs

Use:

1. Reuters
2. AP
3. official government / company releases when relevant

### Strategy mechanics

Use primary sources:

1. IBKR for broker behavior, assignment, margin, order handling
2. OIC / OCC for options mechanics
3. Fidelity or similar major broker education pages as secondary references

## Research vs Execution

Public chain sites can be acceptable for:

- rough structure ranking
- confirming listed expiries and strikes
- sanity-checking public market context

They are not acceptable for:

- final executable limit prices
- live fill decisions
- silent replacement of missing broker data

## Required Analysis Metadata

When writing modeling output, prefer to include:

- `as_of`
- `spot_source`
- `option_source`
- `event_source`
- `news_source`
- `holdings_source`
- `used_fallback`

If the current scripts do not yet emit all of these, state them in the narrative summary.

## Hard Stops

Stop and say so if:

- IBKR quote data is incomplete for executable work
- the event date is central to the thesis and still unconfirmed
- the structure relies on a strike or expiry that is not clearly listed live
- the news thesis is the main driver and the news has not been refreshed
