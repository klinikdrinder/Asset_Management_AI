"""Explicitly gated, resumable Step 10 full-production orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Mapping
from uuid import uuid4

from .google_drive import (
    create_destination_write_drive_service,
    create_readonly_drive_service,
    load_destination_oauth_config,
    load_oauth_config,
)
from .step10_upload import (
    DestinationRootGuard,
    DriveResumableTransfer,
    Step10Error,
    Step10UploadWorker,
    SupabaseStep10Repository,
    build_destination_plan,
    lookup_destination_identity,
    read_destination_metadata,
    read_source_metadata,
    resolve_category_folder,
    route_category,
    select_canonical_source,
    verify_destination_metadata,
    verify_destination_sha256,
    DriveCredentialProfile,
)


READY = "STEP_10_COMPLETE_READY_FOR_STEP_11"
BLOCKED = "BLOCKED_DURING_FULL_STEP_10_UPLOAD"
MANUAL = "BLOCKED_REQUIRES_MANUAL_PRODUCTION_RECONCILIATION"
APPROVED_ROOT = "1CdmowWV5TAk5R9D5yl2cOT8Plx3ihZgl"


@dataclass(frozen=True)
class ProductionOptions:
    execute: bool
    authorize: bool
    expected_total: int
    expected_completed: int
    expected_remaining: int
    root_id: str
    source_profile: str
    destination_profile: str
    batch_size: int
    report_path: Path
    pilot_report_path: Path
    spool_root: Path

    def validate(self) -> None:
        if (self.expected_total, self.expected_completed, self.expected_remaining) != (
            878,
            8,
            870,
        ):
            raise ValueError("Expected production counts must be 878/8/870")
        if not 1 <= self.batch_size <= 50:
            raise ValueError("Batch size must be between 1 and 50")
        if self.source_profile != "source_readonly":
            raise ValueError("Source profile must be source_readonly")
        if self.destination_profile != "destination_write":
            raise ValueError("Destination profile must be destination_write")
        if self.root_id != APPROVED_ROOT:
            raise ValueError("Destination root is not the approved KDI Master root")
        if self.execute and not self.authorize:
            raise ValueError("Drive transfer authorization is required")


class ProductionOrchestrator:
    DEST_COLS = (
        "id,asset_id,selected_source_file_id,destination_folder_id,"
        "destination_google_file_id,destination_filename,"
        "destination_relative_path,upload_status,verification_level,"
        "expected_bytes,upload_attempt_count,claim_owner,claim_expires_at,"
        "next_retry_at,upload_completed_at,verified_at,failure_code"
    )
    SOURCE_COLS = (
        "id,source_folder_id,google_file_id,file_name,mime_type,"
        "file_extension,size_bytes,decision,processing_status,hash_status,"
        "hash_algorithm,content_sha256,hash_expected_bytes,"
        "hash_drive_mime_type,hash_drive_modified_at,hash_drive_version,"
        "trashed,is_missing,access_status,hash_completed_at"
    )

    def __init__(self, client: Any, options: ProductionOptions) -> None:
        self.client = client
        self.options = options
        self.repo = SupabaseStep10Repository(client)
        self.worker_id = f"step10-production-{uuid4()}"
        self.source_service: Any = None
        self.destination_service: Any = None
        self.folders: dict[str, str] = {}
        self.worker: Step10UploadWorker | None = None
        self.assets: dict[str, dict] = {}
        self.sources: dict[str, dict] = {}
        self.links: list[dict] = []
        self.pilot_ids: set[str] = set()
        self.pilot_baseline: dict[str, str] = {}

    def plan(self) -> dict[str, Any]:
        self.options.validate()
        return {
            "mode": "PLAN_ONLY",
            "database_writes": 0,
            "drive_requests": 0,
            "batch_size": self.options.batch_size,
            "concurrency": 1,
            "expected_total": 878,
            "expected_completed": 8,
            "expected_remaining": 870,
        }

    def execute(self) -> dict[str, Any]:
        self.options.validate()
        if not self.options.execute:
            return self.plan()
        report = self.plan() | {
            "mode": "LIVE_FULL_PRODUCTION",
            "started_at": _now(),
            "verdict": BLOCKED,
            "batches": [],
            "totals": _totals(),
            "exceptions": [],
        }
        try:
            eligible = self._preflight(report)
            self._start_services()
            if eligible:
                self._run_batches(eligible, report)
            reconciliation = self._reconcile_all(report)
            report["final_reconciliation"] = reconciliation
            report["verdict"] = READY if reconciliation["clean"] else BLOCKED
        except Exception as exc:
            report["failure"] = _safe(str(exc))
            if self._spool_files():
                report["verdict"] = MANUAL
        finally:
            report["finished_at"] = _now()
            report["spool_files_remaining"] = len(self._spool_files())
            write_report(self.options.report_path, report)
        return report

    def _preflight(self, report: dict[str, Any]) -> list[str]:
        rows = self._all("asset_destinations", self.DEST_COLS)
        if len(rows) != 878:
            raise RuntimeError("Lifecycle total mismatch")
        pilot_report = json.loads(
            self.options.pilot_report_path.read_text(encoding="utf-8")
        )
        self.pilot_ids = set(pilot_report["pilot_lifecycle_ids"])
        if len(self.pilot_ids) != 8:
            raise RuntimeError("Pilot exclusion set is not exactly eight")
        pilot = [row for row in rows if row["id"] in self.pilot_ids]
        outside = [row for row in rows if row["id"] not in self.pilot_ids]
        if len(pilot) != 8 or len(outside) != 870:
            raise RuntimeError("Pilot/non-pilot partition mismatch")
        if any(
            row["upload_status"] != "VERIFIED"
            or not row["destination_google_file_id"]
            for row in pilot
        ):
            raise RuntimeError("Pilot baseline is not verified")
        self.pilot_baseline = {
            row["id"]: row["destination_google_file_id"] for row in pilot
        }
        if any(row["claim_owner"] or row["claim_expires_at"] for row in rows):
            raise RuntimeError("Active claim or lease exists at preflight")
        self.assets = {
            row["id"]: row
            for row in self._all(
                "assets", "id,content_hash,checksum_sha256,metadata"
            )
        }
        self.links = self._all("asset_sources", "asset_id,source_file_id")
        self.sources = {
            row["id"]: row
            for row in self._all("source_files", self.SOURCE_COLS)
        }
        if not (
            len(self.assets) == len(self.links) == 878
            and len(self.sources) == 886
        ):
            raise RuntimeError("Step 9 reconciliation count mismatch")
        eligible = [
            row["id"]
            for row in outside
            if row["upload_status"]
            in {"NOT_STARTED", "QUEUED", "FAILED_RETRYABLE"}
            and int(row["upload_attempt_count"] or 0) < 5
        ]
        unresolved = [
            row
            for row in outside
            if row["upload_status"] != "VERIFIED"
            and row["id"] not in eligible
        ]
        if unresolved:
            raise RuntimeError("Unresolved non-pilot lifecycle state at preflight")
        report["preflight"] = {
            "total": 878,
            "pilot_verified": 8,
            "production_cohort": 870,
            "eligible_now": len(eligible),
            "already_verified_non_pilot": 870 - len(eligible),
            "pilot_excluded": True,
            "free_spool_bytes": shutil.disk_usage(
                self.options.spool_root.parent
            ).free,
        }
        return eligible

    def _start_services(self) -> None:
        source_config = load_oauth_config()
        destination_config = load_destination_oauth_config()
        if source_config.token_file.resolve() == destination_config.token_file.resolve():
            raise RuntimeError("Source and destination tokens are shared")
        self.source_service = create_readonly_drive_service(source_config)
        self.destination_service = create_destination_write_drive_service(
            destination_config
        )
        root_guard = DestinationRootGuard(self.options.root_id)
        self.folders = {
            name: resolve_category_folder(
                self.destination_service, root_guard, name, allow_create=False
            )
            for name in ("Images", "Videos", "Documents")
        }
        guard = DestinationRootGuard(self.options.root_id, self.folders)
        self.worker = Step10UploadWorker(
            repository=self.repo,
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

    def _run_batches(self, eligible: list[str], report: dict[str, Any]) -> None:
        allowed = set(eligible)
        batch_number = 0
        while True:
            claimed = self.repo.claim_batch(
                self.worker_id,
                self.options.batch_size,
                3600,
                sorted(allowed),
                self.options.root_id,
            )
            if not claimed:
                break
            if any(row["id"] in self.pilot_ids for row in claimed):
                raise RuntimeError("Pilot row was claimed")
            batch_number += 1
            batch = {"batch": batch_number, "claimed": len(claimed), "results": []}
            for lifecycle in claimed:
                row_id = lifecycle["id"]
                allowed.discard(row_id)
                try:
                    if not self.repo.renew(row_id, self.worker_id, 3600):
                        raise RuntimeError("Claim renewal failed")
                    asset = self.assets[lifecycle["asset_id"]]
                    source = select_canonical_source(
                        asset, self.links, self.sources.values()
                    )
                    category = route_category(
                        source.file_extension, source.mime_type
                    )
                    result = self.worker.process(
                        lifecycle=lifecycle,
                        asset=asset,
                        source=source,
                        stored_source_row=self.sources[source.id],
                        category_parent_id=self.folders[category],
                        worker_id=self.worker_id,
                        execute=True,
                    )
                    outcome = result["outcome"]
                    report["totals"][
                        "response_loss_recoveries"
                        if outcome == "RECOVERED"
                        else "newly_uploaded"
                    ] += 1
                    report["totals"]["bytes_transferred"] += int(
                        lifecycle["expected_bytes"]
                    )
                    report["totals"]["per_category"][category] += 1
                    batch["results"].append(
                        {"lifecycle_id": row_id, "outcome": outcome}
                    )
                except Step10Error as exc:
                    self.repo.fail(
                        row_id, self.worker_id, exc, retry_delay_seconds=60
                    )
                    key = _failure_key(exc.code)
                    report["totals"][key] += 1
                    report["exceptions"].append(
                        {
                            "lifecycle_id": row_id,
                            "asset_id": lifecycle["asset_id"],
                            "category": exc.code,
                            "attempt_count": lifecycle["upload_attempt_count"],
                            "retryable": exc.retryable,
                        }
                    )
                    batch["results"].append(
                        {"lifecycle_id": row_id, "outcome": exc.code}
                    )
                except Exception:
                    self.repo.release(row_id, self.worker_id)
                    raise
            if self._spool_files():
                raise RuntimeError("Spool cleanup failed after batch")
            report["batches"].append(batch)
            report["totals"]["attempted"] += len(claimed)
            write_report(self.options.report_path, report)

    def _reconcile_all(self, report: dict[str, Any]) -> dict[str, Any]:
        rows = self._all("asset_destinations", self.DEST_COLS)
        verified = [row for row in rows if row["upload_status"] == "VERIFIED"]
        checks = 0
        duplicates = 0
        missing = 0
        metadata_verified = 0
        byte_verified = 0
        sample_candidates: dict[str, tuple[int, dict, Any]] = {}
        for row in verified:
            asset = self.assets[row["asset_id"]]
            source = select_canonical_source(asset, self.links, self.sources.values())
            category = route_category(source.file_extension, source.mime_type)
            plan = build_destination_plan(
                asset,
                source,
                self.options.root_id,
                destination_record_id=row["id"],
            )
            matches = lookup_destination_identity(
                self.destination_service, self.folders[category], plan
            )
            if len(matches) != 1:
                duplicates += max(0, len(matches) - 1)
                missing += int(len(matches) == 0)
                continue
            if matches[0]["id"] != row["destination_google_file_id"]:
                missing += 1
                continue
            verify_destination_metadata(
                matches[0],
                plan=plan,
                expected_parent_id=self.folders[category],
            )
            checks += 1
            metadata_verified += 1
            byte_verified += 1
            extension = source.file_extension.lower()
            current = sample_candidates.get(extension)
            if current is None or plan.expected_bytes < current[0]:
                sample_candidates[extension] = (
                    plan.expected_bytes,
                    row,
                    asset,
                )
        hash_verified = 0
        for _, row, asset in sample_candidates.values():
            level = verify_destination_sha256(
                self.destination_service,
                row["destination_google_file_id"],
                asset["content_hash"],
                enabled=True,
                profile=DriveCredentialProfile.DESTINATION_WRITE,
            )
            if self.repo.set_verification_level(
                row["id"], row["destination_google_file_id"], level
            ):
                hash_verified += 1
        final_rows = self._all("asset_destinations", self.DEST_COLS)
        pilot_stable = all(
            next(row for row in final_rows if row["id"] == row_id)[
                "destination_google_file_id"
            ]
            == file_id
            for row_id, file_id in self.pilot_baseline.items()
        )
        clean = (
            len(verified) == 878
            and checks == 878
            and duplicates == 0
            and missing == 0
            and pilot_stable
            and not any(
                row["claim_owner"]
                or row["claim_expires_at"]
                or row["next_retry_at"]
                or row["failure_code"]
                for row in final_rows
            )
            and not self._spool_files()
        )
        return {
            "clean": clean,
            "verified_rows": len(verified),
            "destination_ids": sum(
                bool(row["destination_google_file_id"]) for row in final_rows
            ),
            "drive_files_verified": checks,
            "metadata_verified": metadata_verified,
            "byte_verified": byte_verified,
            "full_hash_verified": hash_verified,
            "duplicate_identities": duplicates,
            "missing_identities": missing,
            "pilot_destination_ids_stable": pilot_stable,
            "active_claims": sum(bool(row["claim_owner"]) for row in final_rows),
            "active_leases": sum(
                bool(row["claim_expires_at"]) for row in final_rows
            ),
            "retry_scheduled": sum(
                bool(row["next_retry_at"]) for row in final_rows
            ),
        }

    def _spool_files(self) -> list[Path]:
        if not self.options.spool_root.exists():
            return []
        return list(self.options.spool_root.glob("step10-*.transfer"))

    def _all(self, table: str, columns: str) -> list[dict]:
        return list(
            self.client.table(table)
            .select(columns)
            .range(0, 999)
            .execute()
            .data
            or []
        )


def _totals() -> dict[str, Any]:
    return {
        "attempted": 0,
        "newly_uploaded": 0,
        "response_loss_recoveries": 0,
        "retries": 0,
        "source_changed": 0,
        "source_missing": 0,
        "source_access_denied": 0,
        "destination_access_denied": 0,
        "destination_conflicts": 0,
        "terminal_failures": 0,
        "bytes_transferred": 0,
        "per_category": {"Images": 0, "Videos": 0, "Documents": 0},
    }


def _failure_key(code: str) -> str:
    return {
        "SOURCE_CHANGED": "source_changed",
        "SOURCE_NOT_FOUND": "source_missing",
        "SOURCE_ACCESS_DENIED": "source_access_denied",
        "DESTINATION_ACCESS_DENIED": "destination_access_denied",
        "DESTINATION_CONFLICT": "destination_conflicts",
    }.get(code, "terminal_failures")


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())[:500]
