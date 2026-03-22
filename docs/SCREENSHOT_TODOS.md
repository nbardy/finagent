# Screenshots to capture for README

Save screenshots to `docs/screenshots/` as PNG. Use a clean terminal with dark background.

## 1. Thesis-driven pricing (hero screenshot)

**Query:**
> I think the Iran war will cause a 5% pullback in SPY over 2 weeks. 20% chance of a 10% crash, 30% chance it resolves early with a 2% bounce. Price me some put spreads.

**What to capture:** The agent building the thesis, calibrating models, and returning ranked candidates with EV/max-loss table.

**File:** `docs/screenshots/thesis_pricing.png`

## 2. Portfolio overview

**Query:**
> Show me my current portfolio with P&L breakdown by position.

**What to capture:** The formatted portfolio table with multi-currency positions, unrealized P&L, and account summary.

**File:** `docs/screenshots/portfolio_overview.png`

## 3. Hedge comparison

**Query:**
> I need crash protection. Compare put spreads, calendars, and long puts on SPY assuming a 7% drawdown over 5 days.

**What to capture:** The book/hedge/combined comparison table with return-on-hedge-capital for each candidate.

**File:** `docs/screenshots/hedge_comparison.png`

## 4. Order execution

**Query:**
> Submit the trade proposal from today's analysis.

**What to capture:** The agent reading the proposal JSON, showing the order summary, and confirming submission with fill prices.

**File:** `docs/screenshots/order_execution.png`

## 5. Signature inspection

**Command:**
```bash
uv run python one_off_scripts/show_signature.py ibkr get_open_orders
```

**What to capture:** The typed signature output showing the agent-readable function interface.

**File:** `docs/screenshots/signature_inspection.png`

## 6. Stratoforge strategy search

**Query:**
> Run a full strategy search for SPY using my bullish thesis from yesterday. Show me the top 10 candidates.

**What to capture:** The scored candidate universe with strategy family, strikes, expiries, and EV ranking.

**File:** `docs/screenshots/stratoforge_search.png`

## Adding to README

Once captured, add to README.md after the description:

```markdown
![Thesis-driven option pricing](docs/screenshots/thesis_pricing.png)
```
