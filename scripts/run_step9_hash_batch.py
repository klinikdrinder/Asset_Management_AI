"""Run one explicitly bounded, sequential Step 9 hashing batch."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from kdi_media.google_drive import create_readonly_drive_service
from kdi_media.rules import FileRuleInput, evaluate_file
from kdi_media.source_folders import create_supabase_client_from_environment
from kdi_media.step9_hashing import (
    FailureInfo,
    HashStatus,
    Step9HashWorker,
    SupabaseHashRepository,
    iter_drive_content,
    read_drive_snapshot,
)
from run_step9_hash_pilot import (
    PILOT_SOURCE_IDS,
    ROW_FIELDS,
    _count,
    _inventory_snapshot,
    _read_one,
    _read_selected,
    _updated_at_map,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file-id", action="append", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--batch-number", type=int, required=True)
    parser.add_argument("--selection-scope-file")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    selected = tuple(dict.fromkeys(args.source_file_id))
    if not 1 <= len(selected) <= 25:
        raise SystemExit("A checkpoint requires between 1 and 25 unique rows")
    if not args.execute:
        raise SystemExit("--execute is required")
    if args.batch_number < 1:
        raise SystemExit("--batch-number must be positive")
    batch_label = f"{args.batch_number:03d}"
    claim_owner = f"step9-b5-batch-{batch_label}"
    protected_selection = selected
    if args.selection_scope_file:
        scope_value = json.loads(
            Path(args.selection_scope_file).read_text(encoding="utf-8")
        )
        protected_selection = tuple(scope_value["source_file_ids"])
        if not set(selected).issubset(protected_selection):
            raise SystemExit("Checkpoint IDs must be inside selection scope")
        if len(protected_selection) > 400:
            raise SystemExit("Selection scope cannot exceed 400 rows")

    client = create_supabase_client_from_environment()
    initial = _read_selected(client, selected)
    if len(initial) != len(selected):
        raise RuntimeError("Every selected checkpoint row must exist")
    for row in initial:
        _require_eligible(row)

    all_before = _updated_at_map(client)
    assets_before = _count(client, "assets")
    links_before = _count(client, "asset_sources")
    initial_hashes = {
        row["id"]: (row["content_sha256"], row["hash_attempt_count"])
        for row in initial
    }
    service = create_readonly_drive_service()
    repository = SupabaseHashRepository(client)
    events: list[dict[str, Any]] = []
    counters = {
        "bytes_streamed": 0,
        "content_streams": 0,
        "metadata_requests": 0,
        "retry_events": 0,
        "http_429_events": 0,
    }

    def observer(event: str, details: dict[str, Any]) -> None:
        if event == "retry":
            counters["retry_events"] += 1
            if details.get("failure_code") == "DRIVE_RATE_LIMITED":
                counters["http_429_events"] += 1

    def metadata_reader(drive_service: Any, file_id: str):
        counters["metadata_requests"] += 1
        return read_drive_snapshot(drive_service, file_id)

    def content_reader(drive_service: Any, file_id: str, *, chunk_size: int):
        counters["content_streams"] += 1
        for chunk in iter_drive_content(
            drive_service, file_id, chunk_size=chunk_size
        ):
            counters["bytes_streamed"] += len(chunk)
            yield chunk

    worker = Step9HashWorker(
        repository,
        service,
        metadata_reader,
        event_observer=observer,
    )
    output = Path(args.report)
    results: list[dict[str, Any]] = []
    stop_reason: str | None = None
    consecutive_mismatches = 0
    consecutive_retry_exhaustions = 0

    for row in initial:
        if stop_reason is not None:
            break
        current = _read_one(client, row["id"])
        try:
            _require_eligible(current)
        except RuntimeError:
            results.append(_outcome(current, "SKIPPED_NO_LONGER_ELIGIBLE"))
            _checkpoint(output, selected, results, counters, None)
            continue
        attempts_before = current["hash_attempt_count"]
        try:
            worker.process(
                current["id"],
                claim_owner,
                _inventory_snapshot(current),
                content_reader=content_reader,
            )
        except Exception:
            latest = _read_one(client, current["id"])
            if latest["hash_claim_owner"] == claim_owner:
                repository.fail(
                    current["id"],
                    claim_owner,
                    FailureInfo(
                        HashStatus.FAILED_RETRYABLE,
                        "BATCH_UNHANDLED_ERROR",
                        "Unexpected sanitized batch worker failure",
                        True,
                    ),
                )
            stop_reason = "DATABASE_OR_WORKER_BEHAVIOR_DIFFERED"
        final = _read_one(client, current["id"])
        outcome = _classify(final)
        results.append(_outcome(final, outcome))
        mismatch = final["hash_failure_code"] == "PARTIAL_DOWNLOAD"
        exhausted = (
            final["hash_status"] == HashStatus.FAILED_RETRYABLE.value
            and final["hash_attempt_count"] - attempts_before >= 6
        )
        consecutive_mismatches = consecutive_mismatches + 1 if mismatch else 0
        consecutive_retry_exhaustions = (
            consecutive_retry_exhaustions + 1 if exhausted else 0
        )
        attempted = sum(x["attempted"] for x in results)
        severe = sum(
            x["outcome"] in {"SOURCE_CHANGED", "PERMANENT_FAILURE"}
            for x in results
        )
        if _has_claim(final):
            stop_reason = "ACTIVE_CLAIM_NOT_RELEASED"
        elif _count(client, "assets") != assets_before or _count(
            client, "asset_sources"
        ) != links_before:
            stop_reason = "CANONICALIZATION_TABLE_CHANGED"
        elif _nonselected_changed(client, all_before, protected_selection):
            stop_reason = "NONSELECTED_ROW_CHANGED"
        elif consecutive_mismatches >= 2:
            stop_reason = "TWO_CONSECUTIVE_BYTE_MISMATCHES"
        elif consecutive_retry_exhaustions >= 3:
            stop_reason = "THREE_CONSECUTIVE_RETRY_EXHAUSTIONS"
        elif attempted and severe / attempted >= 0.05:
            stop_reason = "SOURCE_CHANGE_OR_PERMANENT_FAILURE_RATE_5_PERCENT"
        elif (
            final["hash_status"] == HashStatus.FAILED_RETRYABLE.value
            and final["hash_failure_code"] == "DRIVE_RATE_LIMITED"
        ):
            stop_reason = "PERSISTENT_HTTP_429"
        _checkpoint(output, selected, results, counters, stop_reason)

    final_rows = _read_selected(client, selected)
    dry_rerun = []
    for row in final_rows:
        old_hash, _old_attempt = initial_hashes[row["id"]]
        dry_rerun.append(
            {
                "source_file_id": row["id"],
                "would_skip_completed": row["hash_status"]
                == HashStatus.HASHED.value,
                "would_download": row["hash_status"]
                != HashStatus.HASHED.value,
                "attempt_count_unchanged_by_dry_run": True,
                "sha256_changed_by_dry_run": False,
                "active_claim": _has_claim(row),
                "had_hash_before_batch": old_hash is not None,
            }
        )
    nonselected_changed = _nonselected_changed(
        client, all_before, protected_selection
    )
    global_rows = (
        client.table("source_files")
        .select(
            "id,source_folder_id,google_file_id,file_name,mime_type,"
            "file_extension,size_bytes,decision,processing_status,trashed,"
            "is_missing,hash_status"
        )
        .in_("source_folder_id", list(PILOT_SOURCE_IDS))
        .range(0, 999)
        .execute()
        .data
        or []
    )
    remaining = sum(_is_remaining_eligible(row) for row in global_rows)
    counts = Counter(x["outcome"] for x in results)
    report = {
            "phase": f"STEP_9_PHASE_B5_BATCH_{batch_label}",
            "batch_number": args.batch_number,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_order": "source_folder_id ASC, source_file UUID ASC",
        "selected_source_file_ids": list(selected),
        "selected": len(selected),
        "attempted": sum(x["attempted"] for x in results),
        "processed_results": results,
        "outcomes": {
            "successfully_hashed": counts["HASHED"],
            "source_changed": counts["SOURCE_CHANGED"],
            "retryable_failures": counts["RETRYABLE_FAILURE"],
            "permanent_failures": counts["PERMANENT_FAILURE"],
            "byte_count_mismatches": sum(
                x["failure_code"] == "PARTIAL_DOWNLOAD" for x in results
            ),
            "skipped_no_longer_eligible": counts[
                "SKIPPED_NO_LONGER_ELIGIBLE"
            ],
            "other_explicit_final_outcomes": (
                len(selected) - len(results)
                + counts["OTHER_FINAL_OUTCOME"]
            ),
        },
        "telemetry": counters,
        "stop_condition": {
            "triggered": stop_reason is not None,
            "reason": stop_reason,
        },
        "idempotency_readonly_rerun": {
            "results": dry_rerun,
            "completed_rows_would_skip": sum(
                x["would_skip_completed"] for x in dry_rerun
            ),
            "content_downloads": 0,
            "database_writes": 0,
        },
        "reconciliation": {
            "active_claims_remaining": sum(_has_claim(x) for x in final_rows),
            "selected_without_final_outcome": len(selected) - len(results),
            "nonselected_rows_changed": len(nonselected_changed),
            "global_hashed": sum(
                row["hash_status"] == HashStatus.HASHED.value
                for row in global_rows
            ),
            "remaining_eligible_not_started": remaining,
            "assets": _count(client, "assets"),
            "asset_sources": _count(client, "asset_sources"),
        },
        "safety": {
            "batch_limit_respected": len(selected) == 25,
            "concurrency": 1,
            "drive_readonly": True,
            "phase_c_started": False,
        },
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "selected": len(selected),
                "attempted": report["attempted"],
                "hashed": counts["HASHED"],
                "stop_reason": stop_reason,
                "bytes_streamed": counters["bytes_streamed"],
                "active_claims": report["reconciliation"][
                    "active_claims_remaining"
                ],
                "nonselected_changed": len(nonselected_changed),
                "global_hashed": report["reconciliation"]["global_hashed"],
                "remaining": remaining,
                "report": str(output),
            },
            sort_keys=True,
        )
    )
    return 0


def _require_eligible(row: dict[str, Any]) -> None:
    result = evaluate_file(
        FileRuleInput(
            row["file_name"],
            row["mime_type"],
            row["file_extension"],
            row["size_bytes"],
            "",
            "accessible",
            row["trashed"],
            row["is_missing"],
            False,
        )
    )
    if not (
        row["source_folder_id"] in PILOT_SOURCE_IDS
        and row["decision"] == "TAKE"
        and row["processing_status"] == "READY"
        and row["hash_status"] == HashStatus.NOT_STARTED.value
        and row["content_sha256"] is None
        and not row["trashed"]
        and not row["is_missing"]
        and (row["google_file_id"] or "").strip()
        and result.automatic_decision == "TAKE"
        and result.accepted_for_migration
        and result.accepted_for_duplicate_detection
        and not _has_claim(row)
    ):
        raise RuntimeError("Row is no longer eligible")


def _is_remaining_eligible(row: dict[str, Any]) -> bool:
    result = evaluate_file(
        FileRuleInput(
            row["file_name"],
            row["mime_type"],
            row["file_extension"],
            row["size_bytes"],
            "",
            "accessible",
            row["trashed"],
            row["is_missing"],
            False,
        )
    )
    return (
        row["decision"] == "TAKE"
        and row["processing_status"] == "READY"
        and row["hash_status"] == HashStatus.NOT_STARTED.value
        and not row["trashed"]
        and not row["is_missing"]
        and bool((row["google_file_id"] or "").strip())
        and result.automatic_decision == "TAKE"
        and result.accepted_for_migration
        and result.accepted_for_duplicate_detection
    )


def _classify(row: dict[str, Any]) -> str:
    if row["hash_status"] == HashStatus.HASHED.value:
        return "HASHED"
    if row["hash_status"] == HashStatus.SOURCE_CHANGED.value:
        return "SOURCE_CHANGED"
    if row["hash_status"] == HashStatus.FAILED_RETRYABLE.value:
        return "RETRYABLE_FAILURE"
    if row["hash_status"] in {
        HashStatus.FAILED_PERMANENT.value,
        HashStatus.SOURCE_NOT_FOUND.value,
        HashStatus.SOURCE_ACCESS_DENIED.value,
        HashStatus.SOURCE_TRASHED.value,
    }:
        return "PERMANENT_FAILURE"
    return "OTHER_FINAL_OUTCOME"


def _outcome(row: dict[str, Any], outcome: str) -> dict[str, Any]:
    return {
        "source_file_id": row["id"],
        "outcome": outcome,
        "attempted": row["hash_attempt_count"] > 0,
        "hash_status": row["hash_status"],
        "sha256_present": row["content_sha256"] is not None,
        "sha256_prefix": (
            row["content_sha256"][:12] if row["content_sha256"] else None
        ),
        "expected_bytes": row["hash_expected_bytes"],
        "observed_bytes": row["hash_observed_bytes"],
        "byte_count_match": (
            row["hash_expected_bytes"] == row["hash_observed_bytes"]
            if row["hash_expected_bytes"] is not None
            and row["hash_observed_bytes"] is not None
            else None
        ),
        "attempt_count": row["hash_attempt_count"],
        "failure_code": row["hash_failure_code"],
        "retryable": row["hash_retryable"],
        "active_claim": _has_claim(row),
    }


def _has_claim(row: dict[str, Any]) -> bool:
    return any(
        row.get(key) is not None
        for key in (
            "hash_claim_owner",
            "hash_claimed_at",
            "hash_claim_expires_at",
        )
    )


def _nonselected_changed(
    client: Any, before: dict[str, str], selected: tuple[str, ...]
) -> list[str]:
    after = _updated_at_map(client)
    return [
        row_id
        for row_id, updated_at in before.items()
        if row_id not in selected and after.get(row_id) != updated_at
    ]


def _checkpoint(
    output: Path,
    selected: tuple[str, ...],
    results: list[dict[str, Any]],
    counters: dict[str, int],
    stop_reason: str | None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "phase": "STEP_9_PHASE_B5_BATCH_CHECKPOINT",
                "selected": len(selected),
                "completed_results": results,
                "telemetry": counters,
                "stop_reason": stop_reason,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
