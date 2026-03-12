import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from executor import _build_submission_context
from helpers.thesis_db import (
    build_order_ref,
    ensure_schema,
    find_thesis_for_order,
    find_thesis_for_position,
    record_order_event,
    upsert_thesis,
)


class ThesisDbTests(unittest.TestCase):
    def test_upsert_thesis_requires_descriptive_reason(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "thesis.db"
            with self.assertRaises(ValueError):
                upsert_thesis(
                    symbol="PLTR",
                    sec_type="STK",
                    reason="too short",
                    db_path=db_path,
                )

    def test_upsert_and_lookup_position_thesis(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "thesis.db"
            record = upsert_thesis(
                symbol="PLTR",
                sec_type="OPT",
                expiry="20260417",
                strike=120,
                right="C",
                strategy="whale_wake",
                intent="add",
                reason="Volume-weighted persistence remains strong and the option is underpriced versus model value.",
                db_path=db_path,
            )

            found = find_thesis_for_position(
                symbol="PLTR",
                sec_type="OPT",
                expiry="20260417",
                strike=120,
                right="C",
                db_path=db_path,
            )

            self.assertIsNotNone(found)
            self.assertEqual(found["thesis_id"], record.thesis_id)
            self.assertEqual(found["strategy"], "whale_wake")

    def test_order_event_lookup_prefers_perm_id(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "thesis.db"
            ensure_schema(db_path)
            record = upsert_thesis(
                symbol="EWY",
                sec_type="OPT",
                expiry="20270115",
                strike=145,
                right="C",
                reason="Holding this LEAP because the macro thesis remains intact and the risk budget still supports it.",
                db_path=db_path,
            )
            record_order_event(
                thesis_id=record.thesis_id,
                order_ref=record.order_ref,
                perm_id=12345,
                order_id=678,
                symbol="EWY",
                sec_type="OPT",
                expiry="20270115",
                strike=145,
                right="C",
                action="BUY",
                quantity=2,
                db_path=db_path,
            )

            found = find_thesis_for_order(
                perm_id=12345,
                order_ref=None,
                symbol="EWY",
                sec_type="OPT",
                expiry="20270115",
                strike=145,
                right="C",
                db_path=db_path,
            )
            self.assertEqual(found["thesis_id"], record.thesis_id)

    def test_executor_submission_context_requires_reason_and_sets_order_ref(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "thesis.db"
            proposal = {
                "intent": "add",
                "strategy": "whale_wake",
                "reason": "Buying this position because the cross-sectional signal and volume-weighted persistence both support the entry.",
                "contract": {
                    "symbol": "PLTR",
                    "secType": "OPT",
                    "exchange": "SMART",
                    "currency": "USD",
                    "lastTradeDateOrContractMonth": "20260417",
                    "strike": 120.0,
                    "right": "C",
                },
                "action": "BUY",
                "tranches": [{"tranche": 1, "quantity": 1, "lmtPrice": 1.25}],
            }

            thesis = _build_submission_context(proposal, source_file="orders/test.json", db_path=db_path)

            self.assertTrue(proposal["thesis_id"].startswith("th-"))
            self.assertEqual(proposal["orderRef"], thesis.order_ref)
            self.assertIn("th:", proposal["orderRef"])

    def test_build_order_ref_appends_short_thesis_pointer(self) -> None:
        ref = build_order_ref("th-20260312-160000-pltr-deadbeef", "PLTR", "wake_scan")
        self.assertTrue(ref.startswith("wake_scan|th:PLTR:"))


if __name__ == "__main__":
    unittest.main()
