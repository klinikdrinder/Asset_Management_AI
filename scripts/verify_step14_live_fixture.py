"""Read-only reconciliation of the controlled Step 14 live fixture."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    load_dotenv(ROOT / ".env")
    fixture = json.loads((ROOT / "tmp" / "step14-live-fixture.json").read_text(encoding="utf-8"))
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    files = client.table("source_files").select("id,google_file_id,file_name,decision,processing_status,skip_reason,hash_status,content_sha256,sync_classification,sync_processing_status,sync_attempt_count,sync_retry_eligible").eq("source_folder_id", fixture["source_folder_id"]).order("google_file_id").execute().data or []
    ids = [row["id"] for row in files]
    links = client.table("asset_sources").select("id,asset_id,source_file_id,relationship_type").in_("source_file_id", ids).execute().data if ids else []
    asset_ids = sorted({row["asset_id"] for row in links or []})
    assets = client.table("assets").select("id,content_hash,file_name,size_bytes").in_("id", asset_ids).execute().data if asset_ids else []
    destinations = client.table("asset_destinations").select("id,asset_id,selected_source_file_id,destination_google_file_id,upload_status,verification_level,upload_attempt_count,idempotency_key").in_("asset_id", asset_ids).execute().data if asset_ids else []
    events = client.table("migration_events").select("id,sync_run_id,source_file_id,asset_id,asset_destination_id,event_type,event_status,message,details").in_("source_file_id", ids).order("occurred_at").execute().data if ids else []
    counts = {}
    for table in ("source_folders", "source_files", "assets", "asset_sources", "asset_destinations"):
        counts[table] = client.table(table).select("*", count="exact").limit(0).execute().count
    print(json.dumps({"fixture": fixture, "source_files": files, "relationships": links or [], "assets": assets or [], "destinations": destinations or [], "events": events or [], "production_counts": counts}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
