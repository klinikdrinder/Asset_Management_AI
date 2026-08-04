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
from uuid import NAMESPACE_URL, uuid5

from kdi_media.step10_pilot import (
    APPROVED_PILOT_LIFECYCLE_IDS,
    APPROVED_ROOT,
    BLOCKED_VERDICT,
    EXPECTED_FORMAT_MIX,
    MANUAL_VERDICT,
    READY_VERDICT,
    PilotManifest,
    PilotOptions,
    PilotOrchestrator,
    PilotSafetyError,
    _clean_pilot_row,
)


MANIFEST = Path("reports/step_10_phase_b1_pilot_manifest.json")
SCRIPT = Path("scripts/run_step10_limited_production_pilot.py")


def options(root: Path, **changes):
    values = {
        "execute": True,
        "production_pilot": True,
        "pilot_only": True,
        "authorize_drive_transfer": True,
        "expected_pilot_count": 8,
        "expected_non_pilot_count": 870,
        "destination_root_id": APPROVED_ROOT,
        "source_profile": "source_readonly",
        "destination_profile": "destination_write",
        "manifest_path": MANIFEST,
        "report_path": root / "report.json",
        "spool_root": root / "spool",
    }
    values.update(changes)
    return PilotOptions(**values)


def destination_rows(manifest):
    ids = sorted(APPROVED_PILOT_LIFECYCLE_IDS)
    return [
        {
            "id": row_id,
            "asset_id": candidate.asset_id,
            "destination_folder_id": APPROVED_ROOT,
            "upload_status": "NOT_STARTED",
            "verification_level": "SOURCE_HASH_VERIFIED",
        }
        for row_id, candidate in zip(ids, manifest.candidates)
    ]


class FakeBackend:
    def __init__(self):
        self.manifest = PilotManifest.load(MANIFEST)
        self.destinations = destination_rows(self.manifest)
        self.calls = []
        self.fail_first = False
        self.cleanup_fails = False

    def preflight(self, manifest):
        self.calls.append("preflight")
        return {
            "destinations": deepcopy(self.destinations),
            "pilot_rows": 8,
            "non_pilot_rows": 870,
            "outside_digest": "stable",
        }

    def start_live(self, manifest):
        self.calls.append("start_live")

    def run_first(self, manifest):
        self.calls.append("first")
        if self.fail_first:
            raise RuntimeError("synthetic pilot failure")
        return [
            {
                "lifecycle_id": candidate.lifecycle_id,
                "destination_file_id": f"destination-{index}",
                "outcome": "UPLOADED",
            }
            for index, candidate in enumerate(manifest.candidates)
        ]

    def run_second(self, manifest):
        self.calls.append("second")
        return [
            {
                "lifecycle_id": candidate.lifecycle_id,
                "destination_file_id": f"destination-{index}",
                "outcome": "SKIPPED_VERIFIED",
                "new_files": 0,
            }
            for index, candidate in enumerate(manifest.candidates)
        ]

    def final_reconciliation(self, manifest, outside_digest):
        self.calls.append("final")
        return {
            "clean": True,
            "pilot_verified": 8,
            "outside_digest_stable": outside_digest == "stable",
        }

    def cleanup(self):
        self.calls.append("cleanup")
        if self.cleanup_fails:
            raise RuntimeError("synthetic cleanup failure")
        return {"released_claims": 0, "spool_files_remaining": 0}


class ManifestAndOptionsTests(unittest.TestCase):
    def test_manifest_exact_mix_and_unique_assets(self):
        manifest = PilotManifest.load(MANIFEST)
        mix = {
            value: sum(c.extension == value for c in manifest.candidates)
            for value in EXPECTED_FORMAT_MIX
        }
        self.assertEqual(mix, EXPECTED_FORMAT_MIX)
        self.assertEqual(len({c.asset_id for c in manifest.candidates}), 8)

    def test_manifest_has_deterministic_hash_selection(self):
        manifest = PilotManifest.load(MANIFEST)
        enhanced = [c.extension for c in manifest.candidates if c.enhanced_sha256]
        self.assertIn("jpeg", enhanced)
        self.assertIn("mp4", enhanced)

    def test_duplicate_manifest_assets_are_rejected(self):
        raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
        raw["candidates"][1]["asset_uuid"] = raw["candidates"][0]["asset_uuid"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(PilotSafetyError):
                PilotManifest.load(path)

    def test_wrong_manifest_mix_is_rejected(self):
        raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
        raw["candidates"][0]["extension"] = "mp4"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(PilotSafetyError):
                PilotManifest.load(path)

    def test_wrong_category_route_is_rejected(self):
        raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
        raw["candidates"][0]["destination_category"] = "Documents"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(PilotSafetyError):
                PilotManifest.load(path)

    def test_unknown_lifecycle_id_is_rejected(self):
        manifest = PilotManifest.load(MANIFEST)
        rows = destination_rows(manifest)
        rows[0]["id"] = "00000000-0000-0000-0000-000000000000"
        with self.assertRaises(PilotSafetyError):
            manifest.bind_lifecycle_ids(rows)

    def test_duplicate_lifecycle_id_is_rejected(self):
        manifest = PilotManifest.load(MANIFEST)
        rows = destination_rows(manifest)
        rows[1]["id"] = rows[0]["id"]
        with self.assertRaises(PilotSafetyError):
            manifest.bind_lifecycle_ids(rows)

    def test_wrong_pilot_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PilotSafetyError):
                options(Path(tmp), expected_pilot_count=7).validate()

    def test_wrong_non_pilot_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PilotSafetyError):
                options(Path(tmp), expected_non_pilot_count=871).validate()

    def test_unapproved_manifest_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PilotSafetyError):
                options(
                    Path(tmp), manifest_path=Path(tmp) / "pilot.json"
                ).validate()

    def test_missing_live_gates_are_rejected(self):
        for gate in (
            "production_pilot",
            "pilot_only",
            "authorize_drive_transfer",
        ):
            with self.subTest(gate=gate), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(PilotSafetyError):
                    options(Path(tmp), **{gate: False}).validate()

    def test_profiles_are_exact_and_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            for changes in (
                {"source_profile": "destination_write"},
                {"destination_profile": "source_readonly"},
            ):
                with self.assertRaises(PilotSafetyError):
                    options(Path(tmp), **changes).validate()

    def test_dirty_pilot_row_is_rejected(self):
        base = {
            "destination_folder_id": APPROVED_ROOT,
            "upload_status": "NOT_STARTED",
            "verification_level": "SOURCE_HASH_VERIFIED",
        }
        self.assertTrue(_clean_pilot_row(base, APPROVED_ROOT))
        for key, value in (
            ("upload_status", "VERIFIED"),
            ("claim_owner", "other"),
            ("claim_expires_at", "later"),
            ("destination_google_file_id", "existing"),
            ("next_retry_at", "later"),
            ("verified_at", "now"),
        ):
            with self.subTest(key=key):
                row = {**base, key: value}
                self.assertFalse(_clean_pilot_row(row, APPROVED_ROOT))


class OrchestratorTests(unittest.TestCase):
    def test_plan_mode_has_no_backend_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FakeBackend()
            report = PilotOrchestrator(
                backend, options(Path(tmp), execute=False)
            ).plan()
        self.assertEqual(backend.calls, [])
        self.assertEqual(report["database_writes"], 0)
        self.assertEqual(report["drive_clients_constructed"], 0)

    def test_success_runs_preflight_first_second_final_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FakeBackend()
            report = PilotOrchestrator(
                backend, options(Path(tmp))
            ).execute()
        self.assertEqual(report["verdict"], READY_VERDICT)
        self.assertEqual(
            backend.calls,
            ["preflight", "start_live", "first", "second", "final", "cleanup"],
        )
        self.assertEqual(len(report["first_run"]), 8)
        self.assertTrue(all(row["new_files"] == 0 for row in report["second_run"]))

    def test_mid_pilot_failure_stops_before_second_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FakeBackend()
            backend.fail_first = True
            report = PilotOrchestrator(
                backend, options(Path(tmp))
            ).execute()
        self.assertEqual(report["verdict"], BLOCKED_VERDICT)
        self.assertNotIn("second", backend.calls)
        self.assertEqual(backend.calls[-1], "cleanup")

    def test_cleanup_failure_requires_manual_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FakeBackend()
            backend.cleanup_fails = True
            report = PilotOrchestrator(
                backend, options(Path(tmp))
            ).execute()
        self.assertEqual(report["verdict"], MANUAL_VERDICT)
        self.assertIsNotNone(report["cleanup_failure"])

    def test_report_uses_only_approved_lifecycle_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = PilotOrchestrator(
                FakeBackend(), options(Path(tmp))
            ).execute()
        self.assertEqual(
            set(report["pilot_lifecycle_ids"]),
            APPROVED_PILOT_LIFECYCLE_IDS,
        )

    def test_partial_failure_error_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FakeBackend()
            backend.fail_first = True
            report = PilotOrchestrator(
                backend, options(Path(tmp))
            ).execute()
        self.assertNotIn("token", report["primary_failure"].lower())
        self.assertEqual(report["first_run"], [])


class StaticProductionPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("src/kdi_media/step10_pilot.py").read_text(
            encoding="utf-8"
        )
        cls.lower = cls.source.lower()

    def test_existing_worker_and_transfer_adapter_are_reused(self):
        self.assertIn("Step10UploadWorker(", self.source)
        self.assertIn("DriveResumableTransfer(", self.source)
        self.assertIn("worker.process(", self.source)

    def test_streaming_and_spool_are_not_reimplemented(self):
        self.assertNotIn("NamedTemporaryFile", self.source)
        self.assertNotIn("MediaFileUpload", self.source)
        self.assertNotIn("iter_drive_content", self.source)

    def test_exact_allowlist_and_root_scope_are_sent_to_claim(self):
        claim = self.source.split("self.repository.claim_batch(", 1)[1]
        self.assertIn("allowed", claim[:500])
        self.assertIn("manifest.root_id", claim[:500])

    def test_claim_renewal_and_cleanup_release_are_used(self):
        self.assertIn("self.repository.renew(", self.source)
        self.assertIn("self.repository.release(", self.source)

    def test_category_folders_are_reused_not_created(self):
        self.assertIn("resolve_category_folder(", self.source)
        self.assertIn("allow_create=False", self.source)

    def test_root_guard_is_configured_with_resolved_children(self):
        self.assertIn("DestinationRootGuard(manifest.root_id, folders)", self.source)

    def test_source_and_destination_services_are_isolated(self):
        self.assertIn("create_readonly_drive_service(", self.source)
        self.assertIn("create_destination_write_drive_service(", self.source)
        self.assertIn("Source and destination tokens are shared", self.source)

    def test_response_loss_lookup_and_metadata_verifier_are_reused(self):
        self.assertIn("lookup_destination_identity", self.source)
        self.assertIn("verify_destination_metadata(", self.source)

    def test_jpeg_and_mp4_sha256_verifier_is_reused(self):
        self.assertIn("verify_destination_sha256(", self.source)
        self.assertIn("candidate.enhanced_sha256", self.source)

    def test_bounded_retry_is_used(self):
        self.assertIn("run_with_retry(", self.source)
        self.assertIn("max_attempts=5", self.source)

    def test_app_properties_come_from_existing_plan(self):
        self.assertIn("build_destination_plan(", self.source)
        self.assertNotIn('"appProperties":', self.source)

    def test_no_source_or_step9_updates(self):
        for table in ("source_files", "assets", "asset_sources"):
            self.assertNotIn(f'table("{table}").update', self.source)

    def test_no_delete_move_trash_or_permission_operations(self):
        for token in (".delete(", ".update(fileid", "permissions().", ".trash("):
            self.assertNotIn(token, self.lower)

    def test_second_run_does_not_call_worker(self):
        concrete = self.source.split("class SupabaseDrivePilotBackend:", 1)[1]
        method = concrete.split("def run_second(", 1)[1].split(
            "def final_reconciliation(", 1
        )[0]
        self.assertNotIn("worker.process", method)
        self.assertIn("lookup_destination_identity", method)

    def test_outside_digest_is_compared_at_final_reconciliation(self):
        self.assertIn("_outside_digest(outside) == outside_digest", self.source)

    def test_step9_digest_is_compared(self):
        self.assertIn("step9_unchanged", self.source)

    def test_spool_cleanup_is_verified(self):
        self.assertIn('glob("step10-*.transfer")', self.source)
        self.assertIn("spool_files_remaining", self.source)

    def test_sensitive_source_fields_are_not_reported(self):
        concrete = self.source.split("def _process(", 1)[1].split(
            "def run_second(", 1
        )[0]
        result_block = concrete.rsplit("return {", 1)[1]
        self.assertNotIn('"source_sha256"', result_block)
        self.assertNotIn('"source_file_name"', result_block)
        self.assertNotIn('"full_source_path"', result_block)


class CliTests(unittest.TestCase):
    def base(self, report):
        return [
            sys.executable,
            str(SCRIPT),
            "--expected-pilot-count", "8",
            "--expected-non-pilot-count", "870",
            "--manifest-path", str(MANIFEST),
            "--destination-root-id", APPROVED_ROOT,
            "--source-profile", "source_readonly",
            "--destination-profile", "destination_write",
            "--report-path", str(report),
        ]

    def test_default_cli_is_plan_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "plan.json"
            result = subprocess.run(
                self.base(report), capture_output=True, text=True, check=False
            )
            data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data["mode"], "PLAN_ONLY")
        self.assertEqual(data["drive_clients_constructed"], 0)

    def test_execute_missing_pilot_only_is_rejected_before_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    *self.base(Path(tmp) / "x.json"),
                    "--execute-pilot",
                    "--production-pilot",
                    "--authorize-drive-transfer",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gates", result.stderr.lower())

    def test_execute_missing_transfer_authorization_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    *self.base(Path(tmp) / "x.json"),
                    "--execute-pilot",
                    "--production-pilot",
                    "--pilot-only",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)

    def test_wrong_cli_format_mix_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [*self.base(Path(tmp) / "x.json"), "--expected-jpeg-count", "2"],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)

    def test_cli_import_constructs_no_clients(self):
        spec = importlib.util.spec_from_file_location("pilot_cli", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        with patch("supabase.create_client") as create:
            assert spec.loader
            spec.loader.exec_module(module)
        create.assert_not_called()

    def test_exit_codes(self):
        spec = importlib.util.spec_from_file_location("pilot_exit_cli", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
        self.assertEqual(module.verdict_exit_code(READY_VERDICT), 0)
        self.assertEqual(module.verdict_exit_code(BLOCKED_VERDICT), 2)
        self.assertEqual(module.verdict_exit_code(MANUAL_VERDICT), 3)


if __name__ == "__main__":
    unittest.main()
