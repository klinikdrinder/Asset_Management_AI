"""Exact-eight Step 10 limited-production pilot orchestration."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping, Protocol
from uuid import uuid4

from .google_drive import (
    DriveCredentialProfile,
    create_destination_write_drive_service,
    create_readonly_drive_service,
    load_destination_oauth_config,
    load_oauth_config,
)
from .step10_upload import (
    DestinationRootGuard,
    DriveResumableTransfer,
    InvalidCanonicalState,
    RetryableTransferError,
    Step10Error,
    Step10UploadWorker,
    SupabaseStep10Repository,
    VerificationLevel,
    build_destination_plan,
    lookup_destination_identity,
    read_destination_metadata,
    read_source_metadata,
    resolve_category_folder,
    run_with_retry,
    select_canonical_source,
    verify_destination_metadata,
    verify_destination_sha256,
)


APPROVED_ROOT = "1CdmowWV5TAk5R9D5yl2cOT8Plx3ihZgl"
APPROVED_MANIFEST = Path(
    "reports/step_10_phase_b1_pilot_manifest.json"
)
APPROVED_PILOT_LIFECYCLE_IDS = frozenset(
    {
        "14c75c65-80fb-5c3f-bfa6-ad9eb9b34e70",
        "22f13a61-ce0b-5e5c-97ae-ec5d5ed75ca8",
        "4dcae399-6183-5655-9eda-fcbee987ace6",
        "5ba81db2-d1e7-5f45-b7a1-05a60b61b6de",
        "63c5c549-d1eb-5631-84b2-ee598fdfff6d",
        "b6be7383-bf2a-5bc5-8e3a-b78e2dc99542",
        "dc5f2e36-b551-5d79-8f83-216fb3255f73",
        "eafcea6b-add3-5f74-affa-960e2f59202d",
    }
)
EXPECTED_FORMAT_MIX = {"jpeg": 3, "mp4": 3, "pdf": 1, "pptx": 1}
READY_VERDICT = "READY_FOR_FULL_STEP_10_PRODUCTION_UPLOAD"
BLOCKED_VERDICT = "BLOCKED_AFTER_LIMITED_PRODUCTION_PILOT"
MANUAL_VERDICT = "BLOCKED_REQUIRES_MANUAL_PILOT_RECONCILIATION"
TERMINAL = {
    "FAILED_PERMANENT",
    "SOURCE_CHANGED",
    "SOURCE_NOT_FOUND",
    "SOURCE_ACCESS_DENIED",
    "DESTINATION_ACCESS_DENIED",
    "DESTINATION_CONFLICT",
    "MANUAL_REVIEW_REQUIRED",
}


class PilotSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PilotCandidate:
    lifecycle_id: str
    asset_id: str
    source_file_id: str
    extension: str
    mime_type: str
    expected_bytes: int
    category: str
    filename: str
    relative_path: str
    enhanced_sha256: bool


@dataclass(frozen=True)
class PilotManifest:
    path: Path
    root_id: str
    candidates: tuple[PilotCandidate, ...]

    @classmethod
    def load(cls, path: Path) -> "PilotManifest":
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = list(raw.get("candidates") or [])
        if len(entries) != 8:
            raise PilotSafetyError("Pilot manifest must contain exactly 8 rows")
        assets = [str(row.get("asset_uuid") or "") for row in entries]
        if len(set(assets)) != 8:
            raise PilotSafetyError("Pilot manifest asset IDs must be unique")
        mix = {
            extension: sum(row.get("extension") == extension for row in entries)
            for extension in EXPECTED_FORMAT_MIX
        }
        if mix != EXPECTED_FORMAT_MIX:
            raise PilotSafetyError("Pilot manifest format mix is incorrect")
        expected_categories = {
            "jpeg": "Images",
            "mp4": "Videos",
            "pdf": "Documents",
            "pptx": "Documents",
        }
        if any(
            row.get("destination_category")
            != expected_categories.get(str(row.get("extension")))
            for row in entries
        ):
            raise PilotSafetyError("Pilot manifest category routing is incorrect")
        enhanced = [
            str(row.get("extension"))
            for row in entries
            if row.get("enhanced_sha256_verification_selected")
        ]
        if enhanced.count("jpeg") < 1 or enhanced.count("mp4") < 1:
            raise PilotSafetyError(
                "Pilot must select JPEG and MP4 enhanced verification"
            )
        root = str(raw.get("destination_root_id") or "")
        if root != APPROVED_ROOT:
            raise PilotSafetyError("Pilot manifest destination root is incorrect")
        # Lifecycle IDs are deterministic database identities approved after B3;
        # pair them to manifest assets during database preflight.
        candidates = tuple(
            PilotCandidate(
                lifecycle_id="",
                asset_id=str(row["asset_uuid"]),
                source_file_id=str(row["selected_source_file_uuid"]),
                extension=str(row["extension"]),
                mime_type=str(row["mime_type"]),
                expected_bytes=int(row["expected_bytes"]),
                category=str(row["destination_category"]),
                filename=str(row["proposed_destination_filename"]),
                relative_path=str(row["proposed_relative_path"]),
                enhanced_sha256=bool(
                    row.get("enhanced_sha256_verification_selected")
                ),
            )
            for row in entries
        )
        return cls(path, root, candidates)

    def bind_lifecycle_ids(
        self, destinations: Iterable[Mapping[str, Any]]
    ) -> "PilotManifest":
        by_asset = {
            str(row.get("asset_id")): str(row.get("id"))
            for row in destinations
            if str(row.get("asset_id"))
            in {candidate.asset_id for candidate in self.candidates}
        }
        if len(by_asset) != 8:
            raise PilotSafetyError("Manifest assets do not map to 8 lifecycle rows")
        ids = set(by_asset.values())
        if ids != APPROVED_PILOT_LIFECYCLE_IDS:
            raise PilotSafetyError("Lifecycle allowlist differs from approval")
        return PilotManifest(
            self.path,
            self.root_id,
            tuple(
                PilotCandidate(
                    lifecycle_id=by_asset[candidate.asset_id],
                    **{
                        name: getattr(candidate, name)
                        for name in (
                            "asset_id",
                            "source_file_id",
                            "extension",
                            "mime_type",
                            "expected_bytes",
                            "category",
                            "filename",
                            "relative_path",
                            "enhanced_sha256",
                        )
                    },
                )
                for candidate in self.candidates
            ),
        )


@dataclass(frozen=True)
class PilotOptions:
    execute: bool
    production_pilot: bool
    pilot_only: bool
    authorize_drive_transfer: bool
    expected_pilot_count: int
    expected_non_pilot_count: int
    destination_root_id: str
    source_profile: str
    destination_profile: str
    manifest_path: Path
    report_path: Path
    spool_root: Path

    def validate(self) -> None:
        if self.expected_pilot_count != 8:
            raise PilotSafetyError("Expected pilot count must equal 8")
        if self.expected_non_pilot_count != 870:
            raise PilotSafetyError("Expected non-pilot count must equal 870")
        if self.destination_root_id != APPROVED_ROOT:
            raise PilotSafetyError("Approved destination root mismatch")
        if self.manifest_path.resolve() != APPROVED_MANIFEST.resolve():
            raise PilotSafetyError("Approved pilot manifest path mismatch")
        if self.source_profile != DriveCredentialProfile.SOURCE_READONLY.value:
            raise PilotSafetyError("Source profile must be source_readonly")
        if (
            self.destination_profile
            != DriveCredentialProfile.DESTINATION_WRITE.value
        ):
            raise PilotSafetyError(
                "Destination profile must be destination_write"
            )
        if self.execute and not (
            self.production_pilot
            and self.pilot_only
            and self.authorize_drive_transfer
        ):
            raise PilotSafetyError("All live pilot gates are required")


class PilotBackend(Protocol):
    def preflight(self, manifest: PilotManifest) -> dict[str, Any]: ...
    def start_live(self, manifest: PilotManifest) -> None: ...
    def run_first(self, manifest: PilotManifest) -> list[dict[str, Any]]: ...
    def run_second(self, manifest: PilotManifest) -> list[dict[str, Any]]: ...
    def final_reconciliation(
        self, manifest: PilotManifest, outside_digest: str
    ) -> dict[str, Any]: ...
    def cleanup(self) -> dict[str, Any]: ...


class PilotOrchestrator:
    def __init__(self, backend: PilotBackend, options: PilotOptions) -> None:
        self.backend = backend
        self.options = options

    def plan(self) -> dict[str, Any]:
        self.options.validate()
        manifest = PilotManifest.load(self.options.manifest_path)
        return {
            "phase": "STEP_10_LIMITED_PRODUCTION_PILOT",
            "mode": "PLAN_ONLY",
            "pilot_count": len(manifest.candidates),
            "non_pilot_count": self.options.expected_non_pilot_count,
            "format_mix": EXPECTED_FORMAT_MIX,
            "destination_root_configured": True,
            "source_profile": self.options.source_profile,
            "destination_profile": self.options.destination_profile,
            "database_writes": 0,
            "drive_clients_constructed": 0,
            "drive_requests": 0,
            "spool_files": 0,
            "report_path": str(self.options.report_path),
        }

    def execute(self) -> dict[str, Any]:
        self.options.validate()
        if not self.options.execute:
            raise PilotSafetyError("Explicit execute-pilot gate is required")
        manifest = PilotManifest.load(self.options.manifest_path)
        report = self.plan()
        report.update(
            {
                "mode": "LIVE_EXACT_EIGHT",
                "verdict": BLOCKED_VERDICT,
                "primary_failure": None,
                "cleanup_failure": None,
                "first_run": [],
                "second_run": [],
            }
        )
        try:
            preflight = self.backend.preflight(manifest)
            manifest = manifest.bind_lifecycle_ids(preflight["destinations"])
            report["preflight"] = {
                key: value
                for key, value in preflight.items()
                if key != "destinations"
            }
            report["pilot_lifecycle_ids"] = sorted(
                candidate.lifecycle_id for candidate in manifest.candidates
            )
            self.backend.start_live(manifest)
            retry_reconciliation = getattr(
                self.backend, "retry_reconciliation", None
            )
            if retry_reconciliation:
                report["retry_reconciliation"] = retry_reconciliation
            report["first_run"] = self.backend.run_first(manifest)
            report["second_run"] = self.backend.run_second(manifest)
            report["final_reconciliation"] = self.backend.final_reconciliation(
                manifest, str(preflight["outside_digest"])
            )
            if report["final_reconciliation"]["clean"]:
                report["verdict"] = READY_VERDICT
        except Exception as exc:
            report["primary_failure"] = _safe_error(exc)
        finally:
            try:
                report["cleanup"] = self.backend.cleanup()
            except Exception as exc:
                report["cleanup_failure"] = _safe_error(exc)
                report["verdict"] = MANUAL_VERDICT
        report["drive_transfer_authorized"] = True
        return report


class SupabaseDrivePilotBackend:
    """Live adapter; Drive services are constructed only by start_live()."""

    DESTINATION_COLUMNS = ",".join(
        (
            "id",
            "asset_id",
            "selected_source_file_id",
            "destination_folder_id",
            "destination_google_file_id",
            "destination_filename",
            "destination_relative_path",
            "upload_status",
            "verification_level",
            "expected_bytes",
            "upload_attempt_count",
            "claim_owner",
            "claim_expires_at",
            "next_retry_at",
            "upload_completed_at",
            "verified_at",
        )
    )

    def __init__(self, client: Any, options: PilotOptions) -> None:
        self.client = client
        self.options = options
        self.repository = SupabaseStep10Repository(client)
        self.assets: dict[str, dict] = {}
        self.sources: dict[str, dict] = {}
        self.relationships: list[dict] = []
        self.destinations: dict[str, dict] = {}
        self.source_service: Any = None
        self.destination_service: Any = None
        self.category_folders: dict[str, str] = {}
        self.worker: Step10UploadWorker | None = None
        self.worker_id = f"step10-pilot-{uuid4()}"
        self.claimed_ids: set[str] = set()
        self.second_results: list[dict[str, Any]] = []
        self.step9_baseline = ""
        self.retry_reconciliation: dict[str, Any] = {}

    def preflight(self, manifest: PilotManifest) -> dict[str, Any]:
        destinations = self._all(
            "asset_destinations", self.DESTINATION_COLUMNS
        )
        bound = manifest.bind_lifecycle_ids(destinations)
        allowed = {
            candidate.lifecycle_id for candidate in bound.candidates
        }
        pilot = [row for row in destinations if str(row["id"]) in allowed]
        outside = [row for row in destinations if str(row["id"]) not in allowed]
        if len(pilot) != 8 or len(outside) != 870:
            raise PilotSafetyError("Pilot/non-pilot count mismatch")
        for row in pilot:
            if not _clean_pilot_row(row, manifest.root_id):
                raise PilotSafetyError("Pilot lifecycle row is not clean")
        if any(
            row.get("upload_status") != "NOT_STARTED"
            or row.get("verification_level") != "SOURCE_HASH_VERIFIED"
            or row.get("destination_google_file_id")
            for row in outside
        ):
            raise PilotSafetyError("Non-pilot lifecycle baseline is dirty")
        self.assets = {
            row["id"]: row
            for row in self._all(
                "assets", "id,content_hash,checksum_sha256,metadata"
            )
        }
        self.relationships = self._all(
            "asset_sources", "asset_id,source_file_id"
        )
        self.sources = {
            row["id"]: row
            for row in self._all(
                "source_files",
                ",".join(
                    (
                        "id",
                        "source_folder_id",
                        "google_file_id",
                        "file_name",
                        "mime_type",
                        "file_extension",
                        "size_bytes",
                        "decision",
                        "processing_status",
                        "hash_status",
                        "hash_algorithm",
                        "content_sha256",
                        "hash_expected_bytes",
                        "hash_drive_mime_type",
                        "hash_drive_modified_at",
                        "hash_drive_version",
                    )
                ),
            )
        }
        self.step9_baseline = _step9_digest(
            self.assets.values(), self.relationships, self.sources.values()
        )
        self.destinations = {row["id"]: row for row in pilot}
        for candidate in bound.candidates:
            row = self.destinations[candidate.lifecycle_id]
            if (
                row["asset_id"] != candidate.asset_id
                or row["selected_source_file_id"] != candidate.source_file_id
                or row["destination_filename"] != candidate.filename
                or row["destination_relative_path"] != candidate.relative_path
                or int(row["expected_bytes"]) != candidate.expected_bytes
            ):
                raise PilotSafetyError("Manifest/lifecycle identity mismatch")
        free = shutil.disk_usage(self.options.spool_root.parent).free
        largest = max(candidate.expected_bytes for candidate in bound.candidates)
        if free < largest * 2:
            raise PilotSafetyError("Insufficient controlled spool capacity")
        if self.options.spool_root.exists() and any(
            self.options.spool_root.iterdir()
        ):
            raise PilotSafetyError("Pilot spool directory is not empty")
        return {
            "destinations": destinations,
            "pilot_rows": 8,
            "non_pilot_rows": 870,
            "outside_digest": _outside_digest(outside),
            "largest_pilot_bytes": largest,
            "spool_capacity_sufficient": True,
        }

    def start_live(self, manifest: PilotManifest) -> None:
        source_config = load_oauth_config()
        destination_config = load_destination_oauth_config()
        if source_config.token_file.resolve() == (
            destination_config.token_file.resolve()
        ):
            raise PilotSafetyError("Source and destination tokens are shared")
        self.source_service = create_readonly_drive_service(source_config)
        self.destination_service = (
            create_destination_write_drive_service(destination_config)
        )
        guard = DestinationRootGuard(manifest.root_id)
        folders = {
            category: resolve_category_folder(
                self.destination_service,
                guard,
                category,
                allow_create=False,
            )
            for category in ("Images", "Videos", "Documents")
        }
        guard = DestinationRootGuard(manifest.root_id, folders)
        self.category_folders = folders
        self.worker = Step10UploadWorker(
            repository=self.repository,
            source_service=self.source_service,
            destination_service=self.destination_service,
            transfer_adapter=DriveResumableTransfer(
                temp_root=self.options.spool_root
            ),
            root_guard=guard,
            source_metadata_reader=read_source_metadata,
            destination_lookup=lookup_destination_identity,
            destination_metadata_reader=read_destination_metadata,
        )
        reconciled = []
        existing_identities = 0
        for candidate in manifest.candidates:
            asset = self.assets[candidate.asset_id]
            source = select_canonical_source(
                asset, self.relationships, self.sources.values()
            )
            plan = build_destination_plan(
                asset,
                source,
                manifest.root_id,
                destination_record_id=candidate.lifecycle_id,
            )
            matches = lookup_destination_identity(
                self.destination_service,
                self.category_folders[candidate.category],
                plan,
            )
            if len(matches) > 1:
                raise PilotSafetyError(
                    "Duplicate pre-transfer pilot destination identities exist"
                )
            if len(matches) == 1:
                verify_destination_metadata(
                    matches[0],
                    plan=plan,
                    expected_parent_id=self.category_folders[
                        candidate.category
                    ],
                )
                existing_identities += 1
            lifecycle = self.destinations[candidate.lifecycle_id]
            self.repository.append_event(
                _event(
                    candidate,
                    "UPLOAD_QUEUED",
                    "INFO",
                    {
                        "recovery": "clean_pre_transfer_retry",
                        "preserved_attempt_count": int(
                            lifecycle.get("upload_attempt_count") or 0
                        ),
                    },
                )
            )
            reconciled.append(candidate.lifecycle_id)
        self.retry_reconciliation = {
            "rows": len(reconciled),
            "prior_status": "QUEUED",
            "preserved_attempt_count": min(
                int(
                    self.destinations[candidate.lifecycle_id].get(
                        "upload_attempt_count"
                    )
                    or 0
                )
                for candidate in manifest.candidates
            ),
            "destination_identities_before_retry": existing_identities,
            "audit_event": "UPLOAD_QUEUED",
            "audit_status": "INFO",
        }

    def run_first(self, manifest: PilotManifest) -> list[dict[str, Any]]:
        allowed = [
            candidate.lifecycle_id for candidate in manifest.candidates
        ]
        claimed = self.repository.claim_batch(
            self.worker_id,
            8,
            3600,
            allowed,
            manifest.root_id,
        )
        claimed_ids = {str(row["id"]) for row in claimed}
        if claimed_ids != set(allowed):
            raise PilotSafetyError("Exact pilot claim did not return 8 rows")
        self.claimed_ids = set(claimed_ids)
        results = []
        for candidate in manifest.candidates:
            lifecycle = next(
                row for row in claimed if str(row["id"]) == candidate.lifecycle_id
            )
            try:
                if not self.repository.renew(
                    candidate.lifecycle_id, self.worker_id, 3600
                ):
                    raise PilotSafetyError("Pilot claim renewal failed")
                result = self._process(candidate, lifecycle)
                results.append(result)
                self.claimed_ids.discard(candidate.lifecycle_id)
            except Exception as exc:
                if isinstance(exc, Step10Error):
                    self.repository.fail(
                        candidate.lifecycle_id,
                        self.worker_id,
                        exc,
                        retry_delay_seconds=60,
                    )
                    self.claimed_ids.discard(candidate.lifecycle_id)
                raise
        return results

    def _process(
        self,
        candidate: PilotCandidate,
        lifecycle: Mapping[str, Any],
    ) -> dict[str, Any]:
        if self.worker is None:
            raise PilotSafetyError("Pilot worker is not initialized")
        asset = self.assets[candidate.asset_id]
        source_row = self.sources[candidate.source_file_id]
        selected = select_canonical_source(
            asset, self.relationships, self.sources.values()
        )
        if selected.id != candidate.source_file_id:
            raise InvalidCanonicalState("Pilot canonical source changed")
        self.repository.append_event(
            _event(candidate, "UPLOAD_STARTED", "INFO")
        )
        result = run_with_retry(
            lambda: self.worker.process(
                lifecycle=lifecycle,
                asset=asset,
                source=selected,
                stored_source_row=source_row,
                category_parent_id=self.category_folders[candidate.category],
                worker_id=self.worker_id,
                execute=True,
            ),
            max_attempts=5,
        )
        destination_id = str(result.get("destination_google_file_id") or "")
        if not destination_id:
            raise PilotSafetyError("Worker returned no destination file ID")
        level = VerificationLevel.DESTINATION_METADATA_VERIFIED
        if candidate.enhanced_sha256:
            level = verify_destination_sha256(
                self.destination_service,
                destination_id,
                str(asset.get("content_hash") or ""),
                enabled=True,
                profile=DriveCredentialProfile.DESTINATION_WRITE,
            )
            if not self.repository.set_verification_level(
                candidate.lifecycle_id, destination_id, level
            ):
                raise PilotSafetyError(
                    "Enhanced verification level was not persisted"
                )
        self.repository.append_event(
            _event(
                candidate,
                (
                    "UPLOAD_RECOVERED"
                    if result["outcome"] == "RECOVERED"
                    else "UPLOAD_CREATED"
                ),
                "SUCCESS",
            )
        )
        self.repository.append_event(
            _event(
                candidate,
                "UPLOAD_VERIFIED",
                "SUCCESS",
                {"verification_level": level.value},
            )
        )
        return {
            "lifecycle_id": candidate.lifecycle_id,
            "asset_id": candidate.asset_id,
            "category": candidate.category,
            "filename": candidate.filename,
            "destination_file_id": destination_id,
            "outcome": result["outcome"],
            "verification_level": level.value,
            "bytes": candidate.expected_bytes,
        }

    def run_second(self, manifest: PilotManifest) -> list[dict[str, Any]]:
        rows = {
            row["id"]: row
            for row in self._all(
                "asset_destinations", self.DESTINATION_COLUMNS
            )
        }
        results = []
        for candidate in manifest.candidates:
            row = rows[candidate.lifecycle_id]
            if row.get("upload_status") != "VERIFIED":
                raise PilotSafetyError("Pilot row is not verified on rerun")
            asset = self.assets[candidate.asset_id]
            source = select_canonical_source(
                asset, self.relationships, self.sources.values()
            )
            plan = build_destination_plan(
                asset,
                source,
                manifest.root_id,
                destination_record_id=candidate.lifecycle_id,
            )
            matches = lookup_destination_identity(
                self.destination_service,
                self.category_folders[candidate.category],
                plan,
            )
            if (
                len(matches) != 1
                or matches[0].get("id")
                != row.get("destination_google_file_id")
            ):
                raise PilotSafetyError("Rerun destination identity mismatch")
            verify_destination_metadata(
                matches[0],
                plan=plan,
                expected_parent_id=self.category_folders[candidate.category],
            )
            results.append(
                {
                    "lifecycle_id": candidate.lifecycle_id,
                    "destination_file_id": row["destination_google_file_id"],
                    "outcome": "SKIPPED_VERIFIED",
                    "new_files": 0,
                }
            )
        self.second_results = list(results)
        return results

    def final_reconciliation(
        self, manifest: PilotManifest, outside_digest: str
    ) -> dict[str, Any]:
        rows = self._all("asset_destinations", self.DESTINATION_COLUMNS)
        allowed = {
            candidate.lifecycle_id for candidate in manifest.candidates
        }
        pilot = [row for row in rows if row["id"] in allowed]
        outside = [row for row in rows if row["id"] not in allowed]
        destination_ids = [
            row.get("destination_google_file_id") for row in pilot
        ]
        final_assets = self._all(
            "assets", "id,content_hash,checksum_sha256,metadata"
        )
        final_relationships = self._all(
            "asset_sources", "asset_id,source_file_id"
        )
        final_sources = self._all(
            "source_files",
            "id,hash_status,processing_status,decision,content_sha256",
        )
        step9_unchanged = (
            _step9_digest(
                final_assets, final_relationships, final_sources
            )
            == self.step9_baseline
        )
        clean = (
            len(pilot) == 8
            and all(row.get("upload_status") == "VERIFIED" for row in pilot)
            and all(destination_ids)
            and len(set(destination_ids)) == 8
            and all(not row.get("claim_owner") for row in rows)
            and all(not row.get("claim_expires_at") for row in rows)
            and all(not row.get("next_retry_at") for row in rows)
            and len(outside) == 870
            and all(
                row.get("upload_status") == "NOT_STARTED"
                and row.get("verification_level") == "SOURCE_HASH_VERIFIED"
                and not row.get("destination_google_file_id")
                for row in outside
            )
            and _outside_digest(outside) == outside_digest
            and len(self.second_results) == 8
            and all(
                result.get("new_files") == 0
                for result in self.second_results
            )
            and step9_unchanged
        )
        if not clean:
            raise PilotSafetyError("Final pilot reconciliation is not clean")
        return {
            "clean": True,
            "pilot_verified": 8,
            "destination_file_ids": 8,
            "non_pilot_not_started": 870,
            "outside_digest_stable": True,
            "active_claims": 0,
            "active_leases": 0,
            "retry_scheduled": 0,
            "second_run_new_files": 0,
            "step9_unchanged": True,
        }

    def cleanup(self) -> dict[str, Any]:
        release_failures = []
        for row_id in sorted(self.claimed_ids):
            if not self.repository.release(row_id, self.worker_id):
                release_failures.append(row_id)
        remaining_spool = (
            list(self.options.spool_root.glob("step10-*.transfer"))
            if self.options.spool_root.exists()
            else []
        )
        if release_failures or remaining_spool:
            raise PilotSafetyError("Pilot cleanup could not be proven")
        return {
            "released_claims": len(self.claimed_ids),
            "spool_files_remaining": 0,
        }

    def _all(self, table: str, columns: str) -> list[dict]:
        return list(
            self.client.table(table)
            .select(columns)
            .range(0, 999)
            .execute()
            .data
            or []
        )


def _clean_pilot_row(row: Mapping[str, Any], root_id: str) -> bool:
    clean_attempt_state = (
        row.get("upload_status") == "NOT_STARTED"
        and int(row.get("upload_attempt_count") or 0) == 0
    ) or (
        row.get("upload_status") == "QUEUED"
        and 1 <= int(row.get("upload_attempt_count") or 0) < 5
    )
    return bool(
        row.get("destination_folder_id") == root_id
        and clean_attempt_state
        and row.get("verification_level") == "SOURCE_HASH_VERIFIED"
        and not row.get("destination_google_file_id")
        and not row.get("claim_owner")
        and not row.get("claim_expires_at")
        and not row.get("next_retry_at")
        and not row.get("upload_completed_at")
        and not row.get("verified_at")
        and row.get("upload_status") not in TERMINAL
    )


def _outside_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    safe = sorted(
        (
            str(row.get("id")),
            str(row.get("upload_status")),
            str(row.get("verification_level")),
            bool(row.get("destination_google_file_id")),
            bool(row.get("claim_owner")),
            bool(row.get("next_retry_at")),
        )
        for row in rows
    )
    return hashlib.sha256(
        json.dumps(safe, sort_keys=True).encode()
    ).hexdigest()[:16]


def _step9_digest(
    assets: Iterable[Mapping[str, Any]],
    relationships: Iterable[Mapping[str, Any]],
    sources: Iterable[Mapping[str, Any]],
) -> str:
    safe = {
        "assets": sorted(str(row.get("id")) for row in assets),
        "relationships": sorted(
            (
                str(row.get("asset_id")),
                str(row.get("source_file_id")),
            )
            for row in relationships
        ),
        "sources": sorted(
            (
                str(row.get("id")),
                str(row.get("hash_status")),
                str(row.get("processing_status")),
                str(row.get("decision")),
            )
            for row in sources
        ),
    }
    return hashlib.sha256(
        json.dumps(safe, sort_keys=True).encode()
    ).hexdigest()[:16]


def _event(
    candidate: PilotCandidate,
    event_type: str,
    event_status: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "asset_id": candidate.asset_id,
        "asset_destination_id": candidate.lifecycle_id,
        "event_type": event_type,
        "event_status": event_status,
        "message": f"Step 10 pilot {event_type.lower()}",
        "details": dict(details or {}),
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _safe_error(exc: Exception) -> str:
    return " ".join(str(exc).replace("\r", " ").replace("\n", " ").split())[
        :500
    ]
