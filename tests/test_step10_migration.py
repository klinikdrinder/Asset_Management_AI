from __future__ import annotations

from pathlib import Path
import re
import unittest


MIGRATION = Path(
    "supabase/migrations/202607300002_add_step10_asset_destinations.sql"
)


class Step10MigrationStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_transaction_and_table(self):
        self.assertTrue(self.lower.startswith("begin;"))
        self.assertTrue(self.lower.rstrip().endswith("commit;"))
        self.assertIn(
            "create table if not exists public.asset_destinations",
            self.lower,
        )

    def test_required_columns(self):
        for column in (
            "asset_id",
            "selected_source_file_id",
            "destination_folder_id",
            "destination_drive_id",
            "destination_google_file_id",
            "destination_url",
            "destination_filename",
            "destination_relative_path",
            "migration_version",
            "idempotency_key",
            "upload_status",
            "verification_level",
            "expected_bytes",
            "transferred_bytes",
            "destination_reported_bytes",
            "source_sha256",
            "provider_checksum_type",
            "provider_checksum_value",
            "upload_attempt_count",
            "last_attempt_at",
            "upload_started_at",
            "upload_completed_at",
            "verified_at",
            "retryable",
            "failure_code",
            "failure_reason",
            "source_metadata_snapshot",
            "destination_metadata_snapshot",
            "claim_owner",
            "claim_started_at",
            "claim_expires_at",
            "claim_renewed_at",
            "created_at",
            "updated_at",
        ):
            self.assertRegex(self.lower, rf"\b{column}\b")

    def test_foreign_keys_and_uniqueness(self):
        self.assertIn("references public.assets(id)", self.lower)
        self.assertIn("references public.source_files(id)", self.lower)
        self.assertIn(
            "references public.assets(id) on delete restrict",
            self.lower,
        )
        self.assertIn(
            "references public.source_files(id) on delete restrict",
            self.lower,
        )
        self.assertRegex(
            self.lower,
            r"unique\s*\(\s*asset_id\s*,\s*destination_folder_id\s*\)",
        )
        self.assertIn(
            "asset_destinations_google_file_id_unique", self.lower
        )
        self.assertRegex(
            self.lower,
            r"unique index[\s\S]*asset_destinations_google_file_id_unique"
            r"[\s\S]*on public\.asset_destinations "
            r"\(destination_google_file_id\)"
            r"[\s\S]*where destination_google_file_id is not null",
        )

    def test_lifecycle_states(self):
        for state in (
            "NOT_STARTED",
            "QUEUED",
            "CLAIMED",
            "UPLOADING",
            "UPLOADED",
            "VERIFIED",
            "FAILED_RETRYABLE",
            "FAILED_PERMANENT",
            "SOURCE_CHANGED",
            "SOURCE_NOT_FOUND",
            "SOURCE_ACCESS_DENIED",
            "DESTINATION_ACCESS_DENIED",
            "DESTINATION_CONFLICT",
            "MANUAL_REVIEW_REQUIRED",
        ):
            self.assertIn(f"'{state.lower()}'", self.lower)

    def test_verification_levels(self):
        for level in (
            "NONE",
            "SOURCE_HASH_VERIFIED",
            "TRANSFER_BYTE_COUNT_VERIFIED",
            "DESTINATION_METADATA_VERIFIED",
            "PROVIDER_CHECKSUM_VERIFIED",
            "DESTINATION_SHA256_VERIFIED",
        ):
            self.assertIn(f"'{level.lower()}'", self.lower)

    def test_indexes_and_updated_at(self):
        for token in (
            "asset_destinations_upload_status_idx",
            "asset_destinations_verification_level_idx",
            "asset_destinations_retryable_idx",
            "asset_destinations_claim_expiry_idx",
            "asset_destinations_asset_id_idx",
            "asset_destinations_source_file_id_idx",
            "asset_destinations_folder_id_idx",
            "asset_destinations_google_file_id_idx",
            "asset_destinations_set_updated_at",
        ):
            self.assertIn(token, self.lower)

    def test_claim_lease_rpcs(self):
        for function in (
            "claim_asset_destinations",
            "renew_asset_destination_claim",
            "release_asset_destination_claim",
        ):
            self.assertIn(
                f"create or replace function public.{function}",
                self.lower,
            )
        self.assertIn("for update skip locked", self.lower)
        self.assertIn("requested_limit between 1 and 100", self.lower)
        self.assertIn("claim_expires_at <= now()", self.lower)
        self.assertIn("next_retry_at <= now()", self.lower)
        self.assertRegex(
            self.lower,
            r"coalesce\([\s\S]*candidate_source\.next_retry_at,"
            r"[\s\S]*candidate_source\.last_attempt_at,"
            r"[\s\S]*candidate_source\.created_at[\s\S]*\)",
        )
        self.assertRegex(
            self.lower,
            r"candidate_source\.upload_status in \(\s*'not_started',"
            r"\s*'queued',\s*'failed_retryable'\s*\)",
        )
        self.assertNotIn("upload_status in ('verified'", self.lower)
        self.assertNotIn("returns setof public.asset_destinations", self.lower)
        self.assertIn("returns table (", self.lower)

    def test_rls_and_security(self):
        self.assertIn(
            "alter table public.asset_destinations enable row level security",
            self.lower,
        )
        self.assertIn("asset_destinations_authorized_read", self.lower)
        self.assertIn("grant all on table public.asset_destinations to service_role", self.lower)
        self.assertIn("revoke all on function", self.lower)

    def test_integrity_checks(self):
        self.assertIn("expected_bytes >= 0", self.lower)
        self.assertIn("transferred_bytes >= 0", self.lower)
        self.assertIn("upload_attempt_count >= 0", self.lower)
        self.assertIn("source_sha256 ~ '^[0-9a-f]{64}$'", self.lower)
        self.assertIn("destination_google_file_id is not null", self.lower)
        self.assertIn("verified_at is not null", self.lower)
        self.assertIn("'destination_metadata_verified'", self.lower)

    def test_no_destructive_or_seed_operations(self):
        self.assertIsNone(re.search(r"\b(delete|truncate)\s+from\b", self.lower))
        self.assertNotIn("insert into public.asset_destinations", self.lower)
        self.assertNotIn("drop table", self.lower)

    def test_worker_enum_and_rpc_contract_matches(self):
        import inspect
        from kdi_media import step10_upload

        for status in step10_upload.UploadStatus:
            self.assertIn(f"'{status.value.lower()}'", self.lower)
        for level in step10_upload.VerificationLevel:
            self.assertIn(f"'{level.value.lower()}'", self.lower)
        worker = inspect.getsource(step10_upload.SupabaseStep10Repository)
        for function in (
            "claim_asset_destinations",
            "renew_asset_destination_claim",
            "release_asset_destination_claim",
        ):
            self.assertIn(function, worker)
        for argument in (
            "requested_claim_owner",
            "requested_limit",
            "requested_lease_seconds",
            "requested_asset_destination_id",
        ):
            self.assertIn(argument, worker)


if __name__ == "__main__":
    unittest.main()
