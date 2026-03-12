from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ROOT = REPO_ROOT / "automated_trading_strats"
DEFAULT_STRATEGY_TITLE = "Whale Wake Cross-Sectional Screener"
DEFAULT_STRATEGY_KEY = "whale_wake_cross_sectional_screener"


@dataclass(frozen=True)
class StrategyPaths:
    strategy_key: str
    strategy_dir: Path
    readme_path: Path
    strategy_path: Path
    manifest_path: Path
    runs_dir: Path
    logs_dir: Path
    cache_dir: Path


def slugify_strategy_key(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not slug:
        raise ValueError("Strategy key cannot be empty.")
    return slug


def ensure_strategy_workspace(strategy_key: str, root: Path = STRATEGY_ROOT) -> StrategyPaths:
    key = slugify_strategy_key(strategy_key)
    strategy_dir = root / key
    runs_dir = strategy_dir / "runs"
    logs_dir = strategy_dir / "logs"
    cache_dir = strategy_dir / "cache"

    strategy_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    return StrategyPaths(
        strategy_key=key,
        strategy_dir=strategy_dir,
        readme_path=strategy_dir / "README.md",
        strategy_path=strategy_dir / "strategy.md",
        manifest_path=strategy_dir / "strategy_manifest.json",
        runs_dir=runs_dir,
        logs_dir=logs_dir,
        cache_dir=cache_dir,
    )


def build_strategy_manifest(
    strategy_key: str,
    *,
    title: str,
    root: Path = STRATEGY_ROOT,
) -> dict[str, Any]:
    paths = ensure_strategy_workspace(strategy_key=strategy_key, root=root)
    return {
        "strategy_key": paths.strategy_key,
        "title": title,
        "created_for": "FinAgent",
        "status": "draft",
        "category": "automated_options_screening",
        "primary_artifact": paths.strategy_path.name,
        "tooling_hooks": {
            "python_module": "custom_scripts.automated_trading_strats",
            "inspect_signature": (
                "uv run python one_off_scripts/show_signature.py "
                "custom_scripts.automated_trading_strats save_strategy_note"
            ),
            "print_manifest": (
                "uv run python -m custom_scripts.automated_trading_strats "
                f"--strategy {paths.strategy_key} --print-manifest"
            ),
        },
    }


def save_strategy_note(
    strategy_key: str,
    *,
    title: str,
    body_markdown: str,
    overwrite: bool = False,
    root: Path = STRATEGY_ROOT,
) -> StrategyPaths:
    paths = ensure_strategy_workspace(strategy_key=strategy_key, root=root)

    if overwrite or not paths.readme_path.exists():
        paths.readme_path.write_text(
            (
                f"# {title}\n\n"
                "This strategy folder stores the thesis and minimal metadata for the strategy.\n\n"
                "Suggested local-only subpaths for future automation:\n\n"
                "- `runs/`\n"
                "- `logs/`\n"
                "- `cache/`\n"
            ),
            encoding="utf-8",
        )

    if overwrite or not paths.strategy_path.exists():
        paths.strategy_path.write_text(body_markdown.strip() + "\n", encoding="utf-8")

    manifest = build_strategy_manifest(strategy_key=paths.strategy_key, title=title, root=root)
    paths.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return paths


def list_saved_strategies(root: Path = STRATEGY_ROOT) -> tuple[str, ...]:
    if not root.exists():
        return ()
    strategy_keys = []
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        if (path / "strategy.md").exists():
            strategy_keys.append(path.name)
    return tuple(strategy_keys)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect saved automated trading strategy metadata.")
    parser.add_argument(
        "--strategy",
        default=DEFAULT_STRATEGY_KEY,
        help="Strategy key to inspect.",
    )
    parser.add_argument(
        "--print-manifest",
        action="store_true",
        help="Print the strategy manifest as JSON.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List tracked saved strategies.",
    )
    args = parser.parse_args()

    if args.list:
        print(json.dumps({"strategies": list_saved_strategies()}, indent=2))
        return

    paths = ensure_strategy_workspace(args.strategy)
    if args.print_manifest:
        if paths.manifest_path.exists():
            payload = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
        else:
            payload = build_strategy_manifest(args.strategy, title=DEFAULT_STRATEGY_TITLE)
        print(json.dumps(payload, indent=2))
        return

    print(json.dumps(asdict(paths), indent=2, default=str))


if __name__ == "__main__":
    main()
