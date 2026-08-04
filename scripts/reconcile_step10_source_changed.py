"""Rehash and recover exactly one unchanged Step 10 SOURCE_CHANGED source."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv
from supabase import create_client

from kdi_media.google_drive import create_readonly_drive_service
from kdi_media.step9_hashing import (
    SupabaseHashRepository,
    hash_drive_file,
    read_drive_snapshot,
)
from kdi_media.step10_upload import SupabaseStep10Repository


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--execute", action="store_true")
    result.add_argument("--lifecycle-id", required=True)
    result.add_argument("--source-file-id", required=True)
    result.add_argument("--expected-non-pilot-digest", required=True)
    result.add_argument("--report", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.execute:
        raise SystemExit("--execute is required")
    load_dotenv(".env")
    client = create_client(
        _required("SUPABASE_URL"), _required("SUPABASE_SERVICE_ROLE_KEY")
    )
    lifecycle = (
        client.table("asset_destinations")
        .select(
            "id,asset_id,selected_source_file_id,upload_status,"
            "upload_attempt_count,destination_google_file_id,claim_owner,"
            "claim_expires_at,next_retry_at"
        )
        .eq("id", args.lifecycle_id)
        .single()
        .execute()
        .data
    )
    if (
        lifecycle["selected_source_file_id"] != args.source_file_id
        or lifecycle["upload_status"] != "SOURCE_CHANGED"
        or int(lifecycle["upload_attempt_count"]) != 2
        or lifecycle["destination_google_file_id"]
        or lifecycle["claim_owner"]
        or lifecycle["claim_expires_at"]
        or lifecycle["next_retry_at"]
    ):
        raise RuntimeError("Target lifecycle is not the exact recoverable row")
    rows_before = _destinations(client)
    outside_before = {
        row["id"]: row for row in rows_before if row["id"] != args.lifecycle_id
    }
    non_pilot_before = [
        row for row in rows_before if row["upload_attempt_count"] == 0
    ]
    if _digest(non_pilot_before) != args.expected_non_pilot_digest:
        raise RuntimeError("Non-pilot digest differs before recovery")

    source = (
        client.table("source_files")
        .select(
            "id,google_file_id,content_sha256,hash_status,hash_algorithm,"
            "hash_claim_owner"
        )
        .eq("id", args.source_file_id)
        .single()
        .execute()
        .data
    )
    if (
        source["hash_status"] != "HASHED"
        or source["hash_algorithm"] != "SHA-256"
        or source["hash_claim_owner"]
    ):
        raise RuntimeError("Target source is not safely rehashable")
    service = create_readonly_drive_service()
    current = read_drive_snapshot(service, source["google_file_id"])
    result = hash_drive_file(service, current, read_drive_snapshot)
    if result.content_sha256 != source["content_sha256"]:
        raise RuntimeError("Source bytes changed; canonical review is required")

    hashes = SupabaseHashRepository(client)
    if not hashes.refresh_unchanged_snapshot(
        args.source_file_id, source["content_sha256"], result
    ):
        raise RuntimeError("Source snapshot refresh did not affect one row")
    destinations = SupabaseStep10Repository(client)
    if not destinations.recover_unchanged_source(
        args.lifecycle_id, args.source_file_id
    ):
        raise RuntimeError("Lifecycle recovery did not affect one row")
    destinations.append_event(
        {
            "asset_id": lifecycle["asset_id"],
            "asset_destination_id": args.lifecycle_id,
            "event_type": "UPLOAD_QUEUED",
            "event_status": "INFO",
            "message": "Step 10 source snapshot revalidated and queued",
            "details": {
                "recovery": "timestamp_format_false_positive",
                "sha256_relationship": "MATCH",
                "attempt_count_preserved": 2,
            },
        }
    )

    rows_after = _destinations(client)
    non_pilot_after = [
        row for row in rows_after if row["upload_attempt_count"] == 0
    ]
    target_after = next(
        row for row in rows_after if row["id"] == args.lifecycle_id
    )
    outside_after = {
        row["id"]: row for row in rows_after if row["id"] != args.lifecycle_id
    }
    if not (
        _digest(non_pilot_after) == args.expected_non_pilot_digest
        and outside_before == outside_after
        and target_after["upload_status"] == "QUEUED"
        and int(target_after["upload_attempt_count"]) == 2
    ):
        raise RuntimeError("Scoped post-recovery reconciliation failed")
    report = {
        "lifecycle_id": args.lifecycle_id,
        "source_file_id": args.source_file_id,
        "cause": "timestamp_format_false_positive",
        "rehash_relationship": "MATCH",
        "byte_count_match": result.observed_bytes == result.expected_bytes,
        "observed_bytes": result.observed_bytes,
        "attempt_count_preserved": 2,
        "non_pilot_digest": args.expected_non_pilot_digest,
        "non_pilot_rows_changed": 0,
        "manifest_change_required": False,
        "verdict": "RECONCILED",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    return 0


def _destinations(client: Any) -> list[dict[str, Any]]:
    return list(
        client.table("asset_destinations")
        .select(
            "id,upload_status,verification_level,upload_attempt_count,"
            "destination_google_file_id,claim_owner,next_retry_at"
        )
        .range(0, 999)
        .execute()
        .data
        or []
    )


def _digest(rows: list[Mapping[str, Any]]) -> str:
    safe = sorted(
        (
            str(row["id"]),
            str(row["upload_status"]),
            str(row["verification_level"]),
            bool(row["destination_google_file_id"]),
            bool(row["claim_owner"]),
            bool(row["next_retry_at"]),
        )
        for row in rows
    )
    return hashlib.sha256(
        json.dumps(safe, sort_keys=True).encode()
    ).hexdigest()[:16]


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
