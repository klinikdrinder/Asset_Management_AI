from __future__ import annotations

from pathlib import Path
import unittest

from kdi_media.step6_inventory import (
    build_source_file_payloads,
    parse_step6_json,
)
from scripts.preview_step8_supabase import build_preview, preview_passes


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = (
    PROJECT_ROOT
    / "tmp"
    / "step6-recursive-scan"
    / "step6-recursive-20260729T090322Z.json"
)


class SupabasePreviewAggregationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        report = parse_step6_json(JSON_PATH)
        cls.rows = build_source_file_payloads(
            report,
            source_folder_id="source-folder-id",
            scan_run_id="scan-run-id",
        )
        for index, row in enumerate(cls.rows):
            row["id"] = f"row-{index}"

    def test_historical_rows_produce_expected_preview(self) -> None:
        preview = build_preview(self.rows)
        self.assertTrue(
            preview_passes(
                preview,
                expected_total=300,
                expected_changes=2,
            )
        )
        self.assertEqual(preview.changed, 2)
        self.assertEqual(preview.unchanged, 298)

    def test_duplicate_identity_is_detected(self) -> None:
        rows = [dict(self.rows[0]), dict(self.rows[0])]
        preview = build_preview(rows)
        self.assertEqual(preview.duplicate_identities, 1)

    def test_command_has_no_supabase_write_operations(self) -> None:
        script = (
            PROJECT_ROOT / "scripts" / "preview_step8_supabase.py"
        ).read_text(encoding="utf-8").lower()
        for prohibited in (
            ".table(",
            "store.insert",
            "store.update",
            "store.delete",
            "store.upsert",
            "record_migration_events(",
            "copy_file(",
        ):
            self.assertNotIn(prohibited, script)


if __name__ == "__main__":
    unittest.main()
