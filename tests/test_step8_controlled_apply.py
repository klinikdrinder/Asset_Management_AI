from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import unittest

from kdi_media.step6_inventory import (
    build_source_file_payloads,
    parse_step6_json,
)
from scripts.apply_step8_approved_documents import (
    ControlledApplyError,
    build_apply_plan,
    reconciliation_passes,
)
from scripts.preview_step8_supabase import build_preview


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = (
    PROJECT_ROOT
    / "tmp"
    / "step6-recursive-scan"
    / "step6-recursive-20260729T090322Z.json"
)
SOURCE_FOLDER_ID = "42affe18-4e7b-4333-87fe-7158c410c072"


def historical_rows() -> list[dict[str, object]]:
    report = parse_step6_json(JSON_PATH)
    rows = build_source_file_payloads(
        report,
        source_folder_id=SOURCE_FOLDER_ID,
        scan_run_id="scan-run-id",
    )
    for index, row in enumerate(rows):
        row["id"] = f"row-{index}"
    return rows


class ControlledApplyPlanTests(unittest.TestCase):
    def test_preflight_selects_exactly_two_approved_rows(self) -> None:
        plan = build_apply_plan(
            historical_rows(),
            source_folder_id=SOURCE_FOLDER_ID,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.assertEqual(plan.mode, "APPLY")
        self.assertEqual(len(plan.source_file_ids), 2)
        self.assertEqual(plan.merged_metadata["step8_rule_version"], "step8.v1")
        self.assertFalse(
            plan.merged_metadata["accepted_for_ai_analysis"]
        )

    def test_mixed_state_fails_before_apply(self) -> None:
        rows = historical_rows()
        pdf = next(
            row
            for row in rows
            if str(row.get("file_extension", "")).lower() == "pdf"
        )
        pdf["decision"] = "TAKE"
        pdf["processing_status"] = "READY"
        with self.assertRaisesRegex(ControlledApplyError, "mixed"):
            build_apply_plan(
                rows,
                source_folder_id=SOURCE_FOLDER_ID,
                evaluated_at=datetime.now(timezone.utc).isoformat(),
            )

    def test_idempotent_state_produces_no_change_plan(self) -> None:
        rows = historical_rows()
        for row in rows:
            extension = str(row.get("file_extension", "")).lower()
            if extension in {"pdf", "pptx"}:
                row["decision"] = "TAKE"
                row["processing_status"] = "READY"
                row["skip_reason"] = None
                row["metadata"] = {
                    **dict(row["metadata"]),
                    "step8_rule_version": "step8.v1",
                    "step8_reason_code": "SUPPORTED_FORMAT",
                    "accepted_for_ai_analysis": False,
                    "step8_evaluated_at": "2026-07-30T00:00:00+00:00",
                }
        plan = build_apply_plan(
            rows,
            source_folder_id=SOURCE_FOLDER_ID,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.assertEqual(plan.mode, "NO_CHANGE")
        preview = build_preview(rows)
        self.assertTrue(reconciliation_passes(preview, expected_total=300))

    def test_metadata_mismatch_prevents_single_statement_apply(self) -> None:
        rows = historical_rows()
        pdf = next(
            row
            for row in rows
            if str(row.get("file_extension", "")).lower() == "pdf"
        )
        pdf["metadata"] = {**deepcopy(pdf["metadata"]), "different": True}
        with self.assertRaisesRegex(ControlledApplyError, "metadata"):
            build_apply_plan(
                rows,
                source_folder_id=SOURCE_FOLDER_ID,
                evaluated_at=datetime.now(timezone.utc).isoformat(),
            )

    def test_apply_script_has_no_forbidden_systems(self) -> None:
        script = (
            PROJECT_ROOT / "scripts" / "apply_step8_approved_documents.py"
        ).read_text(encoding="utf-8").lower()
        for prohibited in (
            "record_migration_events(",
            "copy_file(",
            '.table("assets")',
            '.table("asset_sources")',
            "destination_file_id",
            "first_seen_at",
            "last_seen_at",
            "googleapiclient",
        ):
            self.assertNotIn(prohibited, script)


if __name__ == "__main__":
    unittest.main()
