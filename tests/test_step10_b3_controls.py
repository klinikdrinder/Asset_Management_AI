from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from kdi_media.step10_upload import (
    SupabaseStep10Repository,
    prepare_lifecycle_initialization,
)


CORRECTIVE_MIGRATION = Path(
    "supabase/migrations/202607300003_fix_step10_b3_controls.sql"
)
B2_MIGRATION = Path(
    "supabase/migrations/202607300002_add_step10_asset_destinations.sql"
)
B2_REVIEWED_SHA256 = (
    "92531a14d45bdf7e6569c1966d17ff95416a408344940a2555fa39fcf89e0758"
)
ROOT = "1CdmowWV5TAk5R9D5yl2cOT8Plx3ihZgl"
HASH = "a" * 64


def source_row(source_id: str, asset_hash: str = HASH) -> dict:
    return {
        "id": source_id,
        "source_folder_id": str(uuid4()),
        "google_file_id": "google-id",
        "file_name": "private-name.jpg",
        "mime_type": "image/jpeg",
        "file_extension": "jpg",
        "size_bytes": 12,
        "decision": "TAKE",
        "processing_status": "READY",
        "hash_status": "HASHED",
        "hash_algorithm": "SHA-256",
        "content_sha256": asset_hash,
        "trashed": False,
        "is_missing": False,
        "access_status": "ACCESSIBLE",
        "hash_drive_modified_at": "2026-07-30T00:00:00Z",
        "hash_drive_version": "7",
        "hash_completed_at": "2026-07-30T00:01:00Z",
    }


class CorrectiveMigrationStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = CORRECTIVE_MIGRATION.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_b2_migration_is_unchanged(self):
        self.assertEqual(
            hashlib.sha256(B2_MIGRATION.read_bytes()).hexdigest(),
            B2_REVIEWED_SHA256,
        )

    def test_transaction_and_no_automatic_initialization(self):
        self.assertTrue(self.lower.startswith("begin;"))
        self.assertTrue(self.lower.rstrip().endswith("commit;"))
        self.assertNotIn("insert into public.asset_destinations", self.lower)
        self.assertNotIn("update public.source_files", self.lower)
        self.assertNotIn("update public.assets", self.lower)
        self.assertNotIn("update public.asset_sources", self.lower)

    def test_null_empty_and_exact_allowlist_contract(self):
        self.assertIn(
            "requested_asset_destination_ids uuid[] default null",
            self.lower,
        )
        self.assertIn(
            "requested_asset_destination_ids is null", self.lower
        )
        self.assertIn(
            "candidate_source.id = any(requested_asset_destination_ids)",
            self.lower,
        )
        # PostgreSQL `id = ANY('{}'::uuid[])` is false, so an empty array
        # admits no candidates while NULL preserves the unscoped path.
        self.assertIn(
            "requested_destination_folder_id text default null",
            self.lower,
        )
        self.assertIn(
            "candidate_source.destination_folder_id",
            self.lower,
        )

    def test_allowlist_does_not_bypass_safety_predicates(self):
        for token in (
            "upload_attempt_count < 5",
            "next_retry_at <= now()",
            "claim_expires_at <= now()",
            "requested_limit between 1 and 100",
            "requested_lease_seconds between 30 and 3600",
            "nullif(btrim(requested_claim_owner), '') is not null",
            "for update skip locked",
        ):
            self.assertIn(token, self.lower)
        self.assertIn(
            "candidate_source.upload_status in (\n"
            "          'not_started',\n"
            "          'queued',\n"
            "          'failed_retryable'",
            self.lower,
        )
        for terminal in (
            "verified",
            "failed_permanent",
            "source_changed",
            "source_not_found",
            "source_access_denied",
            "destination_access_denied",
            "destination_conflict",
            "manual_review_required",
        ):
            self.assertNotIn(
                f"candidate_source.upload_status = '{terminal}'",
                self.lower,
            )

    def test_deterministic_order_and_expired_recovery(self):
        self.assertIn("case candidate_source.upload_status", self.lower)
        self.assertIn("candidate_source.created_at", self.lower)
        self.assertIn("candidate_source.id", self.lower)
        self.assertIn("'claim_recovered'", self.lower)
        self.assertIn(
            "claimed.previous_status in ('claimed', 'uploading')",
            self.lower,
        )

    def test_success_only_audit_contract(self):
        for event_type in (
            "lifecycle_initialized",
            "claim_renewed",
            "claim_released",
            "claim_recovered",
        ):
            self.assertIn(f"'{event_type}'", self.lower)
        self.assertIn("if renewed then", self.lower)
        self.assertIn("if released then", self.lower)
        self.assertIn("after insert on public.asset_destinations", self.lower)
        self.assertNotIn("authorization", self.lower)
        self.assertNotIn("access_token", self.lower)
        self.assertNotIn("refresh_token", self.lower)

    def test_permissions_and_fixed_search_paths(self):
        self.assertGreaterEqual(self.lower.count("security invoker"), 4)
        self.assertGreaterEqual(self.lower.count("set search_path = ''"), 4)
        self.assertIn(
            "grant execute on function public.claim_asset_destinations",
            self.lower,
        )
        self.assertIn(
            "to service_role", self.lower
        )
        self.assertIn(
            "from public, anon, authenticated", self.lower
        )

    def test_only_narrow_old_signature_drop(self):
        self.assertIn(
            "drop function if exists public.claim_asset_destinations",
            self.lower,
        )
        self.assertNotIn("drop table", self.lower)
        self.assertNotIn("truncate", self.lower)
        self.assertNotIn("delete from", self.lower)
        self.assertNotIn("alter table public.source_files", self.lower)
        self.assertNotIn("alter table public.assets", self.lower)
        self.assertNotIn("alter table public.asset_sources", self.lower)

    def test_worker_rpc_signature_agreement(self):
        source = inspect.getsource(SupabaseStep10Repository.claim_batch)
        self.assertIn("allowed_ids", source)
        self.assertIn("requested_asset_destination_ids", source)
        self.assertIn("requested_destination_folder_id", source)
        self.assertIn("requested_asset_destination_ids", self.lower)


class InitializerEvidenceTests(unittest.TestCase):
    def test_source_hash_evidence_and_snapshot_are_populated(self):
        asset_id = str(uuid4())
        source_id = str(uuid4())
        values = prepare_lifecycle_initialization(
            [{"id": asset_id, "content_hash": HASH, "metadata": {}}],
            [{"asset_id": asset_id, "source_file_id": source_id}],
            [source_row(source_id)],
            ROOT,
        )
        self.assertEqual(len(values), 1)
        value = values[0]
        self.assertEqual(value["upload_status"], "NOT_STARTED")
        self.assertEqual(
            value["verification_level"], "SOURCE_HASH_VERIFIED"
        )
        self.assertEqual(value["source_sha256"], HASH)
        self.assertEqual(value["expected_bytes"], 12)
        self.assertEqual(value["upload_attempt_count"], 0)
        snapshot = value["source_metadata_snapshot"]
        self.assertEqual(snapshot["hash_algorithm"], "SHA-256")
        self.assertEqual(snapshot["expected_bytes"], 12)
        self.assertEqual(snapshot["drive_version"], "7")
        self.assertEqual(snapshot["google_file_id"], "google-id")
        self.assertEqual(snapshot["hash_status"], "HASHED")
        self.assertEqual(
            snapshot["hash_completed_at"],
            "2026-07-30T00:01:00Z",
        )
        self.assertNotIn("file_name", snapshot)
        self.assertNotIn("content_sha256", snapshot)

    def test_initializer_is_deterministic_and_idempotent_input(self):
        asset_id = str(uuid4())
        source_id = str(uuid4())
        args = (
            [{"id": asset_id, "content_hash": HASH, "metadata": {}}],
            [{"asset_id": asset_id, "source_file_id": source_id}],
            [source_row(source_id)],
            ROOT,
        )
        self.assertEqual(
            prepare_lifecycle_initialization(*args),
            prepare_lifecycle_initialization(*args),
        )


class RepositoryScopedClaimTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.rpc.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        self.repository = SupabaseStep10Repository(self.client)

    def payload(self):
        return self.client.rpc.call_args.args[1]

    def test_null_allowlist_preserves_unscoped_behavior(self):
        self.repository.claim_batch("worker", 3, 30, None)
        self.assertIsNone(
            self.payload()["requested_asset_destination_ids"]
        )

    def test_empty_allowlist_is_sent_as_empty(self):
        self.repository.claim_batch("worker", 3, 30, [])
        self.assertEqual(
            self.payload()["requested_asset_destination_ids"], []
        )

    def test_exact_three_allowlist_is_sent_without_other_rows(self):
        identifiers = [str(uuid4()) for _ in range(3)]
        self.repository.claim_batch(
            "worker", 3, 30, identifiers, ROOT
        )
        self.assertEqual(
            self.payload()["requested_asset_destination_ids"],
            identifiers,
        )
        self.assertEqual(
            self.payload()["requested_destination_folder_id"],
            ROOT,
        )

    def test_invalid_allowlist_id_is_rejected_before_rpc(self):
        with self.assertRaises(ValueError):
            self.repository.claim_batch("worker", 1, 30, ["invalid"])
        self.client.rpc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
