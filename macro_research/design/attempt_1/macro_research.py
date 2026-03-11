"""
Macro thesis research generator.

Runs Claude to produce N independent macro theses with chain-of-thought
reasoning, probabilistic forecasts, and trade proposals. Writes structured
output to:

    macro_research/day_{mon_dd_yyyy}/{HH_MM_SS}_{uuid}/
        research.json        — full structured output
        chain_of_thought.md  — raw CoT reasoning
        portfolio_context.json — portfolio snapshot (if provided)
        summary.md           — human-readable summary

Usage:
    uv run python macro_research.py
    uv run python macro_research.py --focus "rates and duration"
    uv run python macro_research.py --theses 5
    uv run python macro_research.py --portfolio config/portfolio_state.json
    uv run python macro_research.py --model claude-sonnet-4-6
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

import anthropic

from macro_prompts import build_research_prompt
from macro_types import (
    Confidence,
    Forecast,
    ForecastInterval,
    MacroFact,
    MacroResearchOutput,
    OptionLeg,
    ProposedTrade,
    Thesis,
)


def make_output_dir() -> Path:
    """Create the output directory following the naming convention."""
    now = datetime.now()
    day_str = now.strftime("day_%b_%d_%Y").lower()
    time_str = now.strftime("%H_%M_%S")
    run_id = uuid.uuid4().hex[:8]
    output_dir = Path("macro_research") / day_str / f"{time_str}_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def load_portfolio(path: str | None) -> dict | None:
    """Load portfolio context from JSON file."""
    if path is None:
        # Try default location
        default = Path("config/portfolio_state.json")
        if default.exists():
            with open(default) as f:
                return json.load(f)
        return None
    with open(path) as f:
        return json.load(f)


def call_claude(prompt: str, model: str) -> str:
    """Call Claude API and return the response text."""
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=16384,
        messages=[{"role": "user", "content": prompt}],
    )
    block = message.content[0]
    assert hasattr(block, "text"), f"Expected TextBlock, got {type(block).__name__}"
    return block.text


def extract_json(text: str) -> dict:
    """Extract JSON from Claude's response, handling markdown fences."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)

    # Try extracting from markdown code fence
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError(f"Could not extract JSON from response:\n{text[:500]}...")


def parse_response(raw: dict, model: str, portfolio: dict | None) -> list[MacroResearchOutput]:
    """Parse Claude's JSON response into MacroResearchOutput objects."""
    chain_of_thought = raw.get("chain_of_thought", "")
    outputs = []

    for thesis_data in raw["theses"]:
        thesis = Thesis(
            title=thesis_data["title"],
            body=thesis_data["body"],
            time_horizon_months=thesis_data["time_horizon_months"],
            confidence=Confidence(thesis_data["confidence"]),
            key_drivers=thesis_data["key_drivers"],
        )

        macro_facts = [
            MacroFact(
                label=f["label"],
                detail=f["detail"],
                source=f.get("source", ""),
                tags=f.get("tags", []),
            )
            for f in thesis_data.get("macro_facts", [])
        ]

        forecasts = {}
        for horizon, fc_data in thesis_data.get("forecasts", {}).items():
            intervals = [
                ForecastInterval(
                    interval=tuple(iv["interval"]),
                    probability=iv["probability"],
                    description=iv["description"],
                )
                for iv in fc_data["intervals"]
            ]
            forecasts[horizon] = Forecast(
                horizon=horizon,
                intervals=intervals,
                logit_commentary=fc_data.get("logit_commentary", ""),
                notes=fc_data.get("notes", ""),
                as_of=datetime.now().isoformat(),
            )

        proposed_trades = []
        for t in thesis_data.get("proposed_trades", []):
            legs = [
                OptionLeg(
                    type=l["type"],
                    strike=l["strike"],
                    expiration=l["expiration"],
                    action=l["action"],
                    contracts=l.get("contracts", 1),
                )
                for l in t.get("legs", [])
            ]
            proposed_trades.append(ProposedTrade(
                ticker=t["ticker"],
                asset_type=t["asset_type"],
                direction=t["direction"],
                thesis_summary=t["thesis_summary"],
                description=t["description"],
                options_strategy=t.get("options_strategy", ""),
                legs=legs,
                stop_loss=t.get("stop_loss", ""),
                profit_target=t.get("profit_target", ""),
                max_loss=t.get("max_loss", ""),
                risk_reward=t.get("risk_reward", ""),
                position_size=t.get("position_size", ""),
                timeframe=t.get("timeframe", ""),
            ))

        outputs.append(MacroResearchOutput(
            thesis=thesis,
            macro_facts=macro_facts,
            forecasts=forecasts,
            proposed_trades=proposed_trades,
            chain_of_thought=chain_of_thought,
            portfolio_context=portfolio,
            model=model,
        ))

    return outputs


def run(
    *,
    focus: str = "",
    num_theses: int = 3,
    portfolio_path: str | None = None,
    model: str = "claude-sonnet-4-6",
) -> Path:
    """Run macro research generation and write output to disk."""
    portfolio = load_portfolio(portfolio_path)
    portfolio_json = json.dumps(portfolio, indent=2) if portfolio else None

    prompt = build_research_prompt(
        portfolio_json=portfolio_json,
        focus=focus,
        num_theses=num_theses,
    )

    print(f"Generating {num_theses} macro theses with {model}...")
    if portfolio:
        print(f"  Portfolio context: {len(portfolio.get('unencumbered_leaps', []))} positions loaded")
    if focus:
        print(f"  Focus: {focus}")

    response_text = call_claude(prompt, model)
    raw = extract_json(response_text)
    outputs = parse_response(raw, model, portfolio)

    base_dir = make_output_dir()

    for i, output in enumerate(outputs):
        thesis_dir = base_dir / f"thesis_{i+1}_{_slugify(output.thesis.title)}"
        output.save(thesis_dir)
        print(f"\n  [{i+1}] {output.thesis.title}")
        print(f"      Confidence: {output.thesis.confidence.value}")
        print(f"      Trades: {len(output.proposed_trades)}")
        for horizon, fc in output.forecasts.items():
            print(f"      E[R] {horizon}: {fc.expected_return():+.1%}")
        print(f"      -> {thesis_dir}")

    # Write an index file linking all theses
    index = {
        "generated_at": datetime.now().isoformat(),
        "model": model,
        "focus": focus,
        "num_theses": len(outputs),
        "theses": [
            {
                "title": o.thesis.title,
                "confidence": o.thesis.confidence.value,
                "dir": str(Path(f"thesis_{i+1}_{_slugify(o.thesis.title)}")),
                "forecasts": {
                    h: round(fc.expected_return(), 4)
                    for h, fc in o.forecasts.items()
                },
                "trades": [t.ticker for t in o.proposed_trades],
            }
            for i, o in enumerate(outputs)
        ],
    }
    with open(base_dir / "index.json", "w") as f:
        json.dump(index, f, indent=2)

    print(f"\n  Index: {base_dir / 'index.json'}")
    print(f"  Done. Output: {base_dir}")
    return base_dir


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug[:50]


def main():
    parser = argparse.ArgumentParser(
        description="Generate macro research theses with Claude",
    )
    parser.add_argument("--focus", default="", help="Research focus area (e.g. 'rates and duration')")
    parser.add_argument("--theses", type=int, default=3, help="Number of theses to generate")
    parser.add_argument("--portfolio", default=None, help="Portfolio JSON file (default: config/portfolio_state.json if exists)")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Claude model to use")
    args = parser.parse_args()

    run(
        focus=args.focus,
        num_theses=args.theses,
        portfolio_path=args.portfolio,
        model=args.model,
    )


if __name__ == "__main__":
    main()
