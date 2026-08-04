"""Checkpointed Steps 5-8 orchestration for registered source folders."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
import sys
from time import sleep
from typing import Any, Callable, Mapping, Protocol
from uuid import UUID


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kdi_media.rules import FileRuleInput, evaluate_file  # noqa: E402
from kdi_media.step6_inventory import (  # noqa: E402
    build_scan_run_payload,
    build_source_file_payloads,
    calculate_report_sha256,
    cross_validate_step6_csv,
    parse_step6_json,
)
from scripts.preview_step8_supabase import build_preview  # noqa: E402
from scripts.verify_google_drive_recursive import (  # noqa: E402
    write_recursive_scan_reports,
)


REPORT_ROOT = PROJECT_ROOT / "tmp" / "multi-source"
BATCH_SIZE = 100
RETRY_DELAYS = (1, 2, 4, 8, 16)
MAX_CONCURRENT_SOURCES = 2


class SourceStage(StrEnum):
    REGISTERED = "REGISTERED"
    ACCESS_VERIFIED = "ACCESS_VERIFIED"
    INACCESSIBLE = "INACCESSIBLE"
    SCANNING = "SCANNING"
    SCAN_COMPLETED = "SCAN_COMPLETED"
    INVENTORY_IMPORTED = "INVENTORY_IMPORTED"
    RULES_APPLIED = "RULES_APPLIED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


FINAL_STAGES = {
    SourceStage.COMPLETED,
    SourceStage.COMPLETED_WITH_ERRORS,
    SourceStage.INACCESSIBLE,
    SourceStage.FAILED,
}


class PermanentSourceError(RuntimeError):
    pass


class PermissionSourceError(PermanentSourceError):
    pass


class AuthenticationSourceError(PermanentSourceError):
    pass


class TransientSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegisteredSource:
    source_folder_id: str
    google_folder_id: str
    source_name: str
    active: bool


@dataclass
class SourceCheckpoint:
    source_folder_id: str
    google_folder_id: str
    current_stage: str
    timestamp: str
    report_paths: dict[str, str] = field(default_factory=dict)
    scan_run_id: str | None = None
    counts: dict[str, Any] = field(default_factory=dict)
    failure_category: str | None = None


@dataclass(frozen=True)
class SourceOutcome:
    source_folder_id: str
    stage: SourceStage
    counts: Mapping[str, Any]
    resumed: bool = False


class SourceBackend(Protocol):
    def verify_access(self, source: RegisteredSource) -> None:
        ...

    def scan(
        self,
        source: RegisteredSource,
        report_directory: Path,
    ) -> tuple[Path, Path, dict[str, Any]]:
        ...

    def import_inventory(
        self,
        source: RegisteredSource,
        json_path: Path,
        csv_path: Path,
    ) -> dict[str, Any]:
        ...

    def apply_rules(self, source: RegisteredSource) -> dict[str, Any]:
        ...

    def reconcile(
        self,
        source: RegisteredSource,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        ...


class CheckpointStore:
    def __init__(self, root: Path = REPORT_ROOT) -> None:
        self.root = root

    def source_directory(self, source: RegisteredSource) -> Path:
        return self.root / source.google_folder_id

    def load(self, source: RegisteredSource) -> SourceCheckpoint | None:
        path = self.source_directory(source) / "checkpoint.json"
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            checkpoint = SourceCheckpoint(**raw)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
            raise PermanentSourceError("Checkpoint is invalid")
        if (
            checkpoint.source_folder_id != source.source_folder_id
            or checkpoint.google_folder_id != source.google_folder_id
        ):
            raise PermanentSourceError("Checkpoint identity mismatch")
        return checkpoint

    def save(self, checkpoint: SourceCheckpoint) -> None:
        directory = self.root / checkpoint.google_folder_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "checkpoint.json"
        temporary = directory / "checkpoint.json.tmp"
        temporary.write_text(
            json.dumps(asdict(checkpoint), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(target)

    def write_summary(
        self,
        source: RegisteredSource,
        outcome: SourceOutcome,
    ) -> Path:
        directory = self.source_directory(source)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = _timestamp()
        path = directory / f"processing-summary-{stamp}.json"
        path.write_text(
            json.dumps(
                {
                    "source_folder_id": source.source_folder_id,
                    "google_folder_id": source.google_folder_id,
                    "stage": outcome.stage.value,
                    "counts": dict(outcome.counts),
                    "timestamp": _now(),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return path

    def write_error(
        self,
        source: RegisteredSource,
        *,
        category: str,
    ) -> Path:
        directory = self.source_directory(source)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"error-{_timestamp()}.json"
        path.write_text(
            json.dumps(
                {"failure_category": category, "timestamp": _now()},
                indent=2,
            ),
            encoding="utf-8",
        )
        return path


class MultiSourceOrchestrator:
    def __init__(
        self,
        backend: SourceBackend,
        *,
        checkpoints: CheckpointStore,
        continue_on_error: bool,
        retry_failed: bool,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.backend = backend
        self.checkpoints = checkpoints
        self.continue_on_error = continue_on_error
        self.retry_failed = retry_failed
        self.sleeper = sleeper

    def process_source(self, source: RegisteredSource) -> SourceOutcome:
        if not source.active:
            return self._finish(
                source, SourceStage.FAILED, {}, "inactive_source"
            )
        checkpoint = self.checkpoints.load(source)
        if checkpoint is not None:
            stage = SourceStage(checkpoint.current_stage)
            if stage in {
                SourceStage.COMPLETED,
                SourceStage.COMPLETED_WITH_ERRORS,
            }:
                return SourceOutcome(
                    source.source_folder_id,
                    stage,
                    checkpoint.counts,
                    resumed=True,
                )
            if stage in {SourceStage.FAILED, SourceStage.INACCESSIBLE}:
                if not self.retry_failed:
                    return SourceOutcome(
                        source.source_folder_id,
                        stage,
                        checkpoint.counts,
                        resumed=True,
                    )

        resume_stage: SourceStage | None = None
        context: dict[str, Any] = {}
        if checkpoint is not None:
            resume_stage = SourceStage(checkpoint.current_stage)
            context.update(checkpoint.counts)
            context["report_paths"] = checkpoint.report_paths
            context["scan_run_id"] = checkpoint.scan_run_id

        try:
            reusable = _reusable_reports(context.get("report_paths"))
            if reusable is None:
                self._checkpoint(source, SourceStage.REGISTERED, context)
                self._retry(
                    lambda: self.backend.verify_access(source),
                    retry_permanent=False,
                )
                self._checkpoint(
                    source, SourceStage.ACCESS_VERIFIED, context
                )
                self._checkpoint(source, SourceStage.SCANNING, context)
                json_path, csv_path, scan_counts = self._retry(
                    lambda: self.backend.scan(
                        source, self.checkpoints.source_directory(source)
                    ),
                    retry_permanent=False,
                )
                context.update(scan_counts)
                context["report_paths"] = {
                    "json": str(json_path),
                    "csv": str(csv_path),
                }
                self._checkpoint(
                    source, SourceStage.SCAN_COMPLETED, context
                )
            else:
                json_path, csv_path = reusable

            if resume_stage not in {
                SourceStage.INVENTORY_IMPORTED,
                SourceStage.RULES_APPLIED,
            }:
                import_result = self._retry(
                    lambda: self.backend.import_inventory(
                        source, json_path, csv_path
                    ),
                    retry_permanent=False,
                )
                context.update(import_result)
                self._checkpoint(
                    source, SourceStage.INVENTORY_IMPORTED, context
                )

            if resume_stage != SourceStage.RULES_APPLIED:
                rule_counts = self._retry(
                    lambda: self.backend.apply_rules(source),
                    retry_permanent=False,
                )
                context.update(rule_counts)
                self._checkpoint(
                    source, SourceStage.RULES_APPLIED, context
                )

            reconciliation = self._retry(
                lambda: self.backend.reconcile(source, context),
                retry_permanent=False,
            )
            context.update(reconciliation)
            final = (
                SourceStage.COMPLETED_WITH_ERRORS
                if int(context.get("errors", 0)) > 0
                else SourceStage.COMPLETED
            )
            return self._finish(source, final, context)
        except PermissionSourceError:
            return self._finish(
                source, SourceStage.INACCESSIBLE, context, "permission"
            )
        except AuthenticationSourceError:
            return self._finish(
                source, SourceStage.FAILED, context, "authentication"
            )
        except Exception as exc:
            category = (
                "transient_exhausted"
                if _is_transient(exc)
                else "processing_failure"
            )
            return self._finish(
                source, SourceStage.FAILED, context, category
            )

    def process_many(
        self,
        sources: list[RegisteredSource],
        *,
        max_concurrent_sources: int,
    ) -> list[SourceOutcome]:
        if not 1 <= max_concurrent_sources <= MAX_CONCURRENT_SOURCES:
            raise ValueError("max concurrency must be between 1 and 2")
        if max_concurrent_sources == 1:
            outcomes = []
            for source in sources:
                outcome = self.process_source(source)
                outcomes.append(outcome)
                if (
                    outcome.stage
                    in {SourceStage.FAILED, SourceStage.INACCESSIBLE}
                    and not self.continue_on_error
                ):
                    break
            return outcomes

        outcomes_by_id: dict[str, SourceOutcome] = {}
        with ThreadPoolExecutor(max_workers=max_concurrent_sources) as pool:
            futures = {
                pool.submit(self.process_source, source): source
                for source in sources
            }
            for future in as_completed(futures):
                outcome = future.result()
                outcomes_by_id[outcome.source_folder_id] = outcome
        return [
            outcomes_by_id[source.source_folder_id]
            for source in sources
            if source.source_folder_id in outcomes_by_id
        ]

    def _retry(
        self,
        operation: Callable[[], Any],
        *,
        retry_permanent: bool,
    ) -> Any:
        attempts = 0
        while True:
            try:
                return operation()
            except Exception as exc:
                if (
                    isinstance(exc, PermanentSourceError)
                    and not retry_permanent
                ) or not _is_transient(exc):
                    raise
                if attempts >= len(RETRY_DELAYS):
                    raise
                self.sleeper(RETRY_DELAYS[attempts])
                attempts += 1

    def _checkpoint(
        self,
        source: RegisteredSource,
        stage: SourceStage,
        context: Mapping[str, Any],
        failure_category: str | None = None,
    ) -> None:
        report_paths = dict(context.get("report_paths") or {})
        counts = {
            key: value
            for key, value in context.items()
            if key not in {"report_paths", "scan_run_id"}
        }
        self.checkpoints.save(
            SourceCheckpoint(
                source_folder_id=source.source_folder_id,
                google_folder_id=source.google_folder_id,
                current_stage=stage.value,
                timestamp=_now(),
                report_paths=report_paths,
                scan_run_id=context.get("scan_run_id"),
                counts=counts,
                failure_category=failure_category,
            )
        )

    def _finish(
        self,
        source: RegisteredSource,
        stage: SourceStage,
        context: Mapping[str, Any],
        failure_category: str | None = None,
    ) -> SourceOutcome:
        self._checkpoint(
            source, stage, context, failure_category=failure_category
        )
        if failure_category:
            self.checkpoints.write_error(
                source, category=failure_category
            )
        outcome = SourceOutcome(
            source.source_folder_id,
            stage,
            {
                key: value
                for key, value in context.items()
                if key not in {"report_paths", "scan_run_id"}
            },
        )
        self.checkpoints.write_summary(source, outcome)
        return outcome


class ProductionBackend:
    """Existing-component adapter. Used only by an explicitly selected mode."""

    def __init__(self, store: Any, *, execute: bool) -> None:
        self.store = store
        self.execute = execute
        self._service: Any = None
        self._dry_rows: dict[str, list[dict[str, Any]]] = {}
        self._scan_status: dict[str, str] = {}

    def verify_access(self, source: RegisteredSource) -> None:
        from kdi_media.google_drive import (
            GoogleDriveAccessError,
            GoogleDriveAuthenticationError,
            create_readonly_drive_service,
            verify_folder_access,
        )

        try:
            self._service = self._service or create_readonly_drive_service()
            verify_folder_access(self._service, source.google_folder_id)
        except GoogleDriveAuthenticationError as exc:
            raise AuthenticationSourceError("Authentication failed") from exc
        except GoogleDriveAccessError as exc:
            raise PermissionSourceError("Folder is inaccessible") from exc

    def scan(
        self,
        source: RegisteredSource,
        report_directory: Path,
    ) -> tuple[Path, Path, dict[str, Any]]:
        from kdi_media.google_drive import scan_folder_recursive

        report = scan_folder_recursive(
            self._service, source.google_folder_id
        )
        json_path, csv_path = write_recursive_scan_reports(
            report, report_root=report_directory
        )
        summary = asdict(report.summary)
        return json_path, csv_path, {
            "folders_scanned": summary["folders_scanned"],
            "total_items": summary["total_items_discovered"],
            "files_discovered": summary["total_files_found"],
            "inaccessible": summary["inaccessible_items"],
            "errors": summary["errors"],
        }

    def import_inventory(
        self,
        source: RegisteredSource,
        json_path: Path,
        csv_path: Path,
    ) -> dict[str, Any]:
        report = parse_step6_json(
            json_path, expected_root_id=source.google_folder_id
        )
        cross_validate_step6_csv(report, csv_path)
        report_fingerprint = calculate_report_sha256(json_path)
        existing = None
        if self.execute:
            existing = self.store.find_scan_run_by_report_sha256(
                source_folder_id=source.source_folder_id,
                report_sha256=report_fingerprint,
                import_type="MULTI_SOURCE_INVENTORY",
                test_batch=False,
            )
        if existing is not None and existing.get("status") == "COMPLETED":
            self._scan_status[source.source_folder_id] = "COMPLETED"
            return {
                "scan_run_id": existing["id"],
                "scan_run_status": "COMPLETED",
                "report_fingerprint": report_fingerprint,
            }

        scan_payload = build_scan_run_payload(
            report, source_folder_id=source.source_folder_id
        )
        scan_payload["metadata"].update(
            {
                "import_type": "MULTI_SOURCE_INVENTORY",
                "test_batch": False,
            }
        )
        scan_run_id = "dry-run"
        if self.execute:
            scan_run = self.store.create_scan_run_from_payload(scan_payload)
            scan_run_id = scan_run["id"]
        rows = build_source_file_payloads(
            report,
            source_folder_id=source.source_folder_id,
            scan_run_id=scan_run_id,
        )
        rows = [_apply_canonical_rule(row) for row in rows]
        self._dry_rows[source.source_folder_id] = rows
        if self.execute:
            try:
                self.store.batch_upsert_source_files(
                    rows, batch_size=BATCH_SIZE
                )
                taken = sum(row["decision"] == "TAKE" for row in rows)
                skipped = sum(row["decision"] == "SKIP" for row in rows)
                self.store.finalize_scan_run_from_payload(
                    scan_run_id,
                    {
                        "status": "COMPLETED",
                        "completed_at": report.generated_at_utc,
                        "files_discovered": len(rows),
                        "files_taken": taken,
                        "files_skipped": skipped,
                        "files_uploaded": 0,
                        "duplicates_found": 0,
                        "files_failed": 0,
                    },
                )
            except Exception:
                self.store.finalize_scan_run_from_payload(
                    scan_run_id,
                    {
                        "status": "FAILED",
                        "completed_at": _now(),
                        "files_failed": 1,
                        "error_message": "Multi-source inventory import failed",
                    },
                )
                raise
        self._scan_status[source.source_folder_id] = (
            "COMPLETED" if self.execute else "DRY_RUN"
        )
        return {
            "scan_run_id": scan_run_id,
            "scan_run_status": self._scan_status[source.source_folder_id],
            "report_fingerprint": report_fingerprint,
        }

    def apply_rules(self, source: RegisteredSource) -> dict[str, Any]:
        rows = (
            self.store.read_step8_preview_rows(source.source_folder_id)
            if self.execute
            else self._dry_rows[source.source_folder_id]
        )
        preview = build_preview(rows)
        if preview.changed:
            raise PermanentSourceError(
                "Imported rows do not match canonical Step 8 decisions"
            )
        return {
            "take_ready": preview.current_take_ready,
            "skip_skipped": preview.current_skip_skipped,
        }

    def reconcile(
        self,
        source: RegisteredSource,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        rows = (
            self.store.read_step8_preview_rows(source.source_folder_id)
            if self.execute
            else self._dry_rows[source.source_folder_id]
        )
        preview = build_preview(rows)
        return {
            "source_files_total": preview.total_rows,
            "take_ready": preview.current_take_ready,
            "skip_skipped": preview.current_skip_skipped,
            "inaccessible": preview.inaccessible,
            "duplicate_source_identities": preview.duplicate_identities,
            "folder_rows": preview.folder_rows,
            "scan_run_status": self._scan_status.get(
                source.source_folder_id,
                str(context.get("scan_run_status") or "UNKNOWN"),
            ),
            "assets_created": 0,
            "asset_sources_created": 0,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process registered sources through Steps 5-8."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--source-folder-id", type=_uuid)
    selection.add_argument("--all-active", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--max-concurrent-sources", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2
    if not 1 <= args.max_concurrent_sources <= MAX_CONCURRENT_SOURCES:
        print("--max-concurrent-sources must be 1 or 2", file=sys.stderr)
        return 2
    try:
        from dotenv import load_dotenv
        from kdi_media.supabase_store import SupabaseStore
        import os

        load_dotenv(PROJECT_ROOT / ".env")
        url = _required_environment(os.environ, "SUPABASE_URL")
        key = _required_environment(
            os.environ, "SUPABASE_SERVICE_ROLE_KEY"
        )
        store = SupabaseStore(url, key)
        raw_sources = _select_sources(store, args)
        sources = [_registered_source(row) for row in raw_sources]
        backend = ProductionBackend(store, execute=args.execute)
        orchestrator = MultiSourceOrchestrator(
            backend,
            checkpoints=CheckpointStore(),
            continue_on_error=args.continue_on_error,
            retry_failed=args.retry_failed,
        )
        outcomes = orchestrator.process_many(
            sources,
            max_concurrent_sources=args.max_concurrent_sources,
        )
    except Exception:
        print(
            "Multi-source processing failed without exposing source or "
            "connection data",
            file=sys.stderr,
        )
        return 1
    for outcome in outcomes:
        print(f"Source result: {outcome.stage.value}")
    print(f"Sources processed: {len(outcomes)}")
    return 0 if all(
        outcome.stage
        in {SourceStage.COMPLETED, SourceStage.COMPLETED_WITH_ERRORS}
        for outcome in outcomes
    ) else 1


def _select_sources(store: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.source_folder_id:
        row = store.get_source_folder_by_id(str(args.source_folder_id))
        if row is None:
            raise PermanentSourceError("Registered source was not found")
        return [row]
    return store.list_active_source_folders(limit=args.limit)


def _registered_source(row: Mapping[str, Any]) -> RegisteredSource:
    return RegisteredSource(
        source_folder_id=str(row["id"]),
        google_folder_id=str(row["google_folder_id"]),
        source_name=str(row["source_name"]),
        active=row.get("active") is True,
    )


def _apply_canonical_rule(row: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(row.get("metadata") or {})
    result = evaluate_file(
        FileRuleInput(
            file_name=row.get("file_name"),
            mime_type=row.get("mime_type"),
            file_extension=row.get("file_extension"),
            size_bytes=row.get("size_bytes"),
            relative_path=row.get("relative_path"),
            accessibility_status=metadata.get(
                "step6_accessibility_status", "accessible"
            ),
            trashed=row.get("trashed"),
            is_missing=row.get("is_missing"),
            is_folder=False,
        )
    )
    metadata.update(
        {
            "step8_rule_version": result.rule_version,
            "step8_reason_code": result.reason_code.value,
            "accepted_for_ai_analysis": result.accepted_for_ai_analysis,
            "step8_evaluated_at": _now(),
        }
    )
    return {
        **row,
        "decision": result.automatic_decision,
        "processing_status": result.target_processing_status,
        "skip_reason": (
            None
            if result.automatic_decision == "TAKE"
            else result.reason_code.value
        ),
        "metadata": metadata,
    }


def _reusable_reports(
    paths: Any,
) -> tuple[Path, Path] | None:
    if not isinstance(paths, Mapping):
        return None
    json_path = Path(str(paths.get("json") or ""))
    csv_path = Path(str(paths.get("csv") or ""))
    if json_path.is_file() and csv_path.is_file():
        return json_path, csv_path
    return None


def _is_transient(exc: Exception) -> bool:
    return isinstance(
        exc, (TransientSourceError, TimeoutError, ConnectionError)
    )


def _required_environment(
    environment: Mapping[str, str],
    name: str,
) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise RuntimeError("Required Supabase configuration is missing")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Source folder ID must be a UUID") from exc


if __name__ == "__main__":
    raise SystemExit(main())
