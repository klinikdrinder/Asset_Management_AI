"""Execute an explicitly bounded Step 9 hashing pilot.

This command hashes source occurrences only. It never creates assets,
asset_sources, duplicate groups, or destination copies.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from kdi_media.google_drive import create_readonly_drive_service
from kdi_media.source_folders import create_supabase_client_from_environment
from kdi_media.step9_hashing import (
    HashStatus,
    SourceSnapshot,
    Step9HashWorker,
    SupabaseHashRepository,
    iter_drive_content,
    read_drive_snapshot,
)


PILOT_SOURCE_IDS = {
    "42affe18-4e7b-4333-87fe-7158c410c072": "ALL PATIENT REVIEW",
    "84a6b92b-e075-4f4b-9384-9b6a99acb51e": "Nushad Raw Video",
    "24bec9f0-7325-4706-896b-6d594daeaef2": (
        "Photo/Video for Marketing (Consented by patient)"
    ),
}
ROW_FIELDS = (
    "id,source_folder_id,google_file_id,file_name,mime_type,file_extension,"
    "size_bytes,md5_checksum,drive_modified_at,decision,processing_status,trashed,"
    "is_missing,metadata,hash_algorithm,content_sha256,hash_status,"
    "hash_expected_bytes,hash_observed_bytes,hash_attempt_count,"
    "hash_completed_at,hash_failure_code,hash_failure_reason,hash_retryable,"
    "hash_claim_owner,hash_claimed_at,hash_claim_expires_at,updated_at"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument(
        "--source-file-id", action="append", required=True
    )
    result.add_argument("--report", required=True)
    result.add_argument("--execute", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    selected = tuple(dict.fromkeys(args.source_file_id))
    if not 5 <= len(selected) <= 8:
        raise SystemExit("Pilot must contain between 5 and 8 unique rows")
    if not args.execute:
        raise SystemExit("--execute is required for the approved pilot")

    client = create_supabase_client_from_environment()
    initial = _read_selected(client, selected)
    _validate_selection(initial, selected)
    all_before = _updated_at_map(client)
    assets_before = _count(client, "assets")
    links_before = _count(client, "asset_sources")

    service = create_readonly_drive_service()
    repository = SupabaseHashRepository(client)
    drive_counts = {"metadata": 0, "content_streams": 0}

    def metadata_reader(drive_service: Any, file_id: str) -> SourceSnapshot:
        drive_counts["metadata"] += 1
        return read_drive_snapshot(drive_service, file_id)

    def content_reader(
        drive_service: Any, file_id: str, *, chunk_size: int
    ):
        drive_counts["content_streams"] += 1
        return iter_drive_content(
            drive_service, file_id, chunk_size=chunk_size
        )

    worker = Step9HashWorker(repository, service, metadata_reader)
    first_results = []
    for row in initial:
        before_attempts = row["hash_attempt_count"]
        result = worker.process(
            row["id"],
            "step9-b3-pilot",
            _inventory_snapshot(row),
            content_reader=content_reader,
        )
        final = _read_one(client, row["id"])
        first_results.append(
            _safe_result(
                final,
                attempted=final["hash_attempt_count"] > before_attempts,
                worker_returned_success=result is not None,
            )
        )

    after_first = _read_selected(client, selected)
    first_statuses = {
        status.value: sum(
            row["hash_status"] == status.value for row in after_first
        )
        for status in HashStatus
    }
    first_hashes = {
        row["id"]: (row["content_sha256"], row["hash_attempt_count"])
        for row in after_first
    }
    first_drive_counts = dict(drive_counts)

    second_results = []
    for row in after_first:
        before_attempts = row["hash_attempt_count"]
        result = worker.process(
            row["id"],
            "step9-b3-pilot-rerun",
            _inventory_snapshot(row),
            content_reader=content_reader,
        )
        final = _read_one(client, row["id"])
        previous_hash, previous_attempts = first_hashes[row["id"]]
        second_results.append(
            {
                "source_file_id": row["id"],
                "worker_returned_success": result is not None,
                "skipped_completed_unchanged": (
                    row["hash_status"] == HashStatus.HASHED.value
                    and result is None
                    and final["content_sha256"] == previous_hash
                    and final["hash_attempt_count"] == previous_attempts
                ),
                "hash_unchanged": final["content_sha256"] == previous_hash,
                "attempt_count_unchanged": (
                    final["hash_attempt_count"] == before_attempts
                ),
            }
        )

    final_rows = _read_selected(client, selected)
    all_after = _updated_at_map(client)
    nonselected_changed = sorted(
        row_id
        for row_id, updated_at in all_before.items()
        if row_id not in selected and all_after.get(row_id) != updated_at
    )
    statuses = {
        status.value: sum(row["hash_status"] == status.value for row in final_rows)
        for status in HashStatus
    }
    report = {
        "phase": "STEP_9_PHASE_B3_LIMITED_PILOT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pilot_selected": len(selected),
        "selected_source_file_ids": list(selected),
        "selected_sources": sorted(
            {row["source_folder_id"] for row in final_rows}
        ),
        "first_run": {
            "results": first_results,
            "successfully_hashed": first_statuses[HashStatus.HASHED.value],
            "source_changed": first_statuses[HashStatus.SOURCE_CHANGED.value],
            "retryable_failures": first_statuses[
                HashStatus.FAILED_RETRYABLE.value
            ],
            "permanent_failures": sum(
                first_statuses[value]
                for value in (
                    HashStatus.FAILED_PERMANENT.value,
                    HashStatus.SOURCE_NOT_FOUND.value,
                    HashStatus.SOURCE_ACCESS_DENIED.value,
                    HashStatus.SOURCE_TRASHED.value,
                )
            ),
            "byte_count_mismatches": sum(
                row["hash_failure_code"] == "PARTIAL_DOWNLOAD"
                for row in after_first
            ),
            "drive_metadata_requests": first_drive_counts["metadata"],
            "drive_content_streams": first_drive_counts["content_streams"],
        },
        "second_run": {
            "results": second_results,
            "completed_files_skipped": sum(
                row["skipped_completed_unchanged"]
                for row in second_results
            ),
            "additional_drive_metadata_requests": (
                drive_counts["metadata"] - first_drive_counts["metadata"]
            ),
            "additional_drive_content_streams": (
                drive_counts["content_streams"]
                - first_drive_counts["content_streams"]
            ),
        },
        "final_results": [
            _safe_result(row, attempted=True, worker_returned_success=None)
            for row in final_rows
        ],
        "reconciliation": {
            "pilot_selected": len(selected),
            "successfully_hashed": statuses[HashStatus.HASHED.value],
            "source_changed": statuses[HashStatus.SOURCE_CHANGED.value],
            "retryable_failures": statuses[
                HashStatus.FAILED_RETRYABLE.value
            ],
            "permanent_failures": sum(
                statuses[value]
                for value in (
                    HashStatus.FAILED_PERMANENT.value,
                    HashStatus.SOURCE_NOT_FOUND.value,
                    HashStatus.SOURCE_ACCESS_DENIED.value,
                    HashStatus.SOURCE_TRASHED.value,
                )
            ),
            "other_final_outcomes": sum(
                statuses[value]
                for value in (
                    HashStatus.NOT_STARTED.value,
                    HashStatus.QUEUED.value,
                    HashStatus.HASHING.value,
                )
            ),
            "active_claims_remaining": sum(
                row["hash_claim_owner"] is not None
                or row["hash_claimed_at"] is not None
                or row["hash_claim_expires_at"] is not None
                for row in final_rows
            ),
            "nonselected_rows_changed": len(nonselected_changed),
            "assets_before": assets_before,
            "assets_after": _count(client, "assets"),
            "asset_sources_before": links_before,
            "asset_sources_after": _count(client, "asset_sources"),
        },
        "safety": {
            "selected_count_at_most_8": len(selected) <= 8,
            "sequential_processing": True,
            "drive_readonly": True,
            "assets_created": 0,
            "asset_sources_created": 0,
            "drive_objects_modified": 0,
            "destination_copies": 0,
        },
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(output),
                "pilot_selected": len(selected),
                "successfully_hashed": statuses[HashStatus.HASHED.value],
                "active_claims": report["reconciliation"][
                    "active_claims_remaining"
                ],
                "nonselected_rows_changed": len(nonselected_changed),
                "assets": report["reconciliation"]["assets_after"],
                "asset_sources": report["reconciliation"][
                    "asset_sources_after"
                ],
                "second_run_content_streams": report["second_run"][
                    "additional_drive_content_streams"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def _inventory_snapshot(row: dict[str, Any]) -> SourceSnapshot:
    metadata = row["metadata"] if isinstance(row.get("metadata"), dict) else {}
    return SourceSnapshot(
        file_id=row["google_file_id"],
        mime_type=(row["mime_type"] or "").strip().lower(),
        size_bytes=row["size_bytes"],
        modified_time=row["drive_modified_at"],
        version=_optional(metadata.get("drive_version") or metadata.get("version")),
        revision=_optional(metadata.get("head_revision_id")),
        trashed=row["trashed"],
        can_download=True,
        provider_md5=_optional(row.get("md5_checksum")),
    )


def _validate_selection(
    rows: list[dict[str, Any]], selected: tuple[str, ...]
) -> None:
    if len(rows) != len(selected) or {row["id"] for row in rows} != set(selected):
        raise RuntimeError("Every selected source_file must exist exactly once")
    for row in rows:
        if (
            row["source_folder_id"] not in PILOT_SOURCE_IDS
            or row["decision"] != "TAKE"
            or row["processing_status"] != "READY"
            or row["hash_status"]
            not in {
                HashStatus.NOT_STARTED.value,
                HashStatus.QUEUED.value,
                HashStatus.FAILED_RETRYABLE.value,
                HashStatus.HASHED.value,
            }
            or row["trashed"] is not False
            or row["is_missing"] is not False
            or not (row["google_file_id"] or "").strip()
        ):
            raise RuntimeError(f"Selected row {row['id']} is not pilot eligible")


def _read_selected(client: Any, selected: tuple[str, ...]) -> list[dict[str, Any]]:
    response = (
        client.table("source_files")
        .select(ROW_FIELDS)
        .in_("id", list(selected))
        .execute()
    )
    by_id = {row["id"]: row for row in response.data or []}
    return [by_id[source_file_id] for source_file_id in selected if source_file_id in by_id]


def _read_one(client: Any, source_file_id: str) -> dict[str, Any]:
    rows = (
        client.table("source_files")
        .select(ROW_FIELDS)
        .eq("id", source_file_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if len(rows) != 1:
        raise RuntimeError("Selected source_file could not be reconciled")
    return rows[0]


def _updated_at_map(client: Any) -> dict[str, str]:
    rows = (
        client.table("source_files")
        .select("id,updated_at")
        .range(0, 999)
        .execute()
        .data
        or []
    )
    return {row["id"]: row["updated_at"] for row in rows}


def _count(client: Any, table: str) -> int:
    response = client.table(table).select("id", count="exact").limit(0).execute()
    return int(response.count or 0)


def _safe_result(
    row: dict[str, Any],
    *,
    attempted: bool,
    worker_returned_success: bool | None,
) -> dict[str, Any]:
    expected = row["hash_expected_bytes"]
    observed = row["hash_observed_bytes"]
    return {
        "source_file_id": row["id"],
        "source_folder_id": row["source_folder_id"],
        "source_name": PILOT_SOURCE_IDS[row["source_folder_id"]],
        "file_name": row["file_name"],
        "mime_type": row["mime_type"],
        "extension": row["file_extension"],
        "final_hash_status": row["hash_status"],
        "hash_algorithm": row["hash_algorithm"],
        "sha256_present": row["content_sha256"] is not None,
        "sha256_prefix": (
            row["content_sha256"][:12] if row["content_sha256"] else None
        ),
        "expected_bytes": expected,
        "observed_bytes": observed,
        "byte_count_match": (
            expected == observed
            if expected is not None and observed is not None
            else None
        ),
        "attempt_count": row["hash_attempt_count"],
        "preflight_result": (
            "PASS" if row["hash_status"] == HashStatus.HASHED.value else "FAILED"
        ),
        "postflight_result": (
            "PASS" if row["hash_status"] == HashStatus.HASHED.value else "FAILED"
        ),
        "failure_code": row["hash_failure_code"],
        "failure_classification": (
            "RETRYABLE"
            if row["hash_retryable"] is True
            else "PERMANENT"
            if row["hash_retryable"] is False
            and row["hash_status"] != HashStatus.HASHED.value
            else None
        ),
        "active_claim_remaining": any(
            row[key] is not None
            for key in (
                "hash_claim_owner",
                "hash_claimed_at",
                "hash_claim_expires_at",
            )
        ),
        "attempted": attempted,
        "worker_returned_success": worker_returned_success,
    }


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    raise SystemExit(main())
