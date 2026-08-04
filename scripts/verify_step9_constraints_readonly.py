"""Read-only deployed-column check for Step 9 canonicalization prerequisites.

PostgREST does not expose indexes or constraints. This command therefore
confirms column availability only and reports the repository-defined
constraints that still require an approved schema-introspection mechanism.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

from kdi_media.source_folders import create_supabase_client_from_environment


PILOT_SOURCE_IDS = (
    "42affe18-4e7b-4333-87fe-7158c410c072",
    "84a6b92b-e075-4f4b-9384-9b6a99acb51e",
    "24bec9f0-7325-4706-896b-6d594daeaef2",
)
NONEXISTENT_SOURCE_FILE_ID = "00000000-0000-0000-0000-000000000000"
HASH_COLUMNS = (
    "hash_algorithm,content_sha256,hash_status,hash_expected_bytes,"
    "hash_observed_bytes,hash_attempt_count,hash_last_attempt_at,"
    "hash_completed_at,hash_failure_code,hash_failure_reason,"
    "hash_retryable,hash_source_snapshot,hash_drive_modified_at,"
    "hash_drive_size,hash_drive_mime_type,hash_drive_version,"
    "hash_claim_owner,hash_claimed_at,hash_claim_expires_at"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute-readonly",
        action="store_true",
        help="Perform zero-row Supabase REST SELECT probes.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = {
        "mode": "READ_ONLY",
        "repository_constraints": {
            "assets": (
                "partial UNIQUE(content_hash) WHERE content_hash IS NOT NULL"
            ),
            "asset_sources": "UNIQUE(source_file_id)",
        },
        "deployed_columns": "NOT_CHECKED",
        "deployed_constraints": "NOT_VERIFIABLE_THROUGH_POSTGREST",
        "deployed_indexes": "NOT_VERIFIABLE_THROUGH_POSTGREST",
        "claim_rpc": "NOT_CHECKED",
        "renew_rpc": "NOT_CHECKED",
        "inventory": "NOT_CHECKED",
        "writes": 0,
    }
    if args.execute_readonly:
        client = create_supabase_client_from_environment()
        client.table("assets").select("id,content_hash").limit(0).execute()
        client.table("asset_sources").select(
            "id,asset_id,source_file_id"
        ).limit(0).execute()
        fields = (
            "id,source_folder_id,google_file_id,decision,processing_status,"
            "trashed,is_missing,"
            + HASH_COLUMNS
        )
        rows = (
            client.table("source_files")
            .select(fields)
            .in_("source_folder_id", list(PILOT_SOURCE_IDS))
            .range(0, 999)
            .execute()
            .data
            or []
        )
        counts = Counter(row["source_folder_id"] for row in rows)
        identities = Counter(
            (row["source_folder_id"], row["google_file_id"]) for row in rows
        )
        assets = (
            client.table("assets").select("id", count="exact").limit(0).execute()
        )
        asset_sources = (
            client.table("asset_sources")
            .select("id", count="exact")
            .limit(0)
            .execute()
        )
        # These calls prove that both deployed RPC signatures are visible.
        # The all-zero UUID cannot match an existing generated source-file ID,
        # so neither call can claim or mutate a production row.
        claim = client.rpc(
            "claim_source_file_hash",
            {
                "requested_source_file_id": NONEXISTENT_SOURCE_FILE_ID,
                "requested_claim_owner": "step9-readonly-verification",
                "requested_lease_seconds": 30,
            },
        ).execute()
        renewal = client.rpc(
            "renew_source_file_hash_claim",
            {
                "requested_source_file_id": NONEXISTENT_SOURCE_FILE_ID,
                "requested_claim_owner": "step9-readonly-verification",
                "requested_lease_seconds": 30,
            },
        ).execute()
        result["deployed_columns"] = "CONFIRMED"
        result["claim_rpc"] = (
            "CONFIRMED_NO_ROW_MATCH" if not (claim.data or []) else "UNEXPECTED"
        )
        result["renew_rpc"] = (
            "CONFIRMED_NO_ROW_MATCH" if renewal.data is False else "UNEXPECTED"
        )
        result["inventory"] = {
            "source_files": len(rows),
            "per_source": {
                source_id: counts[source_id]
                for source_id in PILOT_SOURCE_IDS
            },
            "take_ready": sum(
                row["decision"] == "TAKE"
                and row["processing_status"] == "READY"
                for row in rows
            ),
            "skip_skipped": sum(
                row["decision"] == "SKIP"
                and row["processing_status"] == "SKIPPED"
                for row in rows
            ),
            "eligible": sum(
                row["decision"] == "TAKE"
                and row["processing_status"] == "READY"
                and row["trashed"] is False
                and row["is_missing"] is False
                and bool((row["google_file_id"] or "").strip())
                for row in rows
            ),
            "duplicate_source_identities": sum(
                count - 1 for count in identities.values() if count > 1
            ),
            "assets": assets.count,
            "asset_sources": asset_sources.count,
            "hash_status": dict(
                Counter(row["hash_status"] for row in rows)
            ),
            "sha256_populated": sum(
                row["content_sha256"] is not None for row in rows
            ),
            "active_claims": sum(
                row["hash_claim_owner"] is not None
                or row["hash_claimed_at"] is not None
                or row["hash_claim_expires_at"] is not None
                for row in rows
            ),
            "non_default_attempt_counts": sum(
                row["hash_attempt_count"] != 0 for row in rows
            ),
        }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
