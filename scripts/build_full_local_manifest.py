"""Extends the frozen #31-#130 manifest to the whole 881-asset library.

The candidate ranking is the one `freeze_and_triage_privacy_rollout.py` already froze, replayed
over every asset rather than truncated at 100. Ordinals #31-#130 are asserted to be byte-identical
to the frozen manifest before anything is written, so the completed local work stays valid and
assets #1-#30 stay untouched. Nothing here writes to the database.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
LOCKED = ROOT / "reports/semantic-search/30-asset-rollout/phase01/kdi_30_asset_rollout_v1.json"
FROZEN_100 = ROOT / "reports/semantic-search/rollout/100/privacy-approval-required.json"
OUT = ROOT / "reports/semantic-search/rollout/full"
MANIFEST = OUT / "kdi_local_preparation_manifest_v1.json"
SUPPORTED = {"jpg", "jpeg", "png", "webp", "mp4", "mov", "pdf"}


def page(db, table, columns, size=1000):
    out, start = [], 0
    while True:
        chunk = db.table(table).select(columns).range(start, start + size - 1).execute().data or []
        out.extend(chunk)
        if len(chunk) < size:
            return out
        start += size


def media_type(asset):
    mime = str(asset.get("mime_type") or "")
    if mime.startswith("video/"):
        return "VIDEO"
    if mime.startswith("image/"):
        return "IMAGE"
    if "pdf" in mime:
        return "DOCUMENT"
    return "OTHER"


def main() -> None:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=False)
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    locked = json.loads(LOCKED.read_text(encoding="utf-8"))
    locked_assets = locked["pilot_assets"] + locked["new_assets"]
    locked_ids = {str(x["asset_id"]) for x in locked_assets}
    locked_hashes = {str(x["content_hash"]) for x in locked_assets}

    assets = page(db, "assets", "id,file_name,file_extension,mime_type,size_bytes,content_hash,checksum_sha256,upload_status,migration_status")
    sources = page(db, "asset_sources", "asset_id,source_file_id,source_files(id,file_name,file_extension,size_bytes,relative_path,processing_status,decision,hash_status,content_sha256,google_file_id,source_folders(source_name))")
    by_asset = {str(x["asset_id"]): (x.get("source_files") or {}) for x in sources}
    # The verified KDI-owned copy is the reliable acquisition reference: the original source files
    # are not all reachable by the reader service account.
    destinations = {str(x["asset_id"]): x.get("destination_google_file_id")
                    for x in page(db, "asset_destinations", "asset_id,destination_google_file_id,upload_status")
                    if x.get("upload_status") == "VERIFIED"}

    candidates, excluded = [], []
    for asset in assets:
        aid = str(asset["id"])
        source = by_asset.get(aid, {})
        ext = str(asset.get("file_extension") or Path(str(asset.get("file_name") or "")).suffix).lower().lstrip(".")
        content_hash = str(asset.get("content_hash") or asset.get("checksum_sha256") or source.get("content_sha256") or "")
        status = str(asset.get("upload_status") or asset.get("migration_status") or "").upper()
        processing = str(source.get("processing_status") or "").upper()
        decision = str(source.get("decision") or "").upper()
        reasons = []
        if aid in locked_ids or content_hash in locked_hashes:
            reasons.append("CERTIFIED_OR_DUPLICATE")
        if ext not in SUPPORTED:
            reasons.append("UNSUPPORTED_FORMAT")
        if not content_hash:
            reasons.append("MISSING_HASH")
        if not source.get("id") or not source.get("google_file_id"):
            reasons.append("UNRESOLVABLE_SOURCE")
        if any(x in status or x in processing for x in ("FAILED", "CORRUPT", "BLOCKED", "FORBIDDEN")):
            reasons.append("BLOCKED_STATUS")
        if decision in {"SKIP", "REJECT"}:
            reasons.append("SOURCE_EXCLUDED")
        item = {"asset_id": aid, "filename": str(asset.get("file_name") or ""), "media_type": media_type(asset),
                "mime_type": asset.get("mime_type"), "size": asset.get("size_bytes") or source.get("size_bytes"),
                "checksum": content_hash, "source_id": source.get("id"),
                "source_master_reference": source.get("google_file_id"),
                "destination_reference": destinations.get(aid),
                "source_folder": (source.get("source_folders") or {}).get("source_name"),
                "source_path": source.get("relative_path"), "source_status": processing or status or "UNKNOWN"}
        if reasons:
            excluded.append({**item, "excluded_reasons": reasons,
                             "certified": aid in locked_ids or content_hash in locked_hashes})
            continue
        candidates.append(item)

    candidates.sort(key=lambda x: (0 if x["media_type"] == "VIDEO" else 1 if x["media_type"] == "IMAGE" else 2,
                                   str(x.get("source_folder") or "").casefold(), int(x.get("size") or 0),
                                   x["filename"].casefold(), x["asset_id"]))
    for ordinal, item in enumerate(candidates, 31):
        item["ordinal"] = ordinal

    frozen = json.loads(FROZEN_100.read_text(encoding="utf-8"))["assets"]
    head = candidates[:100]
    if [x["asset_id"] for x in head] != [x["asset_id"] for x in frozen]:
        raise RuntimeError("FROZEN_MANIFEST_DRIFT: ordinals #31-#130 no longer reproduce")
    if [x["ordinal"] for x in head] != list(range(31, 131)):
        raise RuntimeError("FROZEN_MANIFEST_ORDINAL_DRIFT")

    by_type: dict[str, int] = {}
    for item in candidates[100:]:
        by_type[item["media_type"]] = by_type.get(item["media_type"], 0) + 1
    reasons: dict[str, int] = {}
    for item in excluded:
        for reason in item["excluded_reasons"]:
            reasons[reason] = reasons.get(reason, 0) + 1

    payload = {
        "manifest_id": "kdi_local_preparation_881_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "library_total": len(assets),
        "certified_locked": len({x["asset_id"] for x in excluded if x["certified"]}),
        "frozen_31_130": 100,
        "new_scope_131_plus": len(candidates) - 100,
        "new_scope_range": f"#131-#{candidates[-1]['ordinal']}" if len(candidates) > 100 else "none",
        "new_scope_by_media_type": by_type,
        "excluded": len(excluded),
        "exclusion_reasons": reasons,
        "assets": candidates,
        "excluded_assets": excluded,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k not in {"assets", "excluded_assets"}}, default=str))


if __name__ == "__main__":
    main()
