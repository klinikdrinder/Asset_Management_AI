from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
import unittest


MIGRATION = Path(
    "supabase/migrations/"
    "202607310002_extend_step10_event_type_contract.sql"
)
VERIFICATION = Path(
    "supabase/verification/verify_step10_event_type_fix.sql"
)
UPLOAD_MODULE = Path("src/kdi_media/step10_upload.py")
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
}


def python_audit_events() -> tuple[str, ...]:
    tree = ast.parse(UPLOAD_MODULE.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "AUDIT_EVENT_TYPES"
                for target in node.targets
            )
        ):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("AUDIT_EVENT_TYPES was not found")


class Step10EventTypeMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()
        cls.verify = VERIFICATION.read_text(encoding="utf-8")
        cls.verify_lower = cls.verify.lower()
        block = re.search(
            r"step10_values constant text\[\] := array\[(.*?)\]::text\[\]",
            cls.sql,
            re.DOTALL,
        )
        assert block
        cls.migration_events = tuple(
            re.findall(r"'([A-Z][A-Z0-9_]*)'", block.group(1))
        )

    def test_forward_only_transaction(self):
        self.assertTrue(self.lower.startswith("begin;"))
        self.assertTrue(self.lower.rstrip().endswith("commit;"))
        self.assertNotIn("rollback;", self.lower)

    def test_all_prior_deployed_migrations_are_unchanged(self):
        for path, expected in DEPLOYED_HASHES.items():
            with self.subTest(path=path):
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected,
                )

    def test_step10_vocabulary_matches_python_registry_exactly(self):
        self.assertEqual(
            set(self.migration_events), set(python_audit_events())
        )
        self.assertEqual(len(self.migration_events), 18)

    def test_lifecycle_and_claim_events_are_added(self):
        for event in (
            "LIFECYCLE_INITIALIZED",
            "CLAIM_RENEWED",
            "CLAIM_RELEASED",
            "CLAIM_RECOVERED",
        ):
            self.assertIn(event, self.migration_events)

    def test_upload_and_verification_events_are_added(self):
        for event in (
            "UPLOAD_QUEUED",
            "UPLOAD_CLAIMED",
            "UPLOAD_STARTED",
            "UPLOAD_CREATED",
            "UPLOAD_RECOVERED",
            "UPLOAD_VERIFIED",
        ):
            self.assertIn(event, self.migration_events)

    def test_retry_failure_and_manual_review_events_are_added(self):
        for event in (
            "UPLOAD_FAILED",
            "UPLOAD_RETRY_SCHEDULED",
            "SOURCE_CHANGED",
            "SOURCE_NOT_FOUND",
            "SOURCE_ACCESS_DENIED",
            "DESTINATION_ACCESS_DENIED",
            "DESTINATION_CONFLICT",
            "MANUAL_REVIEW_REQUIRED",
        ):
            self.assertIn(event, self.migration_events)

    def test_existing_constraint_is_catalog_resolved(self):
        self.assertIn("pg_get_expr(", self.lower)
        self.assertIn(
            "constraint_row.conname = 'migration_events_event_type_check'",
            self.lower,
        )
        self.assertIn(
            "constraint_row.conkey", self.lower
        )
        self.assertIn(
            "array[event_type_attribute_number]::smallint[]",
            self.lower,
        )

    def test_missing_or_unvalidated_constraint_fails_closed(self):
        self.assertIn("constraint_row.convalidated", self.lower)
        self.assertIn(
            "expected strict migration_events_event_type_check was not found",
            self.lower,
        )

    def test_unsupported_expression_shape_fails_closed(self):
        self.assertIn("unsupported_remainder", self.lower)
        self.assertIn(
            "unsupported migration_events_event_type_check expression shape",
            self.lower,
        )

    def test_legacy_literals_are_extracted_and_retained(self):
        self.assertIn("legacy_values || step10_values", self.lower)
        self.assertIn(
            "array_agg(distinct value order by value)", self.lower
        )
        self.assertIn(
            "step10_preserved_legacy_event_types=", self.lower
        )

    def test_constraint_remains_strict_membership(self):
        self.assertIn(
            "check (event_type = any (array[%s]))", self.lower
        )
        self.assertNotIn("event_type is not null", self.lower)
        self.assertNotIn("drop column", self.lower)

    def test_drop_and_recreate_use_same_named_constraint(self):
        self.assertEqual(
            self.lower.count("drop constraint migration_events_event_type_check"),
            1,
        )
        self.assertIn(
            "add constraint migration_events_event_type_check",
            self.lower,
        )

    def test_idempotent_comment_preserves_original_legacy_set(self):
        self.assertIn(
            "if existing_comment like "
            "'step10_preserved_legacy_event_types=%'",
            self.lower,
        )
        self.assertIn("preserved_comment := existing_comment", self.lower)

    def test_status_fix_is_not_changed(self):
        self.assertNotIn(
            "set_step10_migration_event_legacy_status", self.lower
        )
        self.assertNotIn("migration_events_event_status_check", self.lower)
        self.assertNotIn("alter column status", self.lower)

    def test_lifecycle_and_rpc_contracts_are_not_changed(self):
        for token in (
            "asset_destinations",
            "claim_asset_destinations",
            "renew_asset_destination_claim",
            "release_asset_destination_claim",
        ):
            self.assertNotIn(f"function public.{token}", self.lower)
        self.assertNotIn("update public.asset_destinations", self.lower)

    def test_no_step9_data_or_contract_change(self):
        for table in ("source_files", "assets", "asset_sources"):
            self.assertNotIn(f"alter table public.{table}", self.lower)
            self.assertNotIn(f"update public.{table}", self.lower)
            self.assertNotIn(f"insert into public.{table}", self.lower)

    def test_no_drive_or_sensitive_payload_dependency(self):
        for token in (
            "google_drive",
            "oauth",
            "access_token",
            "refresh_token",
            "source_path",
            "file_name",
            "content_sha256",
            "patient",
        ):
            self.assertNotIn(token, self.lower)

    def test_verifier_requires_all_step10_and_legacy_values(self):
        self.assertIn(
            "required_step10_values || preserved_legacy_values",
            self.verify_lower,
        )
        self.assertIn(
            "required event types are missing", self.verify_lower
        )

    def test_verifier_proves_unknown_value_is_absent(self):
        self.assertIn(
            "step10_arbitrary_invalid_event", self.verify_lower
        )
        self.assertIn(
            "arbitrary event type is unexpectedly allowed",
            self.verify_lower,
        )

    def test_verifier_checks_strict_shape_and_status_helper(self):
        self.assertIn(
            "event_type check is not a strict membership constraint",
            self.verify_lower,
        )
        self.assertIn(
            "set_step10_migration_event_legacy_status",
            self.verify_lower,
        )
        self.assertIn(
            "migration_events_event_status_check", self.verify_lower
        )

    def test_verifier_is_read_only(self):
        for token in (
            "insert into",
            "update public.",
            "delete from",
            "truncate",
            "alter table",
            "drop constraint",
            "create table",
        ):
            self.assertNotIn(token, self.verify_lower)

    def test_verifier_checks_pre_b3_reconciliation(self):
        for value in (
            "source_file_count <> 886",
            "eligible_hashed_count <> 878",
            "asset_count <> 878",
            "relationship_count <> 878",
            "destination_count <> 0",
            "orphan_relationship_count <> 0",
        ):
            self.assertIn(value, self.verify_lower)

    def test_verifier_returns_required_marker_and_vocabulary(self):
        self.assertIn(
            "'step_10_event_type_fix_verified' as result",
            self.verify_lower,
        )
        self.assertIn(
            "preserved_legacy_vocabulary", self.verify_lower
        )
        self.assertIn(
            "deployed_event_type_contract", self.verify_lower
        )

    def test_atomicity_and_no_unconstrained_commit(self):
        drop_index = self.lower.index(
            "drop constraint migration_events_event_type_check"
        )
        add_index = self.lower.index(
            "add constraint migration_events_event_type_check"
        )
        commit_index = self.lower.rindex("commit;")
        self.assertLess(drop_index, add_index)
        self.assertLess(add_index, commit_index)
        self.assertEqual(self.lower.count("commit;"), 1)


if __name__ == "__main__":
    unittest.main()
