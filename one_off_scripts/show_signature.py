from __future__ import annotations

import argparse
import importlib
import inspect
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _resolve_attr(module: ModuleType, attr_path: str):
    value = module
    for part in attr_path.split("."):
        value = getattr(value, part)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a symbol signature from a module in this repo."
    )
    parser.add_argument("module", help="Python module path, e.g. ibkr")
    parser.add_argument(
        "symbol",
        help="Attribute path inside the module, e.g. connect or OptionQuote.has_market",
    )
    args = parser.parse_args()

    module = importlib.import_module(args.module)
    value = _resolve_attr(module, args.symbol)

    print(f"{args.module}.{args.symbol}")

    try:
        print(inspect.signature(value))
    except (TypeError, ValueError):
        print("<no callable signature available>")

    doc = inspect.getdoc(value)
    if doc:
        print()
        print(doc)


if __name__ == "__main__":
    main()
