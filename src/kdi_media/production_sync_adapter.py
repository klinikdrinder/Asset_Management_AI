"""Step 14 production orchestration over the existing Step 8-10 components."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from .incremental_sync import DriveMetadata, FileClassification, sanitize_error
from .rules import FileRuleInput, evaluate_file
from .step9_canonicalization import (
    SupabaseCanonicalRepository,
    build_canonical_groups,
)
from .step9_hashing import SourceSnapshot, Step9HashWorker, SupabaseHashRepository, iter_drive_content, read_drive_snapshot
from .step10_upload import (
    DestinationRootGuard,
    DriveResumableTransfer,
    Step10Error,
    Step10UploadWorker,
    SupabaseStep10Repository,
    lookup_destination_identity,
    prepare_lifecycle_initialization,
    read_destination_metadata,
    read_source_metadata,
    resolve_category_folder,
    route_category,
    select_canonical_source,
)


class AdapterOutcome(StrEnum):
    UNCHANGED = "UNCHANGED"
    SKIPPED = "SKIPPED"
    REUSED_EXISTING_ASSET = "REUSED_EXISTING_ASSET"
    UPLOADED_AND_VERIFIED = "UPLOADED_AND_VERIFIED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"


@dataclass(frozen=True)
class AdapterRequest:
    run_id: str
    source_folder: Mapping[str, Any]
    source_file: Mapping[str, Any]
    drive_metadata: DriveMetadata
    classification: FileClassification
    dry_run: bool = False


@dataclass(frozen=True)
class AdapterResult:
    outcome: AdapterOutcome
    source_file_id: str
    classification: FileClassification
    dry_run: bool
    reason: str | None = None
    content_sha256: str | None = None
    asset_id: str | None = None
    destination_id: str | None = None
    counters: Mapping[str, int] = field(default_factory=dict)


class ProductionSyncAdapter:
    """One-file durable adapter; algorithms remain owned by Steps 8-10."""

    SOURCE_COLUMNS = (
        "id,source_folder_id,google_file_id,file_name,mime_type,file_extension,"
        "size_bytes,drive_modified_at,relative_path,decision,processing_status,"
        "hash_status,hash_algorithm,content_sha256,hash_expected_bytes,"
        "hash_drive_mime_type,hash_drive_modified_at,hash_drive_version,"
        "hash_completed_at,sync_classification,sync_processing_status,"
        "sync_attempt_count,sync_retry_eligible,sync_last_failure_reason,"
        "sync_last_success_at"
    )

    def __init__(
        self,
        *,
        client: Any,
        source_service: Any,
        destination_service: Any,
        destination_root_id: str,
        spool_root: Path,
        category_folders: Mapping[str, str] | None = None,
        hash_content_reader: Callable[..., Iterable[bytes]] = iter_drive_content,
        hash_sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.client = client
        self.source_service = source_service
        self.destination_service = destination_service
        self.destination_root_id = destination_root_id
        self.hash_repository = SupabaseHashRepository(client)
        self.canonical_repository = SupabaseCanonicalRepository(client)
        self.destination_repository = SupabaseStep10Repository(client)
        self.worker_id_prefix = "step14"
        self.hash_content_reader = hash_content_reader
        self.hash_sleeper = hash_sleeper
        self.hash_retry_events = 0
        root_guard = DestinationRootGuard(destination_root_id)
        self.category_folders = dict(category_folders or {
            category: resolve_category_folder(
                destination_service, root_guard, category, allow_create=False
            )
            for category in ("Images", "Videos", "Documents")
        })
        self.root_guard = DestinationRootGuard(
            destination_root_id, self.category_folders
        )
        self.upload_worker = Step10UploadWorker(
            repository=self.destination_repository,
            source_service=source_service,
            destination_service=destination_service,
            transfer_adapter=DriveResumableTransfer(temp_root=spool_root),
            root_guard=self.root_guard,
            source_metadata_reader=read_source_metadata,
            destination_lookup=lookup_destination_identity,
            destination_metadata_reader=read_destination_metadata,
        )

    def process(self, request: AdapterRequest) -> AdapterResult:
        if request.classification not in {
            FileClassification.NEW, FileClassification.CHANGED
        }:
            return AdapterResult(
                AdapterOutcome.UNCHANGED,
                str(request.source_file.get("id") or ""),
                request.classification,
                request.dry_run,
                counters={"unchanged_files": 1},
            )
        source_id = str(request.source_file.get("id") or "")
        if not source_id:
            raise ValueError("The adapter requires a persisted source-file ID")
        decision = self._decision(request)
        base = {
            "new_files": int(request.classification is FileClassification.NEW),
            "changed_files": int(request.classification is FileClassification.CHANGED),
        }
        if decision.automatic_decision != "TAKE":
            if not request.dry_run:
                self._persist_skip(request, decision.reason_code.value)
            return AdapterResult(
                AdapterOutcome.SKIPPED, source_id, request.classification,
                request.dry_run, reason=decision.reason_code.value,
                counters={**base, "skipped_files": 1},
            )
        if request.dry_run:
            return AdapterResult(
                AdapterOutcome.UPLOADED_AND_VERIFIED,
                source_id,
                request.classification,
                True,
                reason="WOULD_HASH_CANONICALIZE_AND_UPLOAD_OR_REUSE",
                counters=base,
            )

        try:
            prior_link = self._prepare_take(request, decision.rule_version)
            source = self._source(source_id)
            result = self._hash(request, source)
            if result is None:
                return self._hash_failure(request, base)
            hash_performed = not bool(getattr(result, "persisted", False))
            source = self._source(source_id)
            asset, reused = self._canonicalize(
                request, source, prior_link
            )
            asset_id = str(asset["id"])
            if reused:
                self._complete_checkpoint(source_id)
                self._event(
                    request, "UPLOAD_VERIFIED", "SUCCESS",
                    "Existing canonical asset reused without upload",
                    asset_id=asset_id,
                    details={"adapter_outcome": "REUSED_EXISTING_ASSET"},
                )
                return AdapterResult(
                    AdapterOutcome.REUSED_EXISTING_ASSET,
                    source_id,
                    request.classification,
                    False,
                    content_sha256=result.content_sha256,
                    asset_id=asset_id,
                    counters={
                        **base, "hashed_files": int(hash_performed),
                        "hash_retry_events": int(getattr(self, "hash_retry_events", 0)),
                        "existing_assets_reused": 1,
                        "relationships_created_or_reused": 1,
                    },
                )
            lifecycle = self._ensure_lifecycle(asset, source)
            upload = self._upload(request, asset, source, lifecycle)
            self._complete_checkpoint(source_id)
            self._event(
                request, "UPLOAD_VERIFIED", "SUCCESS",
                "Incremental canonical asset destination verified",
                asset_id=asset_id,
                asset_destination_id=str(lifecycle.get("id") or "") or None,
                details={
                    "asset_destination_id": lifecycle.get("id"),
                    "destination_google_file_id": upload.get("destination_google_file_id") or lifecycle.get("destination_google_file_id"),
                    "adapter_outcome": "UPLOADED_AND_VERIFIED",
                },
            )
            return AdapterResult(
                AdapterOutcome.UPLOADED_AND_VERIFIED,
                source_id,
                request.classification,
                False,
                content_sha256=result.content_sha256,
                asset_id=asset_id,
                destination_id=str(upload.get("destination_google_file_id") or lifecycle.get("destination_google_file_id") or "") or None,
                counters={
                    **base, "hashed_files": int(hash_performed),
                    "hash_retry_events": int(getattr(self, "hash_retry_events", 0)),
                    "unique_assets_created": 1,
                    "relationships_created_or_reused": 1,
                    "uploaded_files": int(upload.get("outcome") == "UPLOADED"),
                    "verified_destinations": 1,
                },
            )
        except Step10Error as exc:
            return self._processing_failure(request, exc, base, exc.retryable)
        except Exception as exc:
            return self._processing_failure(request, exc, base, False)

    def _decision(self, request: AdapterRequest):
        row = request.source_file
        return evaluate_file(FileRuleInput(
            file_name=row.get("file_name"),
            mime_type=request.drive_metadata.mime_type,
            file_extension=row.get("file_extension"),
            size_bytes=request.drive_metadata.size_bytes,
            relative_path=row.get("relative_path"),
            accessibility_status="accessible" if request.drive_metadata.accessible else "inaccessible",
            trashed=False,
            is_missing=False,
            is_folder=False,
        ))

    def _prepare_take(self, request: AdapterRequest, rule_version: str) -> Mapping[str, Any] | None:
        source_id = str(request.source_file["id"])
        prior = self._current_link(source_id)
        now = _now()
        metadata = dict(request.source_file.get("metadata") or {})
        metadata.update({
            "step8_rule_version": rule_version,
            "step14_previous_asset_id": prior.get("asset_id") if prior else None,
            "step14_observed_at": now,
        })
        values: dict[str, Any] = {
            "file_name": request.source_file.get("file_name"),
            "file_extension": request.source_file.get("file_extension"),
            "relative_path": request.source_file.get("relative_path"),
            "mime_type": request.drive_metadata.mime_type,
            "size_bytes": request.drive_metadata.size_bytes,
            "md5_checksum": request.drive_metadata.md5_checksum,
            "drive_modified_at": request.drive_metadata.modified_time,
            "last_seen_at": now,
            "is_missing": False,
            "decision": "TAKE",
            "processing_status": "READY",
            "skip_reason": None,
            "processing_error": None,
            "sync_classification": request.classification.value,
            "sync_processing_status": "PROCESSING",
            "sync_retry_eligible": False,
            "sync_last_failure_reason": None,
            "metadata": metadata,
        }
        if request.classification is FileClassification.CHANGED:
            values.update({
                "hash_algorithm": None, "content_sha256": None,
                "hash_status": "NOT_STARTED", "hash_expected_bytes": None,
                "hash_observed_bytes": None, "hash_attempt_count": 0,
                "hash_last_attempt_at": None, "hash_completed_at": None,
                "hash_failure_code": None, "hash_failure_reason": None,
                "hash_retryable": None, "hash_source_snapshot": None,
                "hash_drive_modified_at": None, "hash_drive_size": None,
                "hash_drive_mime_type": None, "hash_drive_version": None,
                "hash_claim_owner": None, "hash_claimed_at": None,
                "hash_claim_expires_at": None,
            })
            self._event(
                request, "SOURCE_CHANGED", "INFO",
                "Changed source version accepted for reprocessing",
                asset_id=str(prior.get("asset_id") or "") or None if prior else None,
                details={
                    "prior_asset_id": prior.get("asset_id") if prior else None,
                    "prior_sha256": request.source_file.get("content_sha256"),
                    "prior_drive_modified_at": request.source_file.get("drive_modified_at"),
                    "current_drive_modified_at": request.drive_metadata.modified_time,
                },
            )
        self.client.table("source_files").update(values).eq("id", source_id).execute()
        return prior

    def _persist_skip(self, request: AdapterRequest, reason: str) -> None:
        source_id = str(request.source_file["id"])
        self.client.table("source_files").update({
            "file_name": request.source_file.get("file_name"),
            "file_extension": request.source_file.get("file_extension"),
            "relative_path": request.source_file.get("relative_path"),
            "mime_type": request.drive_metadata.mime_type,
            "size_bytes": request.drive_metadata.size_bytes,
            "md5_checksum": request.drive_metadata.md5_checksum,
            "drive_modified_at": request.drive_metadata.modified_time,
            "last_seen_at": _now(), "is_missing": False,
            "decision": "SKIP", "processing_status": "SKIPPED",
            "skip_reason": reason, "processing_error": None,
            "sync_classification": request.classification.value,
            "sync_processing_status": "COMPLETED",
            "sync_retry_eligible": False,
            "sync_last_failure_reason": None,
            "sync_last_success_at": _now(),
        }).eq("id", source_id).execute()

    def _hash(self, request: AdapterRequest, source: Mapping[str, Any]):
        if (
            source.get("hash_status") == "HASHED"
            and source.get("hash_algorithm") == "SHA-256"
            and isinstance(source.get("content_sha256"), str)
            and len(source["content_sha256"]) == 64
        ):
            return type("PersistedHashResult", (), {
                "content_sha256": source["content_sha256"], "persisted": True
            })()
        self.hash_retry_events = 0
        options: dict[str, Any] = {
            "event_observer": lambda event, _details: setattr(
                self, "hash_retry_events", self.hash_retry_events + int(event == "retry")
            )
        }
        if self.hash_sleeper is not None:
            options["sleeper"] = self.hash_sleeper
        worker = Step9HashWorker(
            self.hash_repository, self.source_service, read_drive_snapshot,
            **options,
        )
        snapshot = SourceSnapshot(
            file_id=request.drive_metadata.google_file_id,
            mime_type=str(request.drive_metadata.mime_type or "").lower(),
            size_bytes=request.drive_metadata.size_bytes,
            modified_time=request.drive_metadata.modified_time,
            provider_md5=request.drive_metadata.md5_checksum,
        )
        return worker.process(
            str(source["id"]),
            f"{self.worker_id_prefix}-hash-{request.run_id}",
            snapshot,
            content_reader=self.hash_content_reader,
        )

    def _canonicalize(self, request: AdapterRequest, source: Mapping[str, Any], prior_link: Mapping[str, Any] | None):
        group = build_canonical_groups([source])[0]
        existing = self._asset_by_hash(group.content_hash)
        asset = self.canonical_repository.create_or_reuse_asset(group.asset_values())
        reused = existing is not None
        source_id = str(source["id"])
        asset_id = str(asset["id"])
        if prior_link and str(prior_link.get("asset_id")) != asset_id:
            response = (
                self.client.table("asset_sources")
                .update({
                    "asset_id": asset_id,
                    "relationship_type": "DUPLICATE" if reused else "ORIGINAL",
                    "is_first_discovered_source": not reused,
                })
                .eq("source_file_id", source_id)
                .eq("asset_id", str(prior_link["asset_id"]))
                .execute()
            )
            if len(response.data or []) != 1:
                raise RuntimeError("Changed source relationship transition conflicted")
        else:
            self.canonical_repository.create_or_reuse_link(
                asset_id=asset_id,
                source_file_id=source_id,
                relationship_type="DUPLICATE" if reused else "ORIGINAL",
            )
        return asset, reused

    def _ensure_lifecycle(self, asset: Mapping[str, Any], source: Mapping[str, Any]) -> Mapping[str, Any]:
        link = self._current_link(str(source["id"]))
        candidates = prepare_lifecycle_initialization(
            [asset], [link], [source], self.destination_root_id
        )
        if len(candidates) != 1:
            raise RuntimeError("Step 10 lifecycle candidate was not produced")
        self.destination_repository.initialize(candidates)
        rows = (
            self.client.table("asset_destinations").select("*")
            .eq("asset_id", str(asset["id"]))
            .eq("destination_folder_id", self.destination_root_id)
            .limit(1).execute().data or []
        )
        if len(rows) != 1:
            raise RuntimeError("Step 10 lifecycle initialization did not reconcile")
        return rows[0]

    def _upload(self, request: AdapterRequest, asset: Mapping[str, Any], source: Mapping[str, Any], lifecycle: Mapping[str, Any]):
        if lifecycle.get("upload_status") == "VERIFIED":
            return {"outcome": "SKIPPED_VERIFIED", "destination_google_file_id": lifecycle.get("destination_google_file_id")}
        worker_id = f"{self.worker_id_prefix}-upload-{request.run_id}"
        claimed = self.destination_repository.claim_batch(
            worker_id, 1, 900, [str(lifecycle["id"])], self.destination_root_id
        )
        if len(claimed) != 1:
            raise RuntimeError("Destination lifecycle is not currently claimable")
        selected = select_canonical_source(asset, [self._current_link(str(source["id"]))], [source])
        category = route_category(selected.file_extension, selected.mime_type)
        try:
            return self.upload_worker.process(
                lifecycle=claimed[0], asset=asset, source=selected,
                stored_source_row=source,
                category_parent_id=self.category_folders[category],
                worker_id=worker_id, execute=True,
            )
        except Step10Error as exc:
            self.destination_repository.fail(
                str(lifecycle["id"]), worker_id, exc, retry_delay_seconds=60
            )
            raise

    def _source(self, source_id: str) -> Mapping[str, Any]:
        rows = self.client.table("source_files").select("*").eq("id", source_id).limit(1).execute().data or []
        if len(rows) != 1:
            raise RuntimeError("Source file could not be reloaded")
        return rows[0]

    def _current_link(self, source_id: str) -> Mapping[str, Any] | None:
        rows = self.client.table("asset_sources").select("*").eq("source_file_id", source_id).limit(1).execute().data or []
        return rows[0] if rows else None

    def _asset_by_hash(self, sha256: str) -> Mapping[str, Any] | None:
        rows = self.client.table("assets").select("*").eq("content_hash", sha256).limit(1).execute().data or []
        return rows[0] if rows else None

    def _complete_checkpoint(self, source_id: str) -> None:
        self.client.table("source_files").update({
            "sync_processing_status": "COMPLETED",
            "sync_retry_eligible": False,
            "sync_last_failure_reason": None,
            "sync_last_success_at": _now(),
        }).eq("id", source_id).execute()

    def _hash_failure(self, request: AdapterRequest, base: Mapping[str, int]) -> AdapterResult:
        row = self._source(str(request.source_file["id"]))
        retryable = row.get("hash_status") == "FAILED_RETRYABLE"
        reason = str(row.get("hash_failure_reason") or row.get("hash_failure_code") or "Hashing did not complete")
        return self._processing_failure(request, RuntimeError(reason), base, retryable)

    def _processing_failure(self, request: AdapterRequest, error: BaseException, base: Mapping[str, int], retryable: bool) -> AdapterResult:
        source_id = str(request.source_file["id"])
        reason = sanitize_error(error)
        current = self._source(source_id)
        attempts = min(5, int(current.get("sync_attempt_count") or 0) + 1)
        final_retryable = retryable and attempts < 5
        self.client.table("source_files").update({
            "sync_processing_status": "AWAITING_RETRY" if final_retryable else "FAILED",
            "sync_attempt_count": attempts,
            "sync_retry_eligible": final_retryable,
            "sync_last_failure_reason": reason,
        }).eq("id", source_id).execute()
        self._event(
            request, "UPLOAD_FAILED", "WARNING" if final_retryable else "ERROR",
            "Incremental source processing failed",
            details={"retryable": final_retryable, "attempt": attempts, "reason": reason},
        )
        return AdapterResult(
            AdapterOutcome.FAILED_RETRYABLE if final_retryable else AdapterOutcome.FAILED_FINAL,
            source_id, request.classification, False, reason=reason,
            counters={**base, "retryable_failures" if final_retryable else "final_failures": 1},
        )

    def _event(self, request: AdapterRequest, event_type: str, status: str, message: str, *, asset_id: str | None = None, asset_destination_id: str | None = None, details: Mapping[str, Any] | None = None) -> None:
        self.destination_repository.append_event({
            "sync_run_id": request.run_id,
            "source_folder_id": request.source_folder.get("id"),
            "source_file_id": request.source_file.get("id"),
            "asset_id": asset_id,
            "asset_destination_id": asset_destination_id,
            "event_type": event_type,
            "event_status": status,
            "status": status,
            "message": message,
            "details": dict(details or {}),
            "event_details": dict(details or {}),
        })


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
