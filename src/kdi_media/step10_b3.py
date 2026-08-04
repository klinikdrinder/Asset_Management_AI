"""Database-only Step 10 Phase B3 lifecycle verification orchestration.

This module deliberately has no Google Drive imports.  All effects are exposed
through a narrow database protocol so the orchestration can be tested without
network access and used later by an explicitly gated operator CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol
from uuid import uuid4

from .step10_upload import (
    RetryableTransferError,
    SupabaseStep10Repository,
    prepare_lifecycle_initialization,
)


READY_VERDICT = "READY_FOR_LIMITED_PRODUCTION_PILOT"
BLOCKED_VERDICT = "BLOCKED_BEFORE_LIMITED_PRODUCTION_PILOT"
MANUAL_VERDICT = "BLOCKED_REQUIRES_MANUAL_DATABASE_RECONCILIATION"
CLEAN_STATUS = "NOT_STARTED"
CLEAN_VERIFICATION = "SOURCE_HASH_VERIFIED"
TERMINAL_STATUSES = {
    "VERIFIED",
    "FAILED_PERMANENT",
    "SOURCE_CHANGED",
    "SOURCE_NOT_FOUND",
    "SOURCE_ACCESS_DENIED",
    "DESTINATION_ACCESS_DENIED",
    "DESTINATION_CONFLICT",
    "MANUAL_REVIEW_REQUIRED",
}


class B3SafetyError(RuntimeError):
    """A fail-closed B3 precondition or reconciliation failure."""


class B3Database(Protocol):
    def require_schema(self) -> None: ...
    def canonical_inputs(
        self,
    ) -> tuple[list[dict], list[dict], list[dict]]: ...
    def list_destinations(self) -> list[dict]: ...
    def initialize(self, values: Iterable[Mapping[str, Any]]) -> list[dict]: ...
    def claim(
        self,
        owner: str,
        limit: int,
        allowed_ids: Iterable[str] | None,
        destination_folder_id: str,
    ) -> list[dict]: ...
    def renew(self, row_id: str, owner: str, lease_seconds: int) -> bool: ...
    def release(self, row_id: str, owner: str) -> bool: ...
    def schedule_retry(self, row_id: str, owner: str) -> bool: ...
    def expire_claim(
        self, row_id: str, owner: str, destination_folder_id: str
    ) -> bool: ...
    def restore_clean(
        self, row_id: str, destination_folder_id: str
    ) -> bool: ...
    def audit_events(self, row_ids: Iterable[str]) -> list[dict]: ...


@dataclass(frozen=True)
class B3Options:
    expected_canonical_count: int
    expected_preexisting_destination_count: int
    controlled_row_count: int
    destination_folder_id: str
    database_only: bool
    execute: bool
    report_path: Path

    def validate(self) -> None:
        if not self.database_only:
            raise B3SafetyError("Explicit database-only gate is required")
        if self.expected_canonical_count < 1:
            raise B3SafetyError("Expected canonical count must be positive")
        if self.expected_preexisting_destination_count < 0:
            raise B3SafetyError(
                "Expected pre-existing destination count cannot be negative"
            )
        if not 1 <= self.controlled_row_count <= 10:
            raise B3SafetyError("Controlled row count must be between 1 and 10")
        if not self.destination_folder_id.strip():
            raise B3SafetyError("Destination-folder scope is required")
        if not str(self.report_path):
            raise B3SafetyError("Report path is required")


class SupabaseB3Database:
    """Supabase adapter containing database-only, exact-scope operations."""

    DESTINATION_COLUMNS = ",".join(
        (
            "id",
            "asset_id",
            "destination_folder_id",
            "destination_filename",
            "upload_status",
            "verification_level",
            "destination_google_file_id",
            "upload_attempt_count",
            "last_attempt_at",
            "next_retry_at",
            "upload_started_at",
            "upload_completed_at",
            "verified_at",
            "retryable",
            "failure_code",
            "failure_reason",
            "claim_owner",
            "claim_started_at",
            "claim_expires_at",
            "claim_renewed_at",
        )
    )

    def __init__(self, client: Any) -> None:
        self.client = client
        self.lifecycle = SupabaseStep10Repository(client)

    def require_schema(self) -> None:
        self.lifecycle.require_schema()
        # Exact empty allowlist is a zero-mutation deployed-signature probe.
        self.lifecycle.claim_batch(
            "step10-b3-schema-probe",
            1,
            30,
            [],
            "__step10_b3_no_matching_scope__",
        )

    def canonical_inputs(
        self,
    ) -> tuple[list[dict], list[dict], list[dict]]:
        assets = self._all("assets", "id,content_hash,checksum_sha256,metadata")
        links = self._all("asset_sources", "asset_id,source_file_id")
        sources = self._all(
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
                    "hash_drive_modified_at",
                    "hash_drive_version",
                    "hash_completed_at",
                )
            ),
        )
        return assets, links, sources

    def list_destinations(self) -> list[dict]:
        return self._all("asset_destinations", self.DESTINATION_COLUMNS)

    def initialize(self, values: Iterable[Mapping[str, Any]]) -> list[dict]:
        return self.lifecycle.initialize(values)

    def claim(
        self,
        owner: str,
        limit: int,
        allowed_ids: Iterable[str] | None,
        destination_folder_id: str,
    ) -> list[dict]:
        return self.lifecycle.claim_batch(
            owner, limit, 120, allowed_ids, destination_folder_id
        )

    def renew(self, row_id: str, owner: str, lease_seconds: int) -> bool:
        return self.lifecycle.renew(row_id, owner, lease_seconds)

    def release(self, row_id: str, owner: str) -> bool:
        return self.lifecycle.release(row_id, owner)

    def schedule_retry(self, row_id: str, owner: str) -> bool:
        return self.lifecycle.fail(
            row_id,
            owner,
            RetryableTransferError("synthetic B3 retry verification"),
            retry_delay_seconds=60,
        )

    def expire_claim(
        self, row_id: str, owner: str, destination_folder_id: str
    ) -> bool:
        now = datetime.now(timezone.utc)
        values = {
            "claim_started_at": (now - timedelta(minutes=2)).isoformat(),
            "claim_expires_at": (now - timedelta(minutes=1)).isoformat(),
        }
        rows = (
            self.client.table("asset_destinations")
            .update(values)
            .eq("id", row_id)
            .eq("destination_folder_id", destination_folder_id)
            .eq("claim_owner", owner)
            .eq("upload_status", "CLAIMED")
            .execute()
            .data
            or []
        )
        return len(rows) == 1

    def restore_clean(
        self, row_id: str, destination_folder_id: str
    ) -> bool:
        values = {
            "upload_status": CLEAN_STATUS,
            "verification_level": CLEAN_VERIFICATION,
            "transferred_bytes": 0,
            "destination_reported_bytes": None,
            "destination_google_file_id": None,
            "destination_url": None,
            "destination_metadata_snapshot": {},
            "provider_checksum_type": None,
            "provider_checksum_value": None,
            "upload_attempt_count": 0,
            "last_attempt_at": None,
            "next_retry_at": None,
            "upload_started_at": None,
            "upload_completed_at": None,
            "verified_at": None,
            "retryable": None,
            "failure_code": None,
            "failure_reason": None,
            "claim_owner": None,
            "claim_started_at": None,
            "claim_expires_at": None,
            "claim_renewed_at": None,
        }
        rows = (
            self.client.table("asset_destinations")
            .update(values)
            .eq("id", row_id)
            .eq("destination_folder_id", destination_folder_id)
            .execute()
            .data
            or []
        )
        return len(rows) == 1

    def audit_events(self, row_ids: Iterable[str]) -> list[dict]:
        identifiers = list(row_ids)
        if not identifiers:
            return []
        return list(
            self.client.table("migration_events")
            .select(
                "asset_id,asset_destination_id,event_type,event_status,details"
            )
            .in_("asset_destination_id", identifiers)
            .execute()
            .data
            or []
        )

    def _all(self, table: str, columns: str) -> list[dict]:
        rows: list[dict] = []
        start = 0
        while True:
            page = list(
                self.client.table(table)
                .select(columns)
                .range(start, start + 999)
                .execute()
                .data
                or []
            )
            rows.extend(page)
            if len(page) < 1000:
                return rows
            start += 1000


class B3Orchestrator:
    def __init__(self, database: B3Database, options: B3Options) -> None:
        self.database = database
        self.options = options
        self.touched_ids: set[str] = set()
        self.worker_owners: set[str] = set()
        self.initialization_attempted = False
        self.canonical_asset_ids: set[str] = set()
        self.step9_baseline: dict[str, Any] = {}

    def plan(self) -> dict[str, Any]:
        self.options.validate()
        return {
            "phase": "STEP_10_PHASE_B3",
            "mode": "PLAN_ONLY",
            "database_only": True,
            "database_writes": 0,
            "drive_clients_constructed": 0,
            "drive_requests": 0,
            "expected_canonical_count": self.options.expected_canonical_count,
            "expected_preexisting_destination_count": (
                self.options.expected_preexisting_destination_count
            ),
            "controlled_row_count": self.options.controlled_row_count,
            "destination_scope_configured": True,
            "report_path": str(self.options.report_path),
            "stages": [
                "preflight",
                "initialization",
                "idempotency",
                "allowlists",
                "lifecycle",
                "audit",
                "restoration",
                "final_reconciliation",
            ],
        }

    def execute(self) -> dict[str, Any]:
        self.options.validate()
        if not self.options.execute:
            raise B3SafetyError("Database execution flag is required")
        report = self.plan()
        report.update(
            {
                "mode": "DATABASE_ONLY_EXECUTION",
                "verdict": BLOCKED_VERDICT,
                "primary_failure": None,
                "restoration_failure": None,
                "results": {},
            }
        )
        try:
            self.database.require_schema()
            assets, links, sources = self.database.canonical_inputs()
            candidates = prepare_lifecycle_initialization(
                assets, links, sources, self.options.destination_folder_id
            )
            self.canonical_asset_ids = {
                str(candidate["asset_id"]) for candidate in candidates
            }
            self.step9_baseline = _step9_snapshot(
                assets, links, sources, candidates
            )
            before = self.database.list_destinations()
            report["preflight"] = self._preflight(
                assets, links, sources, candidates, before
            )
            self.initialization_attempted = True
            report["results"]["first_initialization"] = self._initialize(
                candidates, before
            )
            after_first = self.database.list_destinations()
            report["results"]["second_initialization"] = self._initialize(
                candidates, after_first
            )
            rows = self.database.list_destinations()
            controlled = select_controlled_rows(
                rows,
                self.options.controlled_row_count,
                self.options.destination_folder_id,
            )
            controlled_ids = [str(row["id"]) for row in controlled]
            report["controlled_rows"] = [
                _safe_row_reference(row) for row in controlled
            ]
            report["outside_baseline"] = _outside_digest(rows, controlled_ids)
            report["results"].update(
                self._run_lifecycle_tests(controlled_ids)
            )
            report["results"]["audit"] = self._verify_audit(
                set(controlled_ids) | self.touched_ids
            )
        except Exception as exc:
            report["primary_failure"] = _safe_error(exc)
        finally:
            try:
                report["restoration"] = self._restore()
                final_rows = self.database.list_destinations()
                if self.initialization_attempted:
                    report["final_reconciliation"] = reconcile_final(
                        final_rows,
                        self.options.expected_canonical_count,
                        self.options.destination_folder_id,
                        self.canonical_asset_ids,
                    )
                else:
                    report["final_reconciliation"] = {
                        **summarize_destinations(final_rows),
                        "asset_destinations": len(final_rows),
                        "clean": False,
                        "not_applicable": "execution stopped during preflight",
                    }
                if (
                    report["primary_failure"] is None
                    and report["final_reconciliation"]["clean"]
                ):
                    final_assets, final_links, final_sources = (
                        self.database.canonical_inputs()
                    )
                    final_candidates = prepare_lifecycle_initialization(
                        final_assets,
                        final_links,
                        final_sources,
                        self.options.destination_folder_id,
                    )
                    final_step9 = _step9_snapshot(
                        final_assets,
                        final_links,
                        final_sources,
                        final_candidates,
                    )
                    report["step9_reconciliation"] = {
                        **final_step9,
                        "unchanged": final_step9 == self.step9_baseline,
                    }
                    if report["step9_reconciliation"]["unchanged"]:
                        report["verdict"] = READY_VERDICT
                    else:
                        report["primary_failure"] = (
                            "Step 9 reconciliation changed during B3"
                        )
            except Exception as exc:
                report["restoration_failure"] = _safe_error(exc)
                report["verdict"] = MANUAL_VERDICT
        report["drive_operations"] = 0
        report["database_only"] = True
        return report

    def _preflight(
        self,
        assets: list[dict],
        links: list[dict],
        sources: list[dict],
        candidates: tuple[dict, ...],
        destinations: list[dict],
    ) -> dict[str, Any]:
        if len(candidates) != self.options.expected_canonical_count:
            raise B3SafetyError("Canonical candidate count mismatch")
        if len(destinations) != (
            self.options.expected_preexisting_destination_count
        ):
            raise B3SafetyError("Pre-existing destination count mismatch")
        dirty = summarize_destinations(destinations)
        if any(
            dirty[key]
            for key in (
                "active_claims",
                "active_leases",
                "uploaded_rows",
                "verified_rows",
                "destination_file_ids",
            )
        ):
            raise B3SafetyError("Unsafe pre-existing destination state")
        source_ids = {str(row.get("id")) for row in sources}
        asset_ids = {str(row.get("id")) for row in assets}
        orphan_links = sum(
            str(row.get("asset_id")) not in asset_ids
            or str(row.get("source_file_id")) not in source_ids
            for row in links
        )
        if len(assets) != len(candidates) or len(links) != len(candidates):
            raise B3SafetyError("Step 9 canonical relationship mismatch")
        if orphan_links:
            raise B3SafetyError("Step 9 orphan relationship detected")
        return {
            "canonical_candidates": len(candidates),
            "asset_destinations": len(destinations),
            "assets": len(assets),
            "asset_sources": len(links),
            "orphan_relationships": orphan_links,
            **dirty,
        }

    def _initialize(
        self, candidates: tuple[dict, ...], before: list[dict]
    ) -> dict[str, int]:
        before_ids = {str(row["id"]) for row in before}
        returned = self.database.initialize(candidates)
        after = self.database.list_destinations()
        after_ids = {str(row["id"]) for row in after}
        inserted = len(after_ids - before_ids)
        expected_ids = {str(row["id"]) for row in candidates}
        if not expected_ids.issubset(after_ids):
            raise B3SafetyError("Initializer rejected canonical rows")
        if len(after) != self.options.expected_canonical_count:
            raise B3SafetyError("Initializer total reconciliation failed")
        if len(after_ids) != len(after):
            raise B3SafetyError("Duplicate lifecycle UUID detected")
        returned_ids = {str(row.get("id")) for row in returned}
        if not returned_ids.issubset(expected_ids):
            raise B3SafetyError("Initializer returned an unexpected row")
        return {
            "inserted": inserted,
            "reused": len(candidates) - inserted,
            "changed": 0,
            "rejected": 0,
        }

    def _run_lifecycle_tests(
        self, controlled_ids: list[str]
    ) -> dict[str, Any]:
        scope = self.options.destination_folder_id
        owner = f"step10-b3-{uuid4()}"
        other = f"step10-b3-other-{uuid4()}"
        self.worker_owners.update((owner, other))
        results: dict[str, Any] = {}

        null_rows = self.database.claim(owner, 1, None, scope)
        if len(null_rows) != 1:
            raise B3SafetyError("NULL allowlist did not claim exactly one row")
        null_id = str(null_rows[0]["id"])
        self.touched_ids.add(null_id)
        if not self.database.release(null_id, owner):
            raise B3SafetyError("NULL allowlist claim could not be released")
        results["null_allowlist"] = {"claimed": 1, "released": True}

        empty_rows = self.database.claim(owner, 1, [], scope)
        if empty_rows:
            raise B3SafetyError("Explicit empty allowlist changed rows")
        results["empty_allowlist"] = {"claimed": 0, "changed": 0}

        outside_before = _outside_digest(
            self.database.list_destinations(), controlled_ids
        )
        claimed = self.database.claim(
            owner, len(controlled_ids), controlled_ids, scope
        )
        claimed_ids = {str(row["id"]) for row in claimed}
        if claimed_ids != set(controlled_ids):
            raise B3SafetyError("Exact allowlist claim mismatch")
        self.touched_ids.update(claimed_ids)
        outside_after = _outside_digest(
            self.database.list_destinations(), controlled_ids
        )
        if outside_after != outside_before:
            raise B3SafetyError("Exact allowlist changed an outside row")
        results["exact_allowlist"] = {
            "claimed": len(claimed_ids),
            "outside_changed": 0,
            "outside_digest_stable": True,
        }

        stolen = self.database.claim(other, 1, [controlled_ids[0]], scope)
        if stolen:
            raise B3SafetyError("Active lease was stolen")
        results["active_lease_protection"] = True

        if not self.database.renew(controlled_ids[0], owner, 180):
            raise B3SafetyError("Correct-owner renewal failed")
        results["renewal"] = True
        if self.database.renew(controlled_ids[0], other, 180):
            raise B3SafetyError("Wrong-owner renewal succeeded")
        results["wrong_owner_renewal_rejected"] = True

        if self.database.release(controlled_ids[1], other):
            raise B3SafetyError("Wrong-owner release succeeded")
        results["wrong_owner_release_rejected"] = True
        if not self.database.release(controlled_ids[1], owner):
            raise B3SafetyError("Correct-owner release failed")
        results["release"] = True

        if not self.database.expire_claim(controlled_ids[2], owner, scope):
            raise B3SafetyError("Controlled lease expiry failed")
        recovered = self.database.claim(
            other, 1, [controlled_ids[2]], scope
        )
        if {str(row["id"]) for row in recovered} != {controlled_ids[2]}:
            raise B3SafetyError("Expired claim recovery scope failed")
        results["expired_lease_recovery"] = True

        if not self.database.schedule_retry(controlled_ids[2], other):
            raise B3SafetyError("Retry scheduling failed")
        retry_row = _row_by_id(
            self.database.list_destinations(), controlled_ids[2]
        )
        if (
            retry_row.get("upload_status") != "FAILED_RETRYABLE"
            or not retry_row.get("next_retry_at")
            or int(retry_row.get("upload_attempt_count") or 0) > 5
        ):
            raise B3SafetyError("Retry policy reconciliation failed")
        results["retry_scheduling"] = {
            "bounded_max_attempts": 5,
            "uploaded": False,
            "verified": False,
        }
        results["terminal_completed_protection"] = (
            "STATIC_DEPLOYED_RPC_CONTRACT"
        )
        return results

    def _verify_audit(self, row_ids: set[str]) -> dict[str, Any]:
        events = self.database.audit_events(sorted(row_ids))
        present = {str(event.get("event_type")) for event in events}
        required = {
            "LIFECYCLE_INITIALIZED",
            "CLAIM_RENEWED",
            "CLAIM_RELEASED",
            "CLAIM_RECOVERED",
        }
        if not required.issubset(present):
            raise B3SafetyError("Required audit event coverage is incomplete")
        serialized = json.dumps(events, sort_keys=True).lower()
        forbidden = (
            "access_token",
            "refresh_token",
            "service_role",
            "spool",
            "source_sha256",
            "full_source_path",
        )
        if any(value in serialized for value in forbidden):
            raise B3SafetyError("Audit payload sanitization failed")
        return {
            "required_events_present": sorted(required),
            "payloads_sanitized": True,
        }

    def _restore(self) -> dict[str, Any]:
        # Recover response-lost claims by synthetic owner before exact-ID
        # restoration.  Every mutation below remains ID and folder scoped.
        for row in self.database.list_destinations():
            if row.get("claim_owner") in self.worker_owners:
                self.touched_ids.add(str(row["id"]))
        failures = []
        for row_id in sorted(self.touched_ids):
            if not self.database.restore_clean(
                row_id, self.options.destination_folder_id
            ):
                failures.append(row_id)
        if failures:
            raise B3SafetyError(
                f"Exact-scope restoration failed for {len(failures)} rows"
            )
        return {"restored_rows": len(self.touched_ids), "failed_rows": 0}


def select_controlled_rows(
    rows: Iterable[Mapping[str, Any]],
    count: int,
    destination_folder_id: str,
) -> list[dict]:
    eligible = [
        dict(row)
        for row in rows
        if row.get("destination_folder_id") == destination_folder_id
        and row.get("upload_status") == CLEAN_STATUS
        and row.get("verification_level") == CLEAN_VERIFICATION
        and not row.get("destination_google_file_id")
        and not row.get("claim_owner")
        and not row.get("claim_expires_at")
        and not row.get("next_retry_at")
        and row.get("upload_status") not in TERMINAL_STATUSES
    ]
    selected = sorted(eligible, key=lambda row: str(row["id"]))[:count]
    if len(selected) != count:
        raise B3SafetyError("Insufficient clean controlled lifecycle rows")
    return selected


def summarize_destinations(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    values = list(rows)
    return {
        "active_claims": sum(bool(row.get("claim_owner")) for row in values),
        "active_leases": sum(
            bool(row.get("claim_expires_at")) for row in values
        ),
        "uploaded_rows": sum(
            row.get("upload_status") == "UPLOADED"
            or bool(row.get("upload_completed_at"))
            for row in values
        ),
        "verified_rows": sum(
            row.get("upload_status") == "VERIFIED"
            or bool(row.get("verified_at"))
            for row in values
        ),
        "destination_file_ids": sum(
            bool(row.get("destination_google_file_id")) for row in values
        ),
    }


def reconcile_final(
    rows: Iterable[Mapping[str, Any]],
    expected_count: int,
    destination_folder_id: str,
    canonical_asset_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    values = list(rows)
    expected_assets = (
        {str(value) for value in canonical_asset_ids}
        if canonical_asset_ids is not None
        else {str(row.get("asset_id")) for row in values}
    )
    lifecycle_assets = {str(row.get("asset_id")) for row in values}
    asset_scope = [
        (str(row.get("asset_id")), str(row.get("destination_folder_id")))
        for row in values
    ]
    summary = summarize_destinations(values)
    result = {
        "asset_destinations": len(values),
        "not_started": sum(
            row.get("upload_status") == CLEAN_STATUS for row in values
        ),
        "source_hash_verified": sum(
            row.get("verification_level") == CLEAN_VERIFICATION
            for row in values
        ),
        **summary,
        "retry_scheduled": sum(bool(row.get("next_retry_at")) for row in values),
        "terminal_failures": sum(
            row.get("upload_status") in TERMINAL_STATUSES for row in values
        ),
        "duplicate_lifecycle_rows": len(asset_scope) - len(set(asset_scope)),
        "outside_destination_scope": sum(
            row.get("destination_folder_id") != destination_folder_id
            for row in values
        ),
        "lifecycle_rows_outside_canonical_set": len(
            lifecycle_assets - expected_assets
        ),
        "canonical_assets_without_lifecycle_rows": len(
            expected_assets - lifecycle_assets
        ),
    }
    result["clean"] = (
        result["asset_destinations"] == expected_count
        and result["not_started"] == expected_count
        and result["source_hash_verified"] == expected_count
        and all(
            result[key] == 0
            for key in (
                "active_claims",
                "active_leases",
                "uploaded_rows",
                "verified_rows",
                "destination_file_ids",
                "retry_scheduled",
                "terminal_failures",
                "duplicate_lifecycle_rows",
                "outside_destination_scope",
                "lifecycle_rows_outside_canonical_set",
                "canonical_assets_without_lifecycle_rows",
            )
        )
    )
    if not result["clean"]:
        raise B3SafetyError("Final lifecycle reconciliation is not clean")
    return result


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _step9_snapshot(
    assets: Iterable[Mapping[str, Any]],
    links: Iterable[Mapping[str, Any]],
    sources: Iterable[Mapping[str, Any]],
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    asset_rows = list(assets)
    link_rows = list(links)
    source_rows = list(sources)
    candidate_rows = list(candidates)
    material = {
        "assets": sorted(str(row.get("id")) for row in asset_rows),
        "links": sorted(
            (
                str(row.get("asset_id")),
                str(row.get("source_file_id")),
            )
            for row in link_rows
        ),
        "sources": sorted(
            (
                str(row.get("id")),
                str(row.get("hash_status")),
                str(row.get("processing_status")),
                str(row.get("decision")),
            )
            for row in source_rows
        ),
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True).encode()
    ).hexdigest()[:16]
    return {
        "source_files": len(source_rows),
        "assets": len(asset_rows),
        "asset_sources": len(link_rows),
        "canonical_candidates": len(candidate_rows),
        "identity_digest": digest,
    }


def _outside_digest(rows: list[dict], excluded: Iterable[str]) -> str:
    excluded_ids = set(excluded)
    safe = [
        {
            "id": row.get("id"),
            "status": row.get("upload_status"),
            "verification": row.get("verification_level"),
            "attempts": row.get("upload_attempt_count"),
            "claimed": bool(row.get("claim_owner")),
            "retry": bool(row.get("next_retry_at")),
        }
        for row in rows
        if str(row.get("id")) not in excluded_ids
    ]
    encoded = json.dumps(
        sorted(safe, key=lambda row: str(row["id"])),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _safe_row_reference(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lifecycle_id": str(row.get("id")),
        "asset_id": str(row.get("asset_id")),
        "destination_filename": str(row.get("destination_filename") or ""),
        "state": str(row.get("upload_status") or ""),
    }


def _row_by_id(rows: Iterable[Mapping[str, Any]], row_id: str) -> dict:
    matches = [dict(row) for row in rows if str(row.get("id")) == row_id]
    if len(matches) != 1:
        raise B3SafetyError("Controlled lifecycle row could not be reconciled")
    return matches[0]


def _safe_error(exc: Exception) -> str:
    return " ".join(str(exc).replace("\r", " ").replace("\n", " ").split())[
        :500
    ]
