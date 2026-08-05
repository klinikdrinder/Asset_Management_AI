"""Controlled live verification of Step 14 overlap and stale-lock recovery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4

from dotenv import load_dotenv
from supabase import create_client


def main() -> int:
    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    run_a, run_b, run_c, run_d = (str(uuid4()) for _ in range(4))
    for run_id in (run_a, run_b, run_c, run_d):
        client.table("sync_runs").insert({
            "id": run_id, "sync_type": "DAILY_SYNC", "run_type": "DAILY_SYNC",
            "status": "RUNNING", "started_at": _now(),
            "metadata": {"run_type": "incremental_sync", "controlled_lock_test": True},
        }).execute()
    first = _acquire(client, run_a)
    overlap_rejected = not _acquire(client, run_b)
    first_released = _release(client, run_a)
    second_after_release = _acquire(client, run_b)
    second_released = _release(client, run_b)
    stale_first = _acquire(client, run_c)
    now = datetime.now(timezone.utc)
    client.table("synchronization_locks").update({
        "acquired_at": (now - timedelta(minutes=2)).isoformat(),
        "expires_at": (now - timedelta(minutes=1)).isoformat(),
    }).eq("lock_name", "daily_incremental_sync").eq("owner_run_id", run_c).execute()
    stale_recovered = _acquire(client, run_d)
    recovered_released = _release(client, run_d)
    for run_id in (run_a, run_b, run_c, run_d):
        client.table("sync_runs").update({"status": "CANCELLED", "completed_at": _now()}).eq("id", run_id).execute()
    remaining = client.table("synchronization_locks").select("*", count="exact").limit(0).execute().count
    result = {
        "first_acquired": first,
        "overlap_rejected": overlap_rejected,
        "first_released": first_released,
        "second_acquired_after_release": second_after_release,
        "second_released": second_released,
        "stale_lock_created": stale_first,
        "stale_lock_recovered": stale_recovered,
        "recovered_lock_released": recovered_released,
        "remaining_locks": remaining,
        "run_ids": [run_a, run_b, run_c, run_d],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(value is True for key, value in result.items() if key not in {"remaining_locks", "run_ids"}) and remaining == 0 else 1


def _acquire(client, run_id: str) -> bool:
    return bool(client.rpc("acquire_synchronization_lock", {
        "requested_lock_name": "daily_incremental_sync",
        "requested_run_id": run_id,
        "requested_lease_seconds": 60,
    }).execute().data)


def _release(client, run_id: str) -> bool:
    return bool(client.rpc("release_synchronization_lock", {
        "requested_lock_name": "daily_incremental_sync",
        "requested_run_id": run_id,
    }).execute().data)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
