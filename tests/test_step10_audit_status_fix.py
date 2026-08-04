from __future__ import annotations

import hashlib
from pathlib import Path
import re
import unittest


MIGRATION = Path(
    "supabase/migrations/"
    "202607310001_fix_step10_migration_events_status.sql"
)
VERIFICATION = Path(
    "supabase/verification/verify_step10_audit_status_fix.sql"
)
B2 = Path(
    "supabase/migrations/202607300002_add_step10_asset_destinations.sql"
)
B3 = Path(
    "supabase/migrations/202607300003_fix_step10_b3_controls.sql"
)
B2_SHA256 = (
    "92531a14d45bdf7e6569c1966d17ff95416a408344940a2555fa39fcf89e0758"
)
B3_SHA256 = (
    "b0202af50e4f5e510d4bec9140a0be208ad1b4262f0920e7911ec0bef100f9ef"
)


class Step10AuditStatusMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()
        cls.verify = VERIFICATION.read_text(encoding="utf-8")
        cls.verify_lower = cls.verify.lower()

    def test_forward_only_transaction(self):
        self.assertTrue(self.lower.startswith("begin;"))
        self.assertTrue(self.lower.rstrip().endswith("commit;"))
        self.assertNotIn("rollback;", self.lower)

    def test_original_step10_migrations_unchanged(self):
        self.assertEqual(
            hashlib.sha256(B2.read_bytes()).hexdigest(), B2_SHA256
        )
        self.assertEqual(
            hashlib.sha256(B3.read_bytes()).hexdigest(), B3_SHA256
        )

    def test_lifecycle_initialized_is_covered(self):
        self.assertIn("'lifecycle_initialized'", self.lower)

    def test_claim_renewed_is_covered(self):
        self.assertIn("'claim_renewed'", self.lower)

    def test_claim_released_is_covered(self):
        self.assertIn("'claim_released'", self.lower)

    def test_claim_recovered_is_covered(self):
        self.assertIn("'claim_recovered'", self.lower)

    def test_retry_and_failure_events_are_covered(self):
        for event in (
            "upload_failed",
            "upload_retry_scheduled",
            "source_changed",
            "source_not_found",
            "source_access_denied",
            "destination_access_denied",
            "destination_conflict",
            "manual_review_required",
        ):
            self.assertIn(f"'{event}'", self.lower)

    def test_upload_and_verification_events_are_covered(self):
        for event in (
            "upload_queued",
            "upload_claimed",
            "upload_started",
            "upload_created",
            "upload_recovered",
            "upload_verified",
        ):
            self.assertIn(f"'{event}'", self.lower)

    def test_success_mapping_uses_deployed_contract(self):
        self.assertIn("preferred_status := 'success'", self.lower)
        self.assertIn("fallback_status := 'completed'", self.lower)
        self.assertIn("pg_get_constraintdef", self.lower)
        self.assertIn("status_attribute.attname = 'status'", self.lower)

    def test_failure_warning_and_info_mappings_are_bounded(self):
        for value in (
            "preferred_status := 'error'",
            "fallback_status := 'failed'",
            "preferred_status := 'warning'",
            "fallback_status := 'skipped'",
            "preferred_status := 'info'",
            "fallback_status := 'pending'",
        ):
            self.assertIn(value, self.lower)

    def test_invalid_event_status_fails_closed(self):
        self.assertIn(
            "unsupported step 10 migration event_status contract",
            self.lower,
        )
        self.assertIn(
            "has no safe step 10 mapping",
            self.lower,
        )

    def test_existing_explicit_status_is_preserved(self):
        self.assertIn("if new.status is not null then", self.lower)

    def test_unrelated_events_are_unchanged(self):
        self.assertIn("new.asset_destination_id is null", self.lower)
        self.assertRegex(
            self.lower,
            r"new\.event_type not in \([\s\S]+?\)\s+then\s+return new",
        )

    def test_payload_is_not_rewritten(self):
        self.assertNotIn("new.details :=", self.lower)
        self.assertNotIn("new.message :=", self.lower)
        self.assertNotIn("new.event_details :=", self.lower)
        self.assertNotIn("new.event_type :=", self.lower)

    def test_no_sensitive_material_is_added(self):
        for token in (
            "file_name",
            "source_path",
            "content_sha256",
            "patient",
            "access_token",
            "refresh_token",
            "authorization",
            "spool",
        ):
            self.assertNotIn(token, self.lower)

    def test_initialization_atomicity_is_preserved(self):
        corrective = B3.read_text(encoding="utf-8").lower()
        self.assertIn(
            "after insert on public.asset_destinations", corrective
        )
        self.assertIn(
            "before insert on public.migration_events", self.lower
        )
        self.assertIn("raise exception", self.lower)

    def test_no_step9_or_destination_table_mutation(self):
        for token in (
            "update public.source_files",
            "update public.assets",
            "update public.asset_sources",
            "update public.asset_destinations",
            "insert into public.asset_destinations",
            "delete from",
            "truncate",
            "drop table",
        ):
            self.assertNotIn(token, self.lower)

    def test_claim_and_scope_functions_are_not_replaced(self):
        for function_name in (
            "claim_asset_destinations",
            "renew_asset_destination_claim",
            "release_asset_destination_claim",
        ):
            self.assertNotIn(
                f"create or replace function public.{function_name}",
                self.lower,
            )

    def test_security_and_permissions_are_narrow(self):
        self.assertIn("security invoker", self.lower)
        self.assertIn("set search_path = ''", self.lower)
        self.assertIn(
            "from public, anon, authenticated", self.lower
        )
        self.assertNotIn("grant all", self.lower)
        self.assertNotIn("disable row level security", self.lower)

    def test_trigger_is_before_insert_only(self):
        self.assertIn(
            "before insert on public.migration_events", self.lower
        )
        self.assertNotIn("before update", self.lower)
        self.assertNotIn("before delete", self.lower)

    def test_verifier_is_read_only(self):
        for token in (
            "insert into",
            "update public.",
            "delete from",
            "truncate",
            "alter table",
            "create ",
            "drop ",
        ):
            self.assertNotIn(token, self.verify_lower)

    def test_verifier_checks_required_schema_contract(self):
        for token in (
            "migration_events.status is missing or nullable",
            "migration_events.event_status contract changed",
            "migration_events_event_status_check",
            "migration_events.status has no allowed successful",
        ):
            self.assertIn(token, self.verify_lower)

    def test_verifier_checks_function_and_trigger(self):
        self.assertIn(
            "set_step10_migration_event_legacy_status",
            self.verify_lower,
        )
        self.assertIn(
            "migration_events_set_step10_legacy_status",
            self.verify_lower,
        )
        self.assertIn("before insert", self.verify_lower)

    def test_verifier_checks_clean_pre_b3_counts(self):
        for value in (
            "source_file_count <> 886",
            "eligible_hashed_count <> 878",
            "asset_count <> 878",
            "relationship_count <> 878",
            "destination_count <> 0",
            "orphan_relationship_count <> 0",
        ):
            self.assertIn(value, self.verify_lower)

    def test_no_drive_dependency(self):
        combined = self.lower + self.verify_lower
        self.assertNotIn("google_drive", combined)
        self.assertNotIn("drive.files", combined)
        self.assertNotIn("oauth", combined)

    def test_only_expected_schema_objects_are_created(self):
        creates = re.findall(
            r"create(?: or replace)? (function|trigger)\s+([^\s(]+)",
            self.lower,
        )
        self.assertEqual(
            creates,
            [
                (
                    "function",
                    "public.set_step10_migration_event_legacy_status",
                ),
                ("trigger", "migration_events_set_step10_legacy_status"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
