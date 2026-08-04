from __future__ import annotations

import hashlib
from pathlib import Path
import re
import unittest


MIGRATION = Path(
    "supabase/migrations/"
    "202607310004_fix_step10_exact_legacy_status_contract.sql"
)
VERIFIER = Path(
    "supabase/verification/verify_step10_legacy_status_mapping.sql"
)
DEPLOYED_HASHES = {
    Path(
        "supabase/migrations/202607300002_add_step10_asset_destinations.sql"
    ): "92531a14d45bdf7e6569c1966d17ff95416a408344940a2555fa39fcf89e0758",
    Path(
        "supabase/migrations/202607300003_fix_step10_b3_controls.sql"
    ): "b0202af50e4f5e510d4bec9140a0be208ad1b4262f0920e7911ec0bef100f9ef",
    Path(
        "supabase/migrations/"
        "202607310001_fix_step10_migration_events_status.sql"
    ): "b5c43d979332750c1caecb1ac9b90a569febf92029b6ff4557cf7d22a2dd5af8",
    Path(
        "supabase/migrations/"
        "202607310002_extend_step10_event_type_contract.sql"
    ): "f24eb3bfd52c9368f328faa9a87993a7fe212764bb68b524a3ac1f148becd304",
}
STEP10_EVENTS = {
    "LIFECYCLE_INITIALIZED",
    "UPLOAD_QUEUED",
    "UPLOAD_CLAIMED",
    "CLAIM_RENEWED",
    "CLAIM_RELEASED",
    "CLAIM_RECOVERED",
    "UPLOAD_STARTED",
    "UPLOAD_CREATED",
    "UPLOAD_RECOVERED",
    "UPLOAD_VERIFIED",
    "UPLOAD_FAILED",
    "UPLOAD_RETRY_SCHEDULED",
    "SOURCE_CHANGED",
    "SOURCE_NOT_FOUND",
    "SOURCE_ACCESS_DENIED",
    "DESTINATION_ACCESS_DENIED",
    "DESTINATION_CONFLICT",
    "MANUAL_REVIEW_REQUIRED",
}


class Step10LegacyStatusMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()
        cls.verify = VERIFIER.read_text(encoding="utf-8")
        cls.verify_lower = cls.verify.lower()

    def test_forward_only_transaction(self):
        self.assertTrue(self.lower.startswith("begin;"))
        self.assertTrue(self.lower.rstrip().endswith("commit;"))
        self.assertNotIn("rollback;", self.lower)

    def test_deployed_migrations_are_unchanged(self):
        for path, expected in DEPLOYED_HASHES.items():
            with self.subTest(path=path):
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected,
                )

    def test_catalog_resolves_exact_status_constraint(self):
        for text in (
            "status_attribute_number",
            "constraint_row.convalidated",
            "array[status_attribute_number]::smallint[]",
            "constraint_row.conname = 'migration_events_status_check'",
        ):
            self.assertIn(text, self.lower)

    def test_unsupported_constraint_shape_fails_closed(self):
        self.assertIn("unsupported_remainder", self.lower)
        self.assertIn(
            "unsupported migration_events_status_check expression shape",
            self.lower,
        )

    def test_existing_legacy_values_are_preserved(self):
        for value in (
            "queued",
            "running",
            "success",
            "skipped",
            "duplicate",
            "failed",
            "retrying",
            "cancelled",
        ):
            self.assertIn(f"'{value}'", self.lower)
        self.assertIn("unexpected migration_events.status vocabulary", self.lower)

    def test_constraint_remains_strict(self):
        self.assertIn(
            "add constraint migration_events_status_check",
            self.lower,
        )
        self.assertIn("status in (", self.lower)
        self.assertNotIn("drop column", self.lower)

    def test_info_mapping(self):
        self.assertIn("when 'info' then new.status := 'info'", self.lower)

    def test_success_mapping(self):
        self.assertIn(
            "when 'success' then new.status := 'success'", self.lower
        )

    def test_warning_mapping(self):
        self.assertIn(
            "when 'warning' then new.status := 'warning'", self.lower
        )

    def test_error_mapping(self):
        self.assertIn("when 'error' then new.status := 'error'", self.lower)

    def test_invalid_event_status_fails_closed(self):
        self.assertIn(
            "unsupported step 10 migration event_status contract",
            self.lower,
        )

    def test_all_step10_events_are_covered(self):
        function_block = self.sql.split(
            "create or replace function", 1
        )[1]
        observed = set(
            re.findall(r"'([A-Z][A-Z0-9_]*)'", function_block)
        )
        self.assertTrue(STEP10_EVENTS.issubset(observed))

    def test_upload_audit_classes_are_verified(self):
        for event_type in (
            "UPLOAD_STARTED",
            "UPLOAD_CREATED",
            "UPLOAD_VERIFIED",
            "UPLOAD_FAILED",
            "UPLOAD_RETRY_SCHEDULED",
            "MANUAL_REVIEW_REQUIRED",
        ):
            self.assertIn(event_type.lower(), self.lower)

    def test_trigger_is_before_insert(self):
        self.assertIn(
            "before insert on public.migration_events", self.lower
        )
        self.assertNotIn("before update", self.lower)

    def test_audit_atomicity_is_preserved(self):
        self.assertIn("raise exception", self.lower)
        self.assertEqual(self.lower.count("commit;"), 1)

    def test_payload_is_not_modified(self):
        for token in (
            "new.details :=",
            "new.message :=",
            "new.event_type :=",
            "new.event_status :=",
        ):
            self.assertNotIn(token, self.lower)

    def test_no_step9_or_lifecycle_data_mutation(self):
        for table in (
            "source_files",
            "assets",
            "asset_sources",
            "asset_destinations",
        ):
            self.assertNotIn(f"update public.{table}", self.lower)
            self.assertNotIn(f"insert into public.{table}", self.lower)
            self.assertNotIn(f"alter table public.{table}", self.lower)

    def test_no_claim_lease_retry_or_scope_function_change(self):
        for function_name in (
            "claim_asset_destinations",
            "renew_asset_destination_claim",
            "release_asset_destination_claim",
            "recover_expired_asset_destination_claims",
        ):
            self.assertNotIn(
                f"create or replace function public.{function_name}",
                self.lower,
            )

    def test_no_drive_or_sensitive_data_dependency(self):
        for token in (
            "google_drive",
            "oauth",
            "access_token",
            "refresh_token",
            "source_path",
            "file_name",
            "content_sha256",
            "patient",
            "spool",
        ):
            self.assertNotIn(token, self.lower + self.verify_lower)

    def test_verifier_probes_all_four_mappings(self):
        for pair in (
            "'upload_started', 'info'",
            "'upload_verified', 'success'",
            "'manual_review_required', 'warning'",
            "'upload_failed', 'error'",
        ):
            self.assertIn(pair, self.verify_lower)

    def test_verifier_rejects_arbitrary_status_and_event(self):
        self.assertIn(
            "step10_arbitrary_invalid_status", self.verify_lower
        )
        self.assertIn(
            "step10_arbitrary_invalid_event", self.verify_lower
        )
        self.assertGreaterEqual(
            self.verify_lower.count("when check_violation then null"), 2
        )

    def test_verifier_checks_required_status_and_trigger(self):
        self.assertIn(
            "migration_events.status is not required", self.verify_lower
        )
        self.assertIn(
            "migration_events_set_step10_legacy_status", self.verify_lower
        )
        self.assertIn(
            "set_step10_migration_event_legacy_status", self.verify_lower
        )

    def test_verifier_checks_counts_before_pilot(self):
        for text in (
            "count(*) from public.source_files) <> 886",
            "count(*) from public.assets) <> 878",
            "count(*) from public.asset_sources) <> 878",
            "count(*) from public.asset_destinations) <> 878",
            "pilot destination ids exist before retry",
        ):
            self.assertIn(text, self.verify_lower)

    def test_verifier_is_transactionally_rolled_back(self):
        self.assertTrue(self.verify_lower.startswith("-- transactional"))
        self.assertIn("begin;", self.verify_lower)
        self.assertTrue(self.verify_lower.rstrip().endswith("rollback;"))

    def test_verifier_returns_required_marker(self):
        self.assertIn(
            "'step_10_legacy_status_mapping_verified' as result",
            self.verify_lower,
        )
        self.assertEqual(
            self.verify_lower.count(
                "'step_10_legacy_status_mapping_verified' as result"
            ),
            1,
        )

    def test_only_expected_schema_objects_change(self):
        self.assertEqual(
            re.findall(
                r"create(?: or replace)? (function|trigger)\s+([^\s(]+)",
                self.lower,
            ),
            [
                (
                    "function",
                    "public.set_step10_migration_event_legacy_status",
                ),
                ("trigger", "migration_events_set_step10_legacy_status"),
            ],
        )
        self.assertNotIn("grant all", self.lower)
        self.assertNotIn("disable row level security", self.lower)


if __name__ == "__main__":
    unittest.main()
