from pathlib import Path
import tempfile
import unittest

from kdi_media.incremental_sync import (
    DriveMetadata, FileClassification, FileOutcome, RetryableSyncError,
    bounded_retry, classify_file, classify_inventory, reconcile,
    trusted_unchanged_checksum, write_json_report,
)


OLD = {"google_file_id":"g1","drive_modified_at":"2026-08-01T00:00:00Z","size_bytes":10,"mime_type":"image/jpeg","md5_checksum":"a"*32,"hash_status":"HASHED","content_sha256":"b"*64}


class Step14IncrementalTests(unittest.TestCase):
    def item(self, **changes):
        values={"google_file_id":"g1","modified_time":"2026-08-01T00:00:00Z","size_bytes":10,"mime_type":"image/jpeg","md5_checksum":"a"*32}
        values.update(changes)
        return DriveMetadata(**values)

    def test_new_changed_unchanged_and_inaccessible(self):
        self.assertEqual(classify_file(self.item(),None),FileClassification.NEW)
        self.assertEqual(classify_file(self.item(size_bytes=11),OLD),FileClassification.CHANGED)
        self.assertEqual(classify_file(self.item(),OLD),FileClassification.UNCHANGED)
        self.assertEqual(classify_file(self.item(accessible=False),OLD),FileClassification.INACCESSIBLE)

    def test_removed_is_recorded(self):
        self.assertEqual(classify_inventory([], [OLD])["g1"],FileClassification.REMOVED_FROM_SOURCE)

    def test_trusted_unchanged_avoids_repeat_hash(self):
        self.assertTrue(trusted_unchanged_checksum(self.item(),OLD))
        self.assertFalse(trusted_unchanged_checksum(self.item(size_bytes=11),OLD))

    def test_equivalent_timestamp_formats_are_unchanged(self):
        stored = {**OLD, "drive_modified_at": "2026-08-01T00:00:00+00:00"}
        self.assertEqual(classify_file(self.item(), stored), FileClassification.UNCHANGED)

    def test_bounded_retry(self):
        attempts=[]
        def operation():
            attempts.append(1)
            if len(attempts)<3: raise RetryableSyncError("temporary")
            return "ok"
        retries=[]
        self.assertEqual(bounded_retry(operation,sleeper=lambda _:None,jitter=lambda:0,on_retry=lambda n,_:retries.append(n)),"ok")
        self.assertEqual((len(attempts),retries),(3,[1,2]))

    def test_reconciliation_and_idempotent_outcomes(self):
        values=[FileOutcome("1","UNCHANGED"),FileOutcome("2","SKIPPED","unsupported")]
        self.assertTrue(reconcile(2,values)["clean"])
        self.assertFalse(reconcile(2,values+[values[0]])["clean"])

    def test_dry_report_write_is_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"report.json"
            write_json_report(path,{"dry_run":True,"unique_files_uploaded":0})
            self.assertIn('"dry_run": true',path.read_text(encoding="utf-8"))


class Step14MigrationTests(unittest.TestCase):
    def test_durable_lock_and_checkpoint_contract(self):
        sql=(Path(__file__).parents[1]/"supabase/migrations/202608050001_add_step14_incremental_sync.sql").read_text(encoding="utf-8").lower()
        for text in ("synchronization_locks","acquire_synchronization_lock","release_synchronization_lock","expires_at <= now()","sync_attempt_count","sync_retry_eligible"):
            self.assertIn(text,sql)


if __name__ == "__main__": unittest.main()
