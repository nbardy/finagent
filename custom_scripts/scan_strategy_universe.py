from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stratoforge.domain.contracts import ChainIndex, load_option_contracts
from stratoforge.domain.thesis import ThesisSchema
from stratoforge.grammar import active_grammars, generate_candidate_universe
from stratoforge.reporting import write_candidate_universe
from stratoforge.search.search_space import build_relevant_subchain, build_search_space


def _load_thesis(path: str | Path) -> ThesisSchema:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return ThesisSchema.from_dict(payload)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a thesis-driven options candidate universe for Stratoforge.",
    )
    parser.add_argument("--thesis", required=True, help="Path to thesis JSON.")
    parser.add_argument("--chain", required=True, help="Path to option chain JSON.")
    parser.add_argument(
        "--family",
        action="append",
        default=None,
        help="Optional family id filter. Repeat to include multiple.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. Defaults to analysis/{date}/stratoforge_{symbol}_{objective}.json",
    )
    args = parser.parse_args()

    thesis = _load_thesis(args.thesis)
    if args.family:
        thesis = ThesisSchema(
            symbol=thesis.symbol,
            asof_date=thesis.asof_date,
            spot=thesis.spot,
            objective=thesis.objective,
            branches=thesis.branches,
            constraints=thesis.constraints,
            allowed_families=tuple(args.family),
            notes=thesis.notes,
        )

    contracts = load_option_contracts(args.chain)
    full_chain = ChainIndex(contracts)
    search_space = build_search_space(thesis, full_chain)
    relevant_chain = build_relevant_subchain(thesis, full_chain, search_space)
    grammars = active_grammars(thesis)
    candidates = generate_candidate_universe(
        thesis=thesis,
        chain_index=relevant_chain,
        search_space=search_space,
        grammars=grammars,
    )
    json_path, md_path = write_candidate_universe(
        thesis=thesis,
        search_space=search_space,
        candidates=candidates,
        output_path=args.output,
    )

    print(f"Generated {len(candidates)} candidates across {len(grammars)} families.")
    print(f"JSON: {json_path}")
    print(f"Summary: {md_path}")


if __name__ == "__main__":
    main()
