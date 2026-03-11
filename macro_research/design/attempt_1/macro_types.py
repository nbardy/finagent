"""
Canonical domain types for macro research output.

Adapted from quant-ai-advisor's QuantState. These types encode the full
chain-of-thought research artifact: thesis, forecasts, macro facts, and
proposed trades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal
import json
from pathlib import Path
from datetime import datetime


# ---------------------------------------------------------------------------
# Forecast types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ForecastInterval:
    """One probability bucket mapping return range to input assumptions."""
    interval: tuple[float, float]   # e.g. (-0.30, -0.10)
    probability: float              # e.g. 0.35
    description: str                # WHICH INPUTS produce this return


@dataclass(frozen=True)
class Forecast:
    """Probabilistic return forecast for a time horizon."""
    horizon: str                    # "1m", "3m", "6m"
    intervals: list[ForecastInterval]
    logit_commentary: str = ""      # reasoning behind probability assignments
    notes: str = ""
    as_of: str = ""

    def expected_return(self) -> float:
        """Probability-weighted midpoint return."""
        return sum(
            ((lo + hi) / 2) * p
            for (lo, hi), p, _ in (
                (iv.interval, iv.probability, iv.description)
                for iv in self.intervals
            )
        )


# ---------------------------------------------------------------------------
# Thesis
# ---------------------------------------------------------------------------

class Confidence(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Thesis:
    """
    Investment thesis following INPUTS -> OUTPUT -> SENSITIVITY structure.
    The body must contain the model, not just an opinion.
    """
    title: str
    body: str                       # markdown with INPUTS/OUTPUT/SENSITIVITY
    time_horizon_months: int
    confidence: Confidence
    key_drivers: list[str]


# ---------------------------------------------------------------------------
# Macro facts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MacroFact:
    """One macro data point with provenance."""
    label: str
    detail: str
    source: str = ""
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Proposed trade
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptionLeg:
    type: Literal["call", "put"]
    strike: float
    expiration: str
    action: Literal["buy", "sell"]
    contracts: int = 1


@dataclass(frozen=True)
class ProposedTrade:
    """Structured trade recommendation with rationale."""
    ticker: str
    asset_type: Literal["stock", "option", "etf"]
    direction: Literal["long", "short"]
    thesis_summary: str
    description: str                # full markdown rationale

    options_strategy: str = ""      # e.g. "vertical-spread", "covered-call"
    legs: list[OptionLeg] = field(default_factory=list)

    stop_loss: str = ""
    profit_target: str = ""
    max_loss: str = ""
    risk_reward: str = ""
    position_size: str = ""
    timeframe: str = ""


# ---------------------------------------------------------------------------
# Full research artifact
# ---------------------------------------------------------------------------

@dataclass
class MacroResearchOutput:
    """Complete chain-of-thought research artifact written to disk."""
    thesis: Thesis
    macro_facts: list[MacroFact]
    forecasts: dict[str, Forecast]          # keyed by horizon: "1m", "3m", "6m"
    proposed_trades: list[ProposedTrade]
    chain_of_thought: str                   # raw CoT reasoning
    portfolio_context: dict | None = None   # snapshot of current portfolio
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    model: str = ""

    def save(self, output_dir: Path) -> None:
        """Write the full research artifact to a directory."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Main structured output
        structured = {
            "generated_at": self.generated_at,
            "model": self.model,
            "thesis": {
                "title": self.thesis.title,
                "body": self.thesis.body,
                "time_horizon_months": self.thesis.time_horizon_months,
                "confidence": self.thesis.confidence.value,
                "key_drivers": self.thesis.key_drivers,
            },
            "macro_facts": [
                {"label": f.label, "detail": f.detail, "source": f.source, "tags": f.tags}
                for f in self.macro_facts
            ],
            "forecasts": {
                horizon: {
                    "horizon": fc.horizon,
                    "intervals": [
                        {"interval": list(iv.interval), "probability": iv.probability, "description": iv.description}
                        for iv in fc.intervals
                    ],
                    "expected_return": round(fc.expected_return(), 4),
                    "logit_commentary": fc.logit_commentary,
                    "notes": fc.notes,
                }
                for horizon, fc in self.forecasts.items()
            },
            "proposed_trades": [
                {
                    "ticker": t.ticker,
                    "asset_type": t.asset_type,
                    "direction": t.direction,
                    "thesis_summary": t.thesis_summary,
                    "description": t.description,
                    "options_strategy": t.options_strategy,
                    "legs": [
                        {"type": l.type, "strike": l.strike, "expiration": l.expiration,
                         "action": l.action, "contracts": l.contracts}
                        for l in t.legs
                    ],
                    "stop_loss": t.stop_loss,
                    "profit_target": t.profit_target,
                    "risk_reward": t.risk_reward,
                    "timeframe": t.timeframe,
                }
                for t in self.proposed_trades
            ],
        }

        with open(output_dir / "research.json", "w") as f:
            json.dump(structured, f, indent=2)

        # Chain of thought (raw reasoning)
        (output_dir / "chain_of_thought.md").write_text(self.chain_of_thought)

        # Portfolio context if provided
        if self.portfolio_context:
            with open(output_dir / "portfolio_context.json", "w") as f:
                json.dump(self.portfolio_context, f, indent=2)

        # Human-readable summary
        summary = self._render_summary()
        (output_dir / "summary.md").write_text(summary)

    def _render_summary(self) -> str:
        lines = [
            f"# {self.thesis.title}",
            f"*Generated: {self.generated_at} | Confidence: {self.thesis.confidence.value} | Horizon: {self.thesis.time_horizon_months}mo*",
            "",
            "## Thesis",
            self.thesis.body,
            "",
            "## Key Drivers",
        ]
        for d in self.thesis.key_drivers:
            lines.append(f"- {d}")

        lines.append("")
        lines.append("## Macro Facts")
        for f in self.macro_facts:
            lines.append(f"- **{f.label}**: {f.detail} ({f.source})")

        for horizon, fc in self.forecasts.items():
            lines.append("")
            lines.append(f"## Forecast: {horizon}")
            lines.append(f"Expected return: {fc.expected_return():.1%}")
            lines.append("")
            lines.append("| Return Range | Probability | Scenario |")
            lines.append("|-------------|-------------|----------|")
            for iv in fc.intervals:
                lo, hi = iv.interval
                lines.append(f"| {lo:+.0%} to {hi:+.0%} | {iv.probability:.0%} | {iv.description} |")
            if fc.logit_commentary:
                lines.append(f"\n*Logit commentary: {fc.logit_commentary}*")

        if self.proposed_trades:
            lines.append("")
            lines.append("## Proposed Trades")
            for t in self.proposed_trades:
                lines.append(f"\n### {t.direction.upper()} {t.ticker} ({t.asset_type})")
                lines.append(t.description)
                if t.stop_loss:
                    lines.append(f"- Stop: {t.stop_loss}")
                if t.profit_target:
                    lines.append(f"- Target: {t.profit_target}")
                if t.risk_reward:
                    lines.append(f"- R:R: {t.risk_reward}")

        return "\n".join(lines)
