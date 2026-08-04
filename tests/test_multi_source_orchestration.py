from __future__ import annotations

from collections import Counter
from pathlib import Path
import tempfile
import unittest

from scripts.process_registered_sources import (
    BATCH_SIZE,
    MAX_CONCURRENT_SOURCES,
    AuthenticationSourceError,
    CheckpointStore,
    MultiSourceOrchestrator,
    PermissionSourceError,
    RegisteredSource,
    SourceCheckpoint,
    SourceStage,
    TransientSourceError,
)


def source(number: int) -> RegisteredSource:
    return RegisteredSource(
        source_folder_id=f"source-{number}",
        google_folder_id=f"folder-{number}",
        source_name=f"Source {number}",
        active=True,
    )


class FakeBackend:
    def __init__(self) -> None:
        self.calls: Counter[tuple[str, str]] = Counter()
        self.failures: dict[tuple[str, str], list[Exception]] = {}

    def fail(self, stage: str, source_id: str, *errors: Exception) -> None:
        self.failures[(stage, source_id)] = list(errors)

    def _call(self, stage: str, item: RegisteredSource) -> None:
        key = (stage, item.source_folder_id)
        self.calls[key] += 1
        errors = self.failures.get(key, [])
        if errors:
            raise errors.pop(0)

    def verify_access(self, item: RegisteredSource) -> None:
        self._call("verify", item)

    def scan(self, item: RegisteredSource, report_directory: Path):
        self._call("scan", item)
        report_directory.mkdir(parents=True, exist_ok=True)
        json_path = report_directory / "recursive-test.json"
        csv_path = report_directory / "recursive-test.csv"
        json_path.write_text("{}", encoding="utf-8")
        csv_path.write_text("header\n", encoding="utf-8")
        return json_path, csv_path, {
            "folders_scanned": 1,
            "total_items": 1,
            "files_discovered": 1,
            "errors": 0,
        }

    def import_inventory(
        self, item: RegisteredSource, json_path: Path, csv_path: Path
    ):
        self._call("import", item)
        return {
            "scan_run_id": f"scan-{item.source_folder_id}",
            "scan_run_status": "COMPLETED",
            "report_fingerprint": "fingerprint",
        }

    def apply_rules(self, item: RegisteredSource):
        self._call("rules", item)
        return {"take_ready": 1, "skip_skipped": 0}

    def reconcile(self, item: RegisteredSource, context):
        self._call("reconcile", item)
        return {
            "source_files_total": 1,
            "duplicate_source_identities": 0,
            "folder_rows": 0,
            "assets_created": 0,
            "asset_sources_created": 0,
        }


class MultiSourceOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.checkpoints = CheckpointStore(Path(self.temporary.name))
        self.backend = FakeBackend()
        self.sleeps: list[float] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def orchestrator(
        self,
        *,
        continue_on_error: bool = True,
        retry_failed: bool = False,
    ) -> MultiSourceOrchestrator:
        return MultiSourceOrchestrator(
            self.backend,
            checkpoints=self.checkpoints,
            continue_on_error=continue_on_error,
            retry_failed=retry_failed,
            sleeper=self.sleeps.append,
        )

    def test_one_accessible_source_completes_with_checkpoint(self) -> None:
        item = source(1)
        outcome = self.orchestrator().process_source(item)
        self.assertEqual(outcome.stage, SourceStage.COMPLETED)
        checkpoint = self.checkpoints.load(item)
        self.assertEqual(
            checkpoint.current_stage, SourceStage.COMPLETED.value
        )
        self.assertEqual(checkpoint.scan_run_id, "scan-source-1")
        self.assertEqual(checkpoint.counts["source_files_total"], 1)

    def test_inaccessible_source_isolated_and_not_retried(self) -> None:
        item = source(1)
        self.backend.fail(
            "verify", item.source_folder_id, PermissionSourceError()
        )
        outcome = self.orchestrator().process_source(item)
        self.assertEqual(outcome.stage, SourceStage.INACCESSIBLE)
        self.assertEqual(
            self.backend.calls[("verify", item.source_folder_id)], 1
        )
        self.assertFalse(self.sleeps)

    def test_authentication_failure_stops_only_source(self) -> None:
        item = source(1)
        self.backend.fail(
            "verify", item.source_folder_id, AuthenticationSourceError()
        )
        outcome = self.orchestrator().process_source(item)
        self.assertEqual(outcome.stage, SourceStage.FAILED)
        self.assertEqual(
            self.checkpoints.load(item).failure_category, "authentication"
        )

    def test_scan_failure_and_supabase_import_failure_are_preserved(self) -> None:
        scan_item = source(1)
        import_item = source(2)
        self.backend.fail(
            "scan", scan_item.source_folder_id, RuntimeError()
        )
        self.backend.fail(
            "import", import_item.source_folder_id, RuntimeError()
        )
        outcomes = self.orchestrator().process_many(
            [scan_item, import_item], max_concurrent_sources=1
        )
        self.assertEqual(
            [outcome.stage for outcome in outcomes],
            [SourceStage.FAILED, SourceStage.FAILED],
        )
        self.assertFalse(
            self.checkpoints.source_directory(scan_item)
            .joinpath("recursive-test.json")
            .exists()
        )
        self.assertTrue(
            self.checkpoints.source_directory(import_item)
            .joinpath("recursive-test.json")
            .exists()
        )

    def test_continue_on_error_behavior(self) -> None:
        first, second = source(1), source(2)
        self.backend.fail("scan", first.source_folder_id, RuntimeError())
        outcomes = self.orchestrator(
            continue_on_error=True
        ).process_many([first, second], max_concurrent_sources=1)
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(outcomes[1].stage, SourceStage.COMPLETED)

        backend = FakeBackend()
        backend.fail("scan", first.source_folder_id, RuntimeError())
        stopped = MultiSourceOrchestrator(
            backend,
            checkpoints=CheckpointStore(
                Path(self.temporary.name) / "stopped"
            ),
            continue_on_error=False,
            retry_failed=False,
            sleeper=self.sleeps.append,
        ).process_many([first, second], max_concurrent_sources=1)
        self.assertEqual(len(stopped), 1)

    def test_resume_from_scan_checkpoint_reuses_reports(self) -> None:
        item = source(1)
        directory = self.checkpoints.source_directory(item)
        directory.mkdir(parents=True)
        json_path = directory / "existing.json"
        csv_path = directory / "existing.csv"
        json_path.write_text("{}", encoding="utf-8")
        csv_path.write_text("header\n", encoding="utf-8")
        self.checkpoints.save(
            SourceCheckpoint(
                source_folder_id=item.source_folder_id,
                google_folder_id=item.google_folder_id,
                current_stage=SourceStage.SCAN_COMPLETED.value,
                timestamp="2026-07-30T00:00:00+00:00",
                report_paths={
                    "json": str(json_path),
                    "csv": str(csv_path),
                },
            )
        )
        outcome = self.orchestrator().process_source(item)
        self.assertEqual(outcome.stage, SourceStage.COMPLETED)
        self.assertEqual(
            self.backend.calls[("verify", item.source_folder_id)], 0
        )
        self.assertEqual(
            self.backend.calls[("scan", item.source_folder_id)], 0
        )
        self.assertEqual(
            self.backend.calls[("import", item.source_folder_id)], 1
        )

    def test_transient_retry_uses_bounded_backoff(self) -> None:
        item = source(1)
        self.backend.fail(
            "verify",
            item.source_folder_id,
            TransientSourceError(),
            TransientSourceError(),
        )
        outcome = self.orchestrator().process_source(item)
        self.assertEqual(outcome.stage, SourceStage.COMPLETED)
        self.assertEqual(self.sleeps, [1, 2])
        self.assertEqual(
            self.backend.calls[("verify", item.source_folder_id)], 3
        )

    def test_completed_source_is_not_reprocessed_or_duplicated(self) -> None:
        item = source(1)
        first = self.orchestrator().process_source(item)
        calls = self.backend.calls.copy()
        second = self.orchestrator().process_source(item)
        self.assertEqual(first.stage, SourceStage.COMPLETED)
        self.assertTrue(second.resumed)
        self.assertEqual(self.backend.calls, calls)
        self.assertEqual(
            self.backend.calls[("import", item.source_folder_id)], 1
        )

    def test_source_and_report_folder_isolation(self) -> None:
        first, second = source(1), source(2)
        outcomes = self.orchestrator().process_many(
            [first, second], max_concurrent_sources=2
        )
        self.assertEqual(len(outcomes), 2)
        self.assertNotEqual(
            self.checkpoints.source_directory(first),
            self.checkpoints.source_directory(second),
        )
        for item in (first, second):
            self.assertTrue(
                self.checkpoints.source_directory(item)
                .joinpath("recursive-test.json")
                .is_file()
            )

    def test_batch_and_concurrency_limits(self) -> None:
        self.assertEqual(BATCH_SIZE, 100)
        self.assertEqual(MAX_CONCURRENT_SOURCES, 2)
        with self.assertRaisesRegex(ValueError, "between 1 and 2"):
            self.orchestrator().process_many(
                [source(1)], max_concurrent_sources=3
            )

    def test_import_uses_fingerprint_and_unique_batched_upsert_path(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "process_registered_sources.py"
        ).read_text(encoding="utf-8")
        self.assertIn("find_scan_run_by_report_sha256(", script)
        self.assertIn("batch_upsert_source_files(", script)
        self.assertIn("batch_size=BATCH_SIZE", script)
        self.assertIn("status\") == \"COMPLETED\"", script)

    def test_no_drive_writes_assets_or_direct_sql(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "process_registered_sources.py"
        ).read_text(encoding="utf-8").lower()
        for prohibited in (
            "copy_file(",
            "files().copy",
            "files().update",
            "files().delete",
            'table("assets")',
            'table("asset_sources")',
            "cursor.execute",
            "execute sql",
        ):
            self.assertNotIn(prohibited, script)


if __name__ == "__main__":
    unittest.main()
