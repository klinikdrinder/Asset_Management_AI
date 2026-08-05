"""Read-only production verification for the Step 14 deployment."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from supabase import create_client


EXPECTED_COUNTS = {
    "source_folders": 3,
    "source_files": 886,
    "assets": 878,
    "asset_sources": 878,
    "asset_destinations": 878,
}


def main() -> int:
    load_dotenv()
    client = create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    )
    actual = {
        table: client.table(table).select("*", count="exact").limit(0).execute().count
        for table in EXPECTED_COUNTS
    }
    for table, count in actual.items():
        print(f"{table}={count}")

    client.table("source_files").select(
        "sync_classification,sync_processing_status,sync_attempt_count,"
        "sync_retry_eligible,sync_last_failure_reason,sync_last_success_at"
    ).limit(1).execute()
    locks = (
        client.table("synchronization_locks")
        .select("lock_name", count="exact")
        .limit(0)
        .execute()
    )
    print("step14_columns=present")
    print(f"synchronization_locks=present,count={locks.count}")
    if actual != EXPECTED_COUNTS:
        print(f"count_reconciliation=FAILED expected={EXPECTED_COUNTS!r}")
        return 1
    print("count_reconciliation=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
