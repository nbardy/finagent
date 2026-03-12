import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from custom_scripts.automated_trading_strats import (
    build_strategy_manifest,
    ensure_strategy_workspace,
    list_saved_strategies,
    save_strategy_note,
    slugify_strategy_key,
)
from custom_scripts.whale_wake_cross_sectional_screener import (
    build_scaffold_snapshot,
    write_scaffold_snapshot,
)


class AutomatedTradingStratsTests(unittest.TestCase):
    def test_slugify_strategy_key_normalizes_input(self) -> None:
        self.assertEqual(
            slugify_strategy_key(" Whale Wake Cross-Sectional Screener "),
            "whale_wake_cross_sectional_screener",
        )

    def test_ensure_strategy_workspace_creates_expected_paths(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            paths = ensure_strategy_workspace("Whale Wake", root=Path(tmp_dir))

            self.assertTrue(paths.strategy_dir.exists())
            self.assertTrue(paths.runs_dir.exists())
            self.assertTrue(paths.logs_dir.exists())
            self.assertTrue(paths.cache_dir.exists())

    def test_save_strategy_note_writes_strategy_and_manifest(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            paths = save_strategy_note(
                "Whale Wake",
                title="Whale Wake",
                body_markdown="# Thesis\n\nTrack cross-sectional signals.\n",
                root=Path(tmp_dir),
            )

            self.assertTrue(paths.strategy_path.exists())
            self.assertTrue(paths.manifest_path.exists())
            self.assertIn("Track cross-sectional signals.", paths.strategy_path.read_text(encoding="utf-8"))

            manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["strategy_key"], "whale_wake")
            self.assertEqual(manifest["title"], "Whale Wake")

    def test_list_saved_strategies_filters_for_tracked_strategy_dirs(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            save_strategy_note(
                "Whale Wake",
                title="Whale Wake",
                body_markdown="# Thesis\n",
                root=root,
            )
            (root / "scratch_only").mkdir()

            self.assertEqual(list_saved_strategies(root=root), ("whale_wake",))

    def test_build_strategy_manifest_includes_tooling_hooks(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            manifest = build_strategy_manifest(
                "Whale Wake",
                title="Whale Wake",
                root=Path(tmp_dir),
            )

            self.assertEqual(manifest["tooling_hooks"]["python_module"], "custom_scripts.automated_trading_strats")
            self.assertIn("--print-manifest", manifest["tooling_hooks"]["print_manifest"])

    def test_build_scaffold_snapshot_captures_expected_pipeline(self) -> None:
        snapshot = build_scaffold_snapshot(universe=("PLTR", "XBI"))

        self.assertEqual(snapshot["strategy_key"], "whale_wake_cross_sectional_screener")
        self.assertEqual(snapshot["config"]["universe"], ("PLTR", "XBI"))
        self.assertIn("rank_by_edge_ratio", snapshot["pipeline"])

    def test_write_scaffold_snapshot_persists_json(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "snapshot.json"
            written_path = write_scaffold_snapshot(output_path=str(output_path), universe=("PLTR",))

            self.assertEqual(written_path, output_path)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["config"]["universe"], ["PLTR"])


if __name__ == "__main__":
    unittest.main()
