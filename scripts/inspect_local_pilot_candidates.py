"""Read-only inventory summary for selecting a bounded local vision pilot."""
from __future__ import annotations

import json
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
client=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SERVICE_ROLE_KEY"])
indexed=client.table("asset_semantic_index").select("asset_id").execute().data or []
all_assets=client.table("assets").select("id,file_name,mime_type,file_extension,size_bytes,content_hash").execute().data or []
destinations=client.table("asset_destinations").select("asset_id,destination_google_file_id,upload_status").eq("upload_status","VERIFIED").execute().data or []
sources=client.table("asset_sources").select("asset_id,source_files(relative_path,is_missing,sync_classification,source_folders(source_name,active))").execute().data or []
indexed_ids={row["asset_id"] for row in indexed}
destination_ids={row["asset_id"] for row in destinations if row.get("destination_google_file_id")}
source_by_asset={row["asset_id"]:row.get("source_files") or {} for row in sources}
extensions={"jpg":"image","jpeg":"image","png":"image","webp":"image","mp4":"video","mov":"video","m4v":"video"}
rows=[]
seen_hashes=set()
for raw in all_assets:
    extension=str(raw.get("file_extension") or "").lower().lstrip(".")
    if raw["id"] in indexed_ids or raw["id"] not in destination_ids or extension not in extensions: continue
    content_hash=raw.get("content_hash")
    if content_hash and content_hash in seen_hashes: continue
    if content_hash: seen_hashes.add(content_hash)
    source_file=source_by_asset.get(raw["id"],{})
    folder=source_file.get("source_folders") or {}
    rows.append({"asset_id":raw["id"],"filename":raw["file_name"],"media_type":extensions[extension],"size_bytes":raw.get("size_bytes"),"source_name":folder.get("source_name"),"source_path":source_file.get("relative_path")})
print(json.dumps({"total_assets":len(all_assets),"indexed":len(indexed),"unindexed_eligible":len(rows),"eligible_images":sum(r["media_type"]=="image" for r in rows),"eligible_videos":sum(r["media_type"]=="video" for r in rows),"images":[r for r in rows if r["media_type"]=="image"][:40],"videos":[r for r in rows if r["media_type"]=="video"][:40]},indent=2))
