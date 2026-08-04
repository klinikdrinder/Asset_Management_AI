from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import json
import tempfile
import unittest

from kdi_media.step6_inventory import (
    INACCESSIBLE_ITEM_CLASSIFICATION,
    Step6InventoryValidationError,
    build_scan_run_payload,
    build_source_file_payloads,
    calculate_report_sha256,
    cross_validate_step6_csv,
    parse_step6_json,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = (
    PROJECT_ROOT
    / "tmp"
    / "step6-recursive-scan"
    / "step6-recursive-20260729T090322Z.json"
)
CSV_PATH = (
    PROJECT_ROOT
    / "tmp"
    / "step6-recursive-scan"
    / "step6-recursive-20260729T090322Z.csv"
)
ROOT_ID = "1kYX3KIEFkerRMrTvZk2zPpVaFQoCLE4v"
ROOT_NAME = "ALL PATIENT REVIEW"


class Step6InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = parse_step6_json(
            JSON_PATH,
            expected_root_id=ROOT_ID,
            expected_root_name=ROOT_NAME,
        )
        cls.payloads = build_source_file_payloads(
            cls.report,
            source_folder_id="source-folder-id",
            scan_run_id="scan-run-id",
        )

    def test_valid_json_parsing_and_exact_totals(self) -> None:
        summary = self.report.summary
        self.assertEqual(self.report.root.file_id, ROOT_ID)
        self.assertEqual(self.report.root.name, ROOT_NAME)
        self.assertEqual(summary.folders_scanned, 39)
        self.assertEqual(summary.total_items_discovered, 338)
        self.assertEqual(summary.total_files_found, 300)
        self.assertEqual(summary.supported_files, 290)
        self.assertEqual(summary.unsupported_files, 10)
        self.assertEqual(summary.inaccessible_items, 0)
        self.assertEqual(summary.errors, 0)

    def test_valid_csv_cross_validation(self) -> None:
        cross_validate_step6_csv(self.report, CSV_PATH)

    def test_root_folder_id_validation(self) -> None:
        with self.assertRaisesRegex(
            Step6InventoryValidationError, "root folder ID"
        ):
            parse_step6_json(JSON_PATH, expected_root_id="wrong-folder")

    def test_root_folder_name_validation(self) -> None:
        with self.assertRaisesRegex(
            Step6InventoryValidationError, "root folder name"
        ):
            parse_step6_json(JSON_PATH, expected_root_name="Wrong name")

    def test_folders_are_excluded_and_file_payload_count_is_exact(self) -> None:
        self.assertEqual(len(self.report.folder_items), 38)
        self.assertEqual(len(self.payloads), 300)
        folder_ids = {item.file_id for item in self.report.folder_items}
        self.assertTrue(
            folder_ids.isdisjoint(
                payload["google_file_id"] for payload in self.payloads
            )
        )

    def test_supported_and_unsupported_mappings(self) -> None:
        supported = [
            value
            for value in self.payloads
            if value["metadata"]["step6_classification"] == "supported_file"
        ]
        unsupported = [
            value
            for value in self.payloads
            if value["metadata"]["step6_classification"]
            == "unsupported_file"
        ]
        self.assertEqual(len(supported), 290)
        self.assertEqual(len(unsupported), 10)
        self.assertTrue(
            all(
                value["decision"] == "TAKE"
                and value["processing_status"] == "READY"
                for value in supported
            )
        )
        self.assertTrue(
            all(
                value["decision"] == "SKIP"
                and value["processing_status"] == "SKIPPED"
                and value["skip_reason"]
                for value in unsupported
            )
        )

    def test_pptx_remains_unsupported_from_report_classification(self) -> None:
        pptx = [
            value
            for value in self.payloads
            if (value["file_extension"] or "").lower() == "pptx"
        ]
        self.assertEqual(len(pptx), 1)
        self.assertEqual(pptx[0]["decision"], "SKIP")
        self.assertEqual(pptx[0]["processing_status"], "SKIPPED")
        self.assertEqual(
            pptx[0]["metadata"]["step6_classification"],
            "unsupported_file",
        )

    def test_google_native_files_remain_unsupported(self) -> None:
        google_native = [
            value
            for value in self.payloads
            if value["mime_type"].startswith("application/vnd.google-apps.")
        ]
        self.assertTrue(google_native)
        self.assertTrue(
            all(
                value["decision"] == "SKIP"
                and value["processing_status"] == "SKIPPED"
                for value in google_native
            )
        )

    def test_inaccessible_item_mapping(self) -> None:
        raw = self._raw_report()
        item = next(
            value
            for value in raw["items"]
            if value["classification"] == "unsupported_file"
        )
        item["classification"] = INACCESSIBLE_ITEM_CLASSIFICATION
        item["accessibility_status"] = "inaccessible"
        raw["summary"]["unsupported_files"] -= 1
        raw["summary"]["inaccessible_items"] += 1
        report = self._parse_temporary(raw)
        payload = next(
            value
            for value in build_source_file_payloads(
                report,
                source_folder_id="source-folder-id",
                scan_run_id="scan-run-id",
            )
            if value["google_file_id"] == item["file_id"]
        )
        self.assertEqual(payload["decision"], "PENDING")
        self.assertEqual(payload["processing_status"], "INACCESSIBLE")

    def test_malformed_size_is_rejected(self) -> None:
        raw = self._raw_report()
        raw["items"][0]["size"] = "not-an-integer"
        with self.assertRaisesRegex(
            Step6InventoryValidationError, "non-negative integer"
        ):
            self._parse_temporary(raw)

    def test_malformed_timestamp_is_rejected(self) -> None:
        raw = self._raw_report()
        raw["items"][0]["modified_time"] = "not-a-timestamp"
        with self.assertRaisesRegex(
            Step6InventoryValidationError, "ISO-8601"
        ):
            self._parse_temporary(raw)

    def test_unknown_classification_is_rejected(self) -> None:
        raw = self._raw_report()
        raw["items"][0]["classification"] = "new-unapproved-class"
        with self.assertRaisesRegex(
            Step6InventoryValidationError, "Unknown classification"
        ):
            self._parse_temporary(raw)

    def test_json_csv_mismatch_is_rejected(self) -> None:
        with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
            fieldnames = list(rows[0])
        rows[0]["classification"] = "unsupported_file"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mismatch.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(
                Step6InventoryValidationError, "JSON and CSV differ"
            ):
                cross_validate_step6_csv(self.report, path)

    def test_summary_item_count_mismatch_is_rejected(self) -> None:
        raw = self._raw_report()
        raw["summary"]["supported_files"] -= 1
        with self.assertRaisesRegex(
            Step6InventoryValidationError, "summary field supported_files"
        ):
            self._parse_temporary(raw)

    def test_report_sha256_is_stable(self) -> None:
        expected = hashlib.sha256(JSON_PATH.read_bytes()).hexdigest()
        self.assertEqual(calculate_report_sha256(JSON_PATH), expected)
        self.assertEqual(self.report.report_sha256, expected)
        self.assertEqual(calculate_report_sha256(JSON_PATH), expected)

    def test_neutral_fields_and_no_invented_migration_information(self) -> None:
        prohibited = {
            "asset_id",
            "content_hash",
            "destination_file_id",
            "destination_web_view_link",
            "uploaded_at",
            "duplicate_of_source_file_id",
        }
        for payload in self.payloads:
            self.assertIsNone(payload["md5_checksum"])
            self.assertIsNone(payload["thumbnail_link"])
            self.assertFalse(payload["trashed"])
            self.assertFalse(payload["is_missing"])
            self.assertTrue(prohibited.isdisjoint(payload))

    def test_last_seen_uses_report_generation_timestamp(self) -> None:
        self.assertTrue(
            all(
                payload["last_seen_at"] == self.report.generated_at_utc
                for payload in self.payloads
            )
        )

    def test_scan_run_payload_has_required_counts_and_metadata(self) -> None:
        payload = build_scan_run_payload(
            self.report, source_folder_id="source-folder-id"
        )
        self.assertEqual(payload["run_mode"], "DRY_RUN")
        self.assertEqual(payload["status"], "RUNNING")
        self.assertEqual(payload["files_discovered"], 300)
        self.assertEqual(payload["files_taken"], 290)
        self.assertEqual(payload["files_skipped"], 10)
        self.assertEqual(payload["files_uploaded"], 0)
        self.assertEqual(payload["duplicates_found"], 0)
        self.assertEqual(payload["files_failed"], 0)
        self.assertEqual(
            payload["metadata"]["import_type"], "STEP6_INVENTORY"
        )
        self.assertEqual(
            payload["metadata"]["report_sha256"],
            self.report.report_sha256,
        )

    @staticmethod
    def _raw_report() -> dict[str, object]:
        return json.loads(JSON_PATH.read_text(encoding="utf-8"))

    def _parse_temporary(self, raw: dict[str, object]):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            return parse_step6_json(
                path,
                expected_root_id=ROOT_ID,
                expected_root_name=ROOT_NAME,
            )


if __name__ == "__main__":
    unittest.main()
