"""Production daily incremental synchronization runner for Step 14."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from .google_drive import FOLDER_CLASSIFICATION, RecursiveScanItem, scan_folder_recursive
from .incremental_sync import (
    DriveMetadata,
    FileClassification,
    FileOutcome,
    RunTotals,
    classify_inventory,
    reconcile,
    sanitize_error,
)
from .production_sync_adapter import AdapterRequest, AdapterResult, ProductionSyncAdapter


LOCK_NAME = "daily_incremental_sync"


class IncrementalSyncRunner:
    """Scan, classify, checkpoint, and delegate NEW/CHANGED processing."""

    STORED_COLUMNS = (
        "*,asset_sources(id,asset_id,relationship_type),"
        "asset_destinations(id,asset_id,destination_google_file_id,upload_status)"
    )

    def __init__(
        self,
        *,
        client: Any,
        source_service: Any,
        adapter_factory: Callable[[], ProductionSyncAdapter],
        report_root: Path,
    ) -> None:
        self.client = client
        self.source_service = source_service
        self.adapter_factory = adapter_factory
        self.report_root = report_root
        self._adapter: ProductionSyncAdapter | None = None

    def run(
        self,
        *,
        dry_run: bool,
        trigger: str,
        source_ids: Iterable[str] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        selected = set(source_ids or ())
        sources = self._sources(selected)
        started = _now()
        run_uuid = run_id or str(uuid4())
        report: dict[str, Any] = {
            "run_id": run_uuid,
            "run_type": "incremental_sync",
            "trigger_type": trigger,
            "dry_run": dry_run,
            "started_at": started,
            "status": "RUNNING",
            "sources": [],
            "totals": asdict(RunTotals()),
        }
        locked = False
        if not dry_run:
            self._create_run(run_uuid, trigger, len(sources), started)
            locked = self._lock(run_uuid)
            if not locked:
                report.update({"status": "OVERLAP_REJECTED", "finished_at": _now()})
                self._finish_run(run_uuid, report, "CANCELLED")
                return report
        try:
            outcomes: list[FileOutcome] = []
            for source in sources:
                source_report, source_outcomes = self._run_source(
                    run_uuid, source, dry_run, report["totals"]
                )
                report["sources"].append(source_report)
                outcomes.extend(source_outcomes)
            reconciliation = reconcile(len(outcomes), outcomes)
            report["reconciliation"] = reconciliation
            report["status"] = (
                "DRY_RUN_RECONCILED" if dry_run and reconciliation["clean"]
                else "COMPLETED" if reconciliation["clean"]
                else "COMPLETED_WITH_ERRORS"
            )
        except Exception as exc:
            report["status"] = "FAILED"
            report["error"] = sanitize_error(exc)
        finally:
            report["finished_at"] = _now()
            if not dry_run:
                self._finish_run(
                    run_uuid,
                    report,
                    "COMPLETED" if report["status"] == "COMPLETED" else
                    "COMPLETED_WITH_ERRORS" if report["status"] == "COMPLETED_WITH_ERRORS" else
                    "FAILED",
                )
                if locked:
                    report["lock_released"] = self._unlock(run_uuid)
            report_path = self.report_root / f"incremental-sync-{run_uuid}.json"
            from .incremental_sync import write_json_report
            write_json_report(report_path, report)
            report["report_path"] = str(report_path)
        return report

    def _run_source(
        self,
        run_id: str,
        source: Mapping[str, Any],
        dry_run: bool,
        totals: dict[str, int],
    ) -> tuple[dict[str, Any], list[FileOutcome]]:
        scan_id = None if dry_run else self._create_scan(run_id, str(source["id"]))
        scan = scan_folder_recursive(self.source_service, str(source["google_folder_id"]))
        stored = self._stored(str(source["id"]))
        stored_by_google = {str(row["google_file_id"]): row for row in stored}
        items = [item for item in scan.items if item.classification != FOLDER_CLASSIFICATION]
        metadata = [_metadata(item) for item in items]
        classifications = classify_inventory(metadata, stored)
        item_by_id = {item.file_id: item for item in items}
        outcomes: list[FileOutcome] = []
        counts = Counter(value.value for value in classifications.values())
        totals["sources_checked"] += 1
        totals["files_discovered"] += len(items)
        totals["new_files_detected"] += counts["NEW"]
        totals["changed_files_detected"] += counts["CHANGED"]
        totals["unchanged_files_ignored"] += counts["UNCHANGED"]
        totals["removed_from_source"] += counts["REMOVED_FROM_SOURCE"]
        totals["inaccessible"] += counts["INACCESSIBLE"]
        for google_id, classification in classifications.items():
            row = stored_by_google.get(google_id)
            if classification is FileClassification.UNCHANGED:
                if (
                    not dry_run
                    and row.get("sync_processing_status") in {"FAILED", "AWAITING_RETRY", "PROCESSING"}
                    and row.get("sync_classification") in {"NEW", "CHANGED"}
                ):
                    item = item_by_id[google_id]
                    resumed = self._process_adapter(AdapterRequest(
                        run_id, source, {**row, **_current_identity_overlay(item)},
                        _metadata(item), FileClassification(row["sync_classification"]), False,
                    ))
                    self._merge_adapter_totals(totals, resumed)
                    outcomes.append(_file_outcome(resumed))
                    continue
                outcomes.append(FileOutcome(str(row["id"]), "UNCHANGED"))
                if not dry_run:
                    self._checkpoint(str(row["id"]), classification, "COMPLETED")
                continue
            if classification is FileClassification.REMOVED_FROM_SOURCE:
                outcomes.append(FileOutcome(str(row["id"]), "REMOVED_FROM_SOURCE"))
                if not dry_run:
                    self.client.table("source_files").update({
                        "is_missing": True,
                        "sync_classification": classification.value,
                        "sync_processing_status": "COMPLETED",
                        "sync_retry_eligible": False,
                        "sync_last_success_at": _now(),
                    }).eq("id", str(row["id"])).execute()
                continue
            item = item_by_id[google_id]
            current = _metadata(item)
            if classification is FileClassification.INACCESSIBLE:
                source_file_id = str(row.get("id") if row else google_id)
                outcomes.append(FileOutcome(source_file_id, "INACCESSIBLE"))
                continue
            if row is None:
                row = self._new_source_row(source, item, scan_id, dry_run)
            else:
                row = {**row, **_current_identity_overlay(item)}
            if dry_run:
                from .rules import FileRuleInput, evaluate_file
                decision = evaluate_file(FileRuleInput(
                    file_name=row.get("file_name"), mime_type=current.mime_type,
                    file_extension=row.get("file_extension"), size_bytes=current.size_bytes,
                    relative_path=row.get("relative_path"),
                ))
                outcome = "SKIPPED" if decision.automatic_decision != "TAKE" else "PLANNED"
                outcomes.append(FileOutcome(str(row.get("id") or google_id), outcome, "DRY_RUN_WOULD_PROCESS"))
                continue
            adapter_result = self._process_adapter(
                AdapterRequest(run_id, source, row, current, classification, False)
            )
            self._merge_adapter_totals(totals, adapter_result)
            outcomes.append(_file_outcome(adapter_result))
        clean_source = not scan.errors and not any(
            outcome.outcome in {"FAILED", "AWAITING_RETRY", "INACCESSIBLE"}
            for outcome in outcomes
        )
        if not dry_run and scan_id:
            self._finish_scan(scan_id, len(items), outcomes, clean_source)
        return ({
            "source_folder_id": source["id"],
            "files_discovered": len(items),
            "scan_errors": len(scan.errors),
            "classifications": dict(counts),
            "status": "RECONCILED" if clean_source else "WITH_ERRORS",
        }, outcomes)

    def _process_adapter(self, request: AdapterRequest) -> AdapterResult:
        if self._adapter is None:
            self._adapter = self.adapter_factory()
        return self._adapter.process(request)

    def _sources(self, selected: set[str]) -> list[dict[str, Any]]:
        query = self.client.table("source_folders").select("*").eq("active", True).order("id")
        rows = list(query.execute().data or [])
        if selected:
            rows = [row for row in rows if str(row["id"]) in selected]
            if len(rows) != len(selected):
                raise RuntimeError("One or more selected active source folders were not found")
        return rows

    def _stored(self, source_id: str) -> list[dict[str, Any]]:
        return list(self.client.table("source_files").select("*").eq("source_folder_id", source_id).execute().data or [])

    def _new_source_row(self, source: Mapping[str, Any], item: RecursiveScanItem, scan_id: str | None, dry_run: bool) -> dict[str, Any]:
        values = {
            "source_folder_id": source["id"], "last_scan_run_id": scan_id,
            "google_file_id": item.file_id, **_current_row_overlay(item),
            "md5_checksum": item.md5_checksum, "drive_created_at": item.created_time,
            "web_view_link": item.web_view_link,
            "parent_google_folder_id": item.parent_folder_id,
            "decision": "PENDING", "processing_status": "DISCOVERED",
            "trashed": False, "is_missing": False,
            "first_seen_at": _now(), "last_seen_at": _now(), "metadata": {},
            "sync_classification": "NEW", "sync_processing_status": "CLASSIFIED",
        }
        if dry_run:
            return {**values, "id": f"dry-run:{item.file_id}"}
        rows = self.client.table("source_files").upsert(
            values, on_conflict="source_folder_id,google_file_id", ignore_duplicates=True
        ).execute().data or []
        if rows:
            return rows[0]
        existing = self.client.table("source_files").select("*").eq("source_folder_id", str(source["id"])).eq("google_file_id", item.file_id).limit(1).execute().data or []
        if len(existing) != 1:
            raise RuntimeError("New source-file identity did not reconcile")
        return existing[0]

    def _checkpoint(self, source_id: str, classification: FileClassification, status: str) -> None:
        self.client.table("source_files").update({
            "sync_classification": classification.value,
            "sync_processing_status": status,
            "sync_retry_eligible": False,
            "sync_last_failure_reason": None,
            "sync_last_success_at": _now(),
        }).eq("id", source_id).execute()

    def _create_run(self, run_id: str, trigger: str, folders: int, started: str) -> None:
        self.client.table("sync_runs").insert({
            # Retained pre-foundation compatibility column.
            "id": run_id, "sync_type": "DAILY_SYNC", "run_type": "DAILY_SYNC", "status": "RUNNING",
            "started_at": started, "folders_total": folders,
            "sources_requested": folders,
            "metadata": {"run_type": "incremental_sync", "trigger": trigger, "dry_run": False},
        }).execute()

    def _lock(self, run_id: str) -> bool:
        return bool(self.client.rpc("acquire_synchronization_lock", {
            "requested_lock_name": LOCK_NAME, "requested_run_id": run_id,
            "requested_lease_seconds": 7200,
        }).execute().data)

    def _unlock(self, run_id: str) -> bool:
        return bool(self.client.rpc("release_synchronization_lock", {
            "requested_lock_name": LOCK_NAME, "requested_run_id": run_id,
        }).execute().data)

    def _create_scan(self, run_id: str, source_id: str) -> str:
        rows = self.client.table("scan_runs").insert({
            "sync_run_id": run_id, "source_folder_id": source_id,
            "run_mode": "MIGRATION", "status": "RUNNING", "started_at": _now(),
            "metadata": {"import_type": "DAILY_INCREMENTAL_SYNC"},
        }).execute().data or []
        return str(rows[0]["id"])

    def _finish_scan(self, scan_id: str, discovered: int, outcomes: list[FileOutcome], clean: bool) -> None:
        counts = Counter(item.outcome for item in outcomes)
        self.client.table("scan_runs").update({
            "status": "COMPLETED" if clean else "COMPLETED_WITH_ERRORS",
            "completed_at": _now(), "files_discovered": discovered,
            "files_taken": counts["UPLOADED_VERIFIED"] + counts["LINKED_DUPLICATE"] + counts["UNCHANGED"],
            "files_skipped": counts["SKIPPED"] + counts["REMOVED_FROM_SOURCE"],
            "files_uploaded": counts["UPLOADED_VERIFIED"],
            "duplicates_found": counts["LINKED_DUPLICATE"],
            "files_failed": counts["FAILED"] + counts["AWAITING_RETRY"] + counts["INACCESSIBLE"],
        }).eq("id", scan_id).execute()

    def _finish_run(self, run_id: str, report: Mapping[str, Any], status: str) -> None:
        totals = report["totals"]
        self.client.table("sync_runs").update({
            "status": status, "completed_at": _now(),
            "sources_requested": len(report.get("sources", [])),
            "sources_scanned": totals["sources_checked"],
            "folders_found": totals["sources_checked"],
            "files_found": totals["files_discovered"],
            "new_files_found": totals["new_files_detected"],
            "changed_files_found": totals["changed_files_detected"],
            "inaccessible_files": totals["inaccessible"],
            "unique_files_uploaded": totals["unique_files_uploaded"],
            "folders_succeeded": sum(source["status"] == "RECONCILED" for source in report.get("sources", [])),
            "folders_failed": sum(source["status"] != "RECONCILED" for source in report.get("sources", [])),
            "files_discovered": totals["files_discovered"],
            "files_taken": totals["unchanged_files_ignored"] + totals["new_files_detected"] + totals["changed_files_detected"] - totals["files_skipped"],
            "files_skipped": totals["files_skipped"],
            "files_uploaded": totals["unique_files_uploaded"],
            "duplicates_found": totals["exact_duplicates_found"],
            "files_failed": totals["failed_files"],
            "error_message": report.get("error"),
            "metadata": {"run_type": "incremental_sync", "trigger": report["trigger_type"], "dry_run": False, "totals": totals, "reconciliation": report.get("reconciliation")},
        }).eq("id", run_id).execute()

    @staticmethod
    def _merge_adapter_totals(totals: dict[str, int], result: AdapterResult) -> None:
        mapping = {
            "skipped_files": "files_skipped", "hashed_files": "files_hashed",
            "existing_assets_reused": "existing_assets_reused",
            "unique_assets_created": "unique_assets_created",
            "relationships_created_or_reused": "relationships_created_or_reused",
            "uploaded_files": "unique_files_uploaded",
            "verified_destinations": "verified_destinations",
            "retryable_failures": "retried_files", "final_failures": "failed_files",
            "hash_retry_events": "retried_files",
        }
        for key, target in mapping.items():
            totals[target] += int(result.counters.get(key, 0))
        totals["exact_duplicates_found"] += int(result.outcome.value == "REUSED_EXISTING_ASSET")
        totals["unresolved_exceptions"] += int(result.outcome.value in {"FAILED_RETRYABLE", "FAILED_FINAL"})


def _metadata(item: RecursiveScanItem) -> DriveMetadata:
    return DriveMetadata(
        item.file_id, item.modified_time, item.size, item.mime_type,
        item.md5_checksum, item.accessibility_status == "accessible",
    )


def _current_row_overlay(item: RecursiveScanItem) -> dict[str, Any]:
    return {
        "file_name": item.name, "mime_type": item.mime_type,
        "file_extension": item.file_extension, "size_bytes": item.size,
        "drive_modified_at": item.modified_time,
        "relative_path": item.relative_folder_path,
    }


def _current_identity_overlay(item: RecursiveScanItem) -> dict[str, Any]:
    return {
        "file_name": item.name,
        "file_extension": item.file_extension,
        "relative_path": item.relative_folder_path,
    }


def _file_outcome(result: AdapterResult) -> FileOutcome:
    mapping = {
        "SKIPPED": "SKIPPED",
        "REUSED_EXISTING_ASSET": "LINKED_DUPLICATE",
        "UPLOADED_AND_VERIFIED": "UPLOADED_VERIFIED",
        "FAILED_RETRYABLE": "AWAITING_RETRY",
        "FAILED_FINAL": "FAILED",
        "UNCHANGED": "UNCHANGED",
    }
    return FileOutcome(result.source_file_id, mapping[result.outcome.value], result.reason)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
