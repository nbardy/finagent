# Sources And Web Lookup Policy
**Date:** 2026-03-12
**Scope:** What had to be looked up live in this thread and what is now encoded as reusable policy.

## What Required Live External Lookup

### Market state
- current EWY quote
- current EWY option chains
- current AAOI quote and option chains

### Macro/news state
- Iran escalation / mines / oil risk reporting

### Event-window validation
- Samsung earnings timing

### Exposure validation
- EWY holdings and Samsung weight

### Broker / strategy mechanics
- IBKR assignment and margin behavior
- OIC / Fidelity strategy references for mechanics and terminology

## What Is Encoded Now

This is now captured as policy in:
- `.codex/skills/references/source_playbook.md`

That file encodes:
- source priority
- execution vs research source rules
- what facts must still be refreshed live
- when to stop instead of inventing inputs

## What Skills Can Replace

Skills can replace repeated process like:
- "check issuer IR first for event dates"
- "use IBKR for executable pricing"
- "public chains are okay for rough structure ranking only"
- "report source metadata in analysis"

## What Skills Cannot Replace

Skills cannot replace:
- today’s price
- today’s option chain
- today’s news
- today’s earnings confirmation
- today’s ETF weight table

## Practical Rule

For this repo:
- use skills to encode lookup behavior
- use live sources to get the facts

That means we still need internet or broker lookups whenever the answer is time-sensitive.
