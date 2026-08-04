from __future__ import annotations

from pathlib import Path
import unittest

from kdi_media.rules import ReasonCode
from kdi_media.step6_inventory import parse_step6_json
from scripts.preview_step8_decisions import preview_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = (
    PROJECT_ROOT
    / "tmp"
    / "step6-recursive-scan"
    / "step6-recursive-20260729T090322Z.json"
)


class Step8HistoricalPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = parse_step6_json(JSON_PATH)
        cls.preview = preview_report(cls.report)

    def test_preview_reconciles_to_292_take_and_8_skip(self) -> None:
        self.assertEqual(self.preview.total_file_records, 300)
        self.assertEqual(self.preview.take_count, 292)
        self.assertEqual(self.preview.skip_count, 8)
        self.assertEqual(self.preview.folder_items_excluded, 38)

    def test_exactly_pdf_and_pptx_change_to_take(self) -> None:
        self.assertEqual(len(self.preview.differences), 2)
        self.assertEqual(
            {difference.extension for difference in self.preview.differences},
            {"pdf", "pptx"},
        )
        for difference in self.preview.differences:
            self.assertEqual(
                difference.previous_classification, "unsupported_file"
            )
            self.assertEqual(difference.proposed_decision, "TAKE")
            self.assertEqual(
                difference.reason_code, ReasonCode.SUPPORTED_FORMAT.value
            )
            self.assertFalse(difference.accepted_for_ai_analysis)

    def test_unsupported_reason_distribution(self) -> None:
        reasons = dict(self.preview.reasons)
        self.assertEqual(reasons[ReasonCode.SUPPORTED_FORMAT.value], 292)
        self.assertEqual(reasons[ReasonCode.GOOGLE_NATIVE_FILE.value], 6)
        self.assertEqual(reasons[ReasonCode.UNSUPPORTED_EXTENSION.value], 2)

    def test_no_folder_is_a_source_file_decision(self) -> None:
        decision_total = sum(count for _, count in self.preview.decisions)
        self.assertEqual(decision_total, 300)
        self.assertNotIn(
            ReasonCode.FOLDER_ITEM.value, dict(self.preview.reasons)
        )

    def test_preview_module_has_no_asset_logic(self) -> None:
        script = (
            PROJECT_ROOT / "scripts" / "preview_step8_decisions.py"
        ).read_text(encoding="utf-8").lower()
        self.assertNotIn("asset_sources", script)
        self.assertNotIn(".table(", script)
        self.assertNotIn("create_client", script)


if __name__ == "__main__":
    unittest.main()
