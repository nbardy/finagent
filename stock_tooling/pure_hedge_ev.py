import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stock_tooling.portfolio_scenario_ev import run_cli


if __name__ == "__main__":
    run_cli(default_mode="pure-hedge")
