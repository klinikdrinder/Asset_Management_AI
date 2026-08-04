from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from kdi_media.step10_b3 import (
    B3Options,
    B3Orchestrator,
    B3SafetyError,
    BLOCKED_VERDICT,
    MANUAL_VERDICT,
    READY_VERDICT,
    reconcile_final,
    select_controlled_rows,
)


ROOT = "1CdmowWV5TAk5R9D5yl2cOT8Plx3ihZgl"
SCRIPT = Path("scripts/run_step10_b3_database_dry_run.py")
HASH = "a" * 64


def fixture_inputs(count=3):
    assets, links, sources = [], [], []
    for index in range(count):
        asset_id = str(UUID(int=index + 1))
        source_id = str(UUID(int=100 + index))
        assets.append(
            {
                "id": asset_id,
                "content_hash": HASH,
                "metadata": {"canonical_source_file_id": source_id},
            }
        )
        links.append({"asset_id": asset_id, "source_file_id": source_id})
        sources.append(
            {
                "id": source_id,
                "source_folder_id": str(UUID(int=200 + index)),
                "google_file_id": f"google-{index}",
                "file_name": f"private-{index}.jpg",
                "mime_type": "image/jpeg",
                "file_extension": "jpg",
                "size_bytes": 10 + index,
                "decision": "TAKE",
                "processing_status": "READY",
                "hash_status": "HASHED",
                "hash_algorithm": "SHA-256",
                "content_sha256": HASH,
                "hash_drive_modified_at": "2026-07-30T00:00:00Z",
                "hash_drive_version": str(index + 1),
                "hash_completed_at": "2026-07-30T00:01:00Z",
            }
        )
    return assets, links, sources


class FakeDatabase:
    def __init__(self, count=3):
        self.assets, self.links, self.sources = fixture_inputs(count)
        self.rows = []
        self.events = []
        self.calls = []
        self.fail_at = None
        self.restore_fails = False

    def require_schema(self):
        self.calls.append("schema")

    def canonical_inputs(self):
        return deepcopy((self.assets, self.links, self.sources))

    def list_destinations(self):
        return deepcopy(self.rows)

    def initialize(self, values):
        inserted = []
        for value in values:
            if not any(row["id"] == value["id"] for row in self.rows):
                row = deepcopy(value)
                row["destination_google_file_id"] = None
                row["claim_owner"] = None
                row["claim_started_at"] = None
                row["claim_expires_at"] = None
                row["claim_renewed_at"] = None
                row["upload_completed_at"] = None
                row["verified_at"] = None
                row["created_at"] = "2026-07-31T00:00:00Z"
                self.rows.append(row)
                inserted.append(deepcopy(row))
                self.events.append(
                    {
                        "asset_id": row["asset_id"],
                        "asset_destination_id": row["id"],
                        "event_type": "LIFECYCLE_INITIALIZED",
                        "event_status": "SUCCESS",
                        "details": {"verification_level": "SOURCE_HASH_VERIFIED"},
                    }
                )
        return inserted

    def claim(self, owner, limit, allowed_ids, destination_folder_id):
        if self.fail_at == "claim":
            raise RuntimeError("synthetic claim failure")
        allowed = None if allowed_ids is None else set(allowed_ids)
        claimed = []
        for row in sorted(self.rows, key=lambda value: value["id"]):
            if len(claimed) >= limit:
                break
            if row["destination_folder_id"] != destination_folder_id:
                continue
            if allowed is not None and row["id"] not in allowed:
                continue
            active = bool(row.get("claim_owner")) and not row.get("_expired")
            if active:
                continue
            if row["upload_status"] in {
                "VERIFIED", "FAILED_PERMANENT", "UPLOADED"
            }:
                continue
            previous = row["upload_status"]
            row["upload_status"] = "CLAIMED"
            row["claim_owner"] = owner
            row["claim_started_at"] = "2026-07-31T00:00:00Z"
            row["claim_expires_at"] = "2026-07-31T00:02:00Z"
            row["upload_attempt_count"] += 1
            row["_expired"] = False
            claimed.append(deepcopy(row))
            if previous == "CLAIMED":
                self.events.append(self._event(row, "CLAIM_RECOVERED"))
        self.calls.append(("claim", None if allowed is None else len(allowed)))
        return claimed

    def renew(self, row_id, owner, lease_seconds):
        row = self._row(row_id)
        if row.get("claim_owner") != owner or row.get("_expired"):
            return False
        row["claim_renewed_at"] = "2026-07-31T00:01:00Z"
        row["claim_expires_at"] = "2026-07-31T00:04:00Z"
        self.events.append(self._event(row, "CLAIM_RENEWED"))
        return True

    def release(self, row_id, owner):
        row = self._row(row_id)
        if row.get("claim_owner") != owner:
            return False
        row["upload_status"] = "QUEUED"
        row["claim_owner"] = None
        row["claim_started_at"] = None
        row["claim_expires_at"] = None
        row["claim_renewed_at"] = None
        self.events.append(self._event(row, "CLAIM_RELEASED"))
        return True

    def schedule_retry(self, row_id, owner):
        row = self._row(row_id)
        if row.get("claim_owner") != owner:
            return False
        row["upload_status"] = "FAILED_RETRYABLE"
        row["retryable"] = True
        row["failure_code"] = "TRANSFER_RETRYABLE"
        row["failure_reason"] = "synthetic B3 retry verification"
        row["next_retry_at"] = "2026-07-31T00:02:00Z"
        row["claim_owner"] = None
        row["claim_started_at"] = None
        row["claim_expires_at"] = None
        return True

    def expire_claim(self, row_id, owner, destination_folder_id):
        row = self._row(row_id)
        if (
            row.get("claim_owner") != owner
            or row["destination_folder_id"] != destination_folder_id
        ):
            return False
        row["_expired"] = True
        return True

    def restore_clean(self, row_id, destination_folder_id):
        if self.restore_fails:
            return False
        row = self._row(row_id)
        if row["destination_folder_id"] != destination_folder_id:
            return False
        for key, value in {
            "upload_status": "NOT_STARTED",
            "verification_level": "SOURCE_HASH_VERIFIED",
            "destination_google_file_id": None,
            "upload_attempt_count": 0,
            "last_attempt_at": None,
            "next_retry_at": None,
            "upload_started_at": None,
            "upload_completed_at": None,
            "verified_at": None,
            "retryable": None,
            "failure_code": None,
            "failure_reason": None,
            "claim_owner": None,
            "claim_started_at": None,
            "claim_expires_at": None,
            "claim_renewed_at": None,
        }.items():
            row[key] = value
        row.pop("_expired", None)
        return True

    def audit_events(self, row_ids):
        allowed = set(row_ids)
        return [
            deepcopy(event)
            for event in self.events
            if event["asset_destination_id"] in allowed
        ]

    def _row(self, row_id):
        return next(row for row in self.rows if row["id"] == row_id)

    @staticmethod
    def _event(row, event_type):
        return {
            "asset_id": row["asset_id"],
            "asset_destination_id": row["id"],
            "event_type": event_type,
            "event_status": "SUCCESS",
            "details": {},
        }


def options(tmp, **changes):
    values = {
        "expected_canonical_count": 3,
        "expected_preexisting_destination_count": 0,
        "controlled_row_count": 3,
        "destination_folder_id": ROOT,
        "database_only": True,
        "execute": True,
        "report_path": Path(tmp) / "report.json",
    }
    values.update(changes)
    return B3Options(**values)


class OrchestrationTests(unittest.TestCase):
    def test_successful_full_sequence_and_restoration(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDatabase()
            report = B3Orchestrator(db, options(tmp)).execute()
        self.assertEqual(report["verdict"], READY_VERDICT)
        self.assertTrue(report["final_reconciliation"]["clean"])
        self.assertEqual(report["restoration"]["restored_rows"], 3)

    def test_first_initialization_exact_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = B3Orchestrator(FakeDatabase(), options(tmp)).execute()
        self.assertEqual(report["results"]["first_initialization"]["inserted"], 3)

    def test_second_initialization_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = B3Orchestrator(FakeDatabase(), options(tmp)).execute()
        self.assertEqual(report["results"]["second_initialization"]["inserted"], 0)
        self.assertEqual(report["results"]["second_initialization"]["reused"], 3)

    def test_wrong_canonical_count_refuses_before_initialize(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDatabase()
            report = B3Orchestrator(
                db, options(tmp, expected_canonical_count=4)
            ).execute()
        self.assertEqual(report["verdict"], BLOCKED_VERDICT)
        self.assertEqual(db.rows, [])

    def test_wrong_preexisting_count_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDatabase()
            report = B3Orchestrator(
                db, options(tmp, expected_preexisting_destination_count=1)
            ).execute()
        self.assertIn("Pre-existing", report["primary_failure"])

    def test_active_claim_refuses_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDatabase()
            db.initialize(
                __import__(
                    "kdi_media.step10_upload", fromlist=["x"]
                ).prepare_lifecycle_initialization(
                    db.assets, db.links, db.sources, ROOT
                )
            )
            db.rows[0]["claim_owner"] = "active"
            db.rows[0]["claim_expires_at"] = "later"
            report = B3Orchestrator(
                db, options(tmp, expected_preexisting_destination_count=3)
            ).execute()
        self.assertIn("Unsafe", report["primary_failure"])

    def test_destination_file_refuses_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDatabase()
            db.initialize(
                __import__(
                    "kdi_media.step10_upload", fromlist=["x"]
                ).prepare_lifecycle_initialization(
                    db.assets, db.links, db.sources, ROOT
                )
            )
            db.rows[0]["destination_google_file_id"] = "existing"
            report = B3Orchestrator(
                db, options(tmp, expected_preexisting_destination_count=3)
            ).execute()
        self.assertIn("Unsafe", report["primary_failure"])

    def test_uploaded_and_verified_refuse_preflight(self):
        for state in ("UPLOADED", "VERIFIED"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                db = FakeDatabase()
                db.initialize(
                    __import__(
                        "kdi_media.step10_upload", fromlist=["x"]
                    ).prepare_lifecycle_initialization(
                        db.assets, db.links, db.sources, ROOT
                    )
                )
                db.rows[0]["upload_status"] = state
                report = B3Orchestrator(
                    db,
                    options(tmp, expected_preexisting_destination_count=3),
                ).execute()
                self.assertIn("Unsafe", report["primary_failure"])

    def test_empty_allowlist_changes_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = B3Orchestrator(FakeDatabase(), options(tmp)).execute()
        self.assertEqual(report["results"]["empty_allowlist"]["changed"], 0)

    def test_exact_allowlist_changes_no_outside_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = B3Orchestrator(FakeDatabase(), options(tmp)).execute()
        self.assertEqual(
            report["results"]["exact_allowlist"]["outside_changed"], 0
        )

    def test_scoped_claim_and_active_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = B3Orchestrator(FakeDatabase(), options(tmp)).execute()
        self.assertEqual(report["results"]["exact_allowlist"]["claimed"], 3)
        self.assertTrue(report["results"]["active_lease_protection"])

    def test_renewal_owner_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = B3Orchestrator(FakeDatabase(), options(tmp)).execute()
        self.assertTrue(report["results"]["renewal"])
        self.assertTrue(report["results"]["wrong_owner_renewal_rejected"])

    def test_release_owner_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = B3Orchestrator(FakeDatabase(), options(tmp)).execute()
        self.assertTrue(report["results"]["release"])
        self.assertTrue(report["results"]["wrong_owner_release_rejected"])

    def test_expired_recovery_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = B3Orchestrator(FakeDatabase(), options(tmp)).execute()
        self.assertTrue(report["results"]["expired_lease_recovery"])
        self.assertEqual(
            report["results"]["retry_scheduling"]["bounded_max_attempts"], 5
        )

    def test_audit_is_sanitized_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = B3Orchestrator(FakeDatabase(), options(tmp)).execute()
        self.assertTrue(report["results"]["audit"]["payloads_sanitized"])
        self.assertEqual(
            len(report["results"]["audit"]["required_events_present"]), 4
        )

    def test_restoration_runs_after_mid_sequence_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDatabase()
            db.fail_at = "claim"
            report = B3Orchestrator(db, options(tmp)).execute()
        self.assertEqual(report["verdict"], BLOCKED_VERDICT)
        self.assertEqual(report["restoration"]["failed_rows"], 0)

    def test_restoration_failure_has_manual_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDatabase()
            db.restore_fails = True
            report = B3Orchestrator(db, options(tmp)).execute()
        self.assertEqual(report["verdict"], MANUAL_VERDICT)
        self.assertIsNotNone(report["restoration_failure"])

    def test_final_reconciliation_detects_dirty_state(self):
        with self.assertRaises(B3SafetyError):
            reconcile_final(
                [
                    {
                        "asset_id": str(uuid4()),
                        "destination_folder_id": ROOT,
                        "upload_status": "CLAIMED",
                        "verification_level": "SOURCE_HASH_VERIFIED",
                        "claim_owner": "x",
                    }
                ],
                1,
                ROOT,
            )

    def test_controlled_selection_is_deterministic(self):
        rows = [
            {
                "id": value,
                "asset_id": str(uuid4()),
                "destination_folder_id": ROOT,
                "upload_status": "NOT_STARTED",
                "verification_level": "SOURCE_HASH_VERIFIED",
            }
            for value in ("c", "a", "b")
        ]
        self.assertEqual(
            [row["id"] for row in select_controlled_rows(rows, 2, ROOT)],
            ["a", "b"],
        )

    def test_database_only_gate_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(B3SafetyError):
                B3Orchestrator(
                    FakeDatabase(), options(tmp, database_only=False)
                ).plan()

    def test_execute_gate_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(B3SafetyError):
                B3Orchestrator(
                    FakeDatabase(), options(tmp, execute=False)
                ).execute()

    def test_report_schema_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = B3Orchestrator(FakeDatabase(), options(tmp)).execute()
        self.assertTrue(
            {
                "phase",
                "mode",
                "verdict",
                "results",
                "restoration",
                "final_reconciliation",
                "drive_operations",
            }.issubset(report)
        )

    def test_candidate_derivation_reuses_step10_selector(self):
        source = Path("src/kdi_media/step10_b3.py").read_text(encoding="utf-8")
        self.assertIn("prepare_lifecycle_initialization(", source)
        self.assertNotIn("def select_canonical_source", source)

    def test_no_drive_import_or_transfer_symbols(self):
        source = Path("src/kdi_media/step10_b3.py").read_text(encoding="utf-8")
        self.assertNotIn("google_drive", source)
        self.assertNotIn("DriveResumableTransfer", source)
        self.assertNotIn(".transfer(", source)

    def test_no_broad_update_in_orchestrator(self):
        source = Path("src/kdi_media/step10_b3.py").read_text(encoding="utf-8")
        update_sections = source.split(
            'self.client.table("asset_destinations")'
        )[1:]
        self.assertTrue(update_sections)
        for section in update_sections:
            if ".update(" not in section:
                continue
            before_execute = section.split(".execute()", 1)[0]
            self.assertIn('.eq("id"', before_execute)
            self.assertIn('.eq("destination_folder_id"', before_execute)


class CliTests(unittest.TestCase):
    def base(self, report):
        return [
            sys.executable,
            str(SCRIPT),
            "--expected-canonical-count",
            "878",
            "--expected-preexisting-destination-count",
            "0",
            "--destination-folder-id",
            ROOT,
            "--report-path",
            str(report),
        ]

    def test_default_cli_is_non_mutating(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "plan.json"
            result = subprocess.run(
                self.base(report), capture_output=True, text=True, check=False
            )
            data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data["database_writes"], 0)
        self.assertEqual(data["drive_requests"], 0)

    def test_execution_requires_database_only_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [*self.base(Path(tmp) / "x.json"), "--execute-database-tests"],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("database-only", result.stderr)

    def test_execution_requires_drive_disabled_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    *self.base(Path(tmp) / "x.json"),
                    "--execute-database-tests",
                    "--database-only",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("drive-operations-disabled", result.stderr)

    def test_help_succeeds(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--execute-database-tests", result.stdout)

    def test_import_constructs_no_clients(self):
        spec = importlib.util.spec_from_file_location("b3_cli", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        with patch("supabase.create_client") as create:
            assert spec.loader
            spec.loader.exec_module(module)
        create.assert_not_called()

    def test_plan_contains_no_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "plan.json"
            subprocess.run(
                self.base(report), capture_output=True, text=True, check=True
            )
            text = report.read_text(encoding="utf-8").lower()
        for token in ("service_role_key", "access_token", "refresh_token"):
            self.assertNotIn(token, text)

    def test_verdict_exit_codes(self):
        spec = importlib.util.spec_from_file_location("b3_exit_cli", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
        self.assertEqual(module.verdict_exit_code(READY_VERDICT), 0)
        self.assertEqual(module.verdict_exit_code(BLOCKED_VERDICT), 2)
        self.assertEqual(module.verdict_exit_code(MANUAL_VERDICT), 3)


if __name__ == "__main__":
    unittest.main()
