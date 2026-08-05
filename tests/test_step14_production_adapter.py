from pathlib import Path
from types import SimpleNamespace
import unittest

from kdi_media.incremental_sync import DriveMetadata, FileClassification
from kdi_media.production_sync_adapter import (
    AdapterOutcome,
    AdapterRequest,
    ProductionSyncAdapter,
)
from kdi_media.step10_upload import RetryableTransferError


class HarnessAdapter(ProductionSyncAdapter):
    def __init__(self, *, decision="TAKE", reused=False, fail=None):
        self.decision_value = decision
        self.reused = reused
        self.fail = fail
        self.calls = []

    def _decision(self, request):
        self.calls.append("decision")
        return SimpleNamespace(
            automatic_decision=self.decision_value,
            reason_code=SimpleNamespace(value="UNSUPPORTED_EXTENSION"),
            rule_version="test-rule",
        )

    def _persist_skip(self, request, reason):
        self.calls.append(("skip", reason))

    def _prepare_take(self, request, rule_version):
        self.calls.append(("prepare", request.classification.value))
        return {"asset_id": "old-asset"} if request.classification is FileClassification.CHANGED else None

    def _source(self, source_id):
        self.calls.append("source")
        return {**SOURCE, "id": source_id, "hash_status": "HASHED"}

    def _hash(self, request, source):
        self.calls.append("hash")
        if self.fail:
            raise self.fail
        return SimpleNamespace(content_sha256="a" * 64)

    def _canonicalize(self, request, source, prior_link):
        self.calls.append(("canonicalize", bool(prior_link)))
        return {"id": "asset-new"}, self.reused

    def _ensure_lifecycle(self, asset, source):
        self.calls.append("lifecycle")
        return {"id": "destination-row", "upload_status": "NOT_STARTED"}

    def _upload(self, request, asset, source, lifecycle):
        self.calls.append("upload")
        return {"outcome": "UPLOADED", "destination_google_file_id": "drive-destination"}

    def _complete_checkpoint(self, source_id):
        self.calls.append("complete")

    def _processing_failure(self, request, error, base, retryable):
        self.calls.append(("failure", retryable))
        return SimpleNamespace(outcome=AdapterOutcome.FAILED_FINAL)

    def _event(self, *args, **kwargs):
        self.calls.append("event")


SOURCE = {
    "id": "source-file",
    "source_folder_id": "folder",
    "google_file_id": "drive-file",
    "file_name": "small.jpg",
    "file_extension": "jpg",
    "mime_type": "image/jpeg",
    "size_bytes": 4,
    "relative_path": "",
    "metadata": {},
}
METADATA = DriveMetadata(
    "drive-file", "2026-08-05T00:00:00Z", 4, "image/jpeg", "b" * 32
)


def request(classification=FileClassification.NEW, *, dry_run=False):
    return AdapterRequest(
        "run-id", {"id": "folder"}, SOURCE, METADATA, classification, dry_run
    )


class ProductionAdapterTests(unittest.TestCase):
    def test_new_unique_path_hashes_canonicalizes_uploads_and_completes(self):
        adapter = HarnessAdapter()
        result = adapter.process(request())
        self.assertEqual(result.outcome, AdapterOutcome.UPLOADED_AND_VERIFIED)
        self.assertEqual(result.destination_id, "drive-destination")
        self.assertEqual(result.counters["unique_assets_created"], 1)
        self.assertEqual(result.counters["uploaded_files"], 1)
        self.assertEqual(
            adapter.calls,
            ["decision", ("prepare", "NEW"), "source", "hash", "source",
             ("canonicalize", False), "lifecycle", "upload", "complete", "event"],
        )

    def test_existing_canonical_is_reused_without_destination_work(self):
        adapter = HarnessAdapter(reused=True)
        result = adapter.process(request())
        self.assertEqual(result.outcome, AdapterOutcome.REUSED_EXISTING_ASSET)
        self.assertEqual(result.counters["existing_assets_reused"], 1)
        self.assertNotIn("lifecycle", adapter.calls)
        self.assertNotIn("upload", adapter.calls)

    def test_changed_path_preserves_prior_link_context(self):
        adapter = HarnessAdapter()
        result = adapter.process(request(FileClassification.CHANGED))
        self.assertEqual(result.outcome, AdapterOutcome.UPLOADED_AND_VERIFIED)
        self.assertIn(("prepare", "CHANGED"), adapter.calls)
        self.assertIn(("canonicalize", True), adapter.calls)
        self.assertEqual(result.counters["changed_files"], 1)

    def test_skip_stops_before_hash(self):
        adapter = HarnessAdapter(decision="SKIP")
        result = adapter.process(request())
        self.assertEqual(result.outcome, AdapterOutcome.SKIPPED)
        self.assertEqual(result.reason, "UNSUPPORTED_EXTENSION")
        self.assertNotIn("hash", adapter.calls)

    def test_dry_run_does_not_mutate_or_hash(self):
        adapter = HarnessAdapter()
        result = adapter.process(request(dry_run=True))
        self.assertTrue(result.dry_run)
        self.assertEqual(result.reason, "WOULD_HASH_CANONICALIZE_AND_UPLOAD_OR_REUSE")
        self.assertEqual(adapter.calls, ["decision"])

    def test_failure_is_final_when_exception_is_not_retryable(self):
        adapter = HarnessAdapter(fail=RuntimeError("controlled"))
        result = adapter.process(request())
        self.assertEqual(result.outcome, AdapterOutcome.FAILED_FINAL)
        self.assertIn(("failure", False), adapter.calls)

    def test_retryable_step10_failure_is_classified_for_retry(self):
        adapter = HarnessAdapter(fail=RetryableTransferError("controlled transient"))
        result = adapter.process(request())
        self.assertEqual(result.outcome, AdapterOutcome.FAILED_FINAL)
        self.assertIn(("failure", True), adapter.calls)

    def test_non_new_or_changed_returns_unchanged(self):
        adapter = HarnessAdapter()
        result = adapter.process(request(FileClassification.UNCHANGED))
        self.assertEqual(result.outcome, AdapterOutcome.UNCHANGED)
        self.assertEqual(adapter.calls, [])

    def test_verified_lifecycle_is_crash_recovery_short_circuit(self):
        adapter = ProductionSyncAdapter.__new__(ProductionSyncAdapter)
        result = adapter._upload(
            request(), {"id": "asset"}, SOURCE,
            {"id": "lifecycle", "upload_status": "VERIFIED", "destination_google_file_id": "existing-drive-id"},
        )
        self.assertEqual(result["outcome"], "SKIPPED_VERIFIED")
        self.assertEqual(result["destination_google_file_id"], "existing-drive-id")

    def test_persisted_hash_resume_does_not_read_content_again(self):
        adapter = ProductionSyncAdapter.__new__(ProductionSyncAdapter)
        result = adapter._hash(request(), {
            "hash_status": "HASHED", "hash_algorithm": "SHA-256",
            "content_sha256": "c" * 64,
        })
        self.assertEqual(result.content_sha256, "c" * 64)
        self.assertTrue(result.persisted)


if __name__ == "__main__":
    unittest.main()
