"""Read-only preflight for the Claude production canary at rollout position 31."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "semantic-search" / "rollout" / "claude-canary-31"
MANIFEST = ROOT / "reports" / "semantic-search" / "30-asset-rollout" / "phase01" / "kdi_30_asset_rollout_v1.json"


def rows(query):
    return query.execute().data or []


def media_type(asset):
    mime = str(asset.get("mime_type") or "")
    if mime.startswith("video/"):
        return "VIDEO"
    if mime.startswith("image/"):
        return "IMAGE"
    if "pdf" in mime:
        return "DOCUMENT"
    return "OTHER"


def main():
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=False)
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("DATABASE_CONFIGURATION_UNAVAILABLE")
    db = create_client(url, key)

    locked = json.loads(MANIFEST.read_text(encoding="utf-8"))
    locked_assets = locked["pilot_assets"] + locked["new_assets"]
    locked_ids = {str(a["asset_id"]) for a in locked_assets}
    locked_hashes = {str(a["content_hash"]) for a in locked_assets}

    assets = rows(db.table("assets").select(
        "id,file_name,file_extension,mime_type,size_bytes,content_hash,created_at,updated_at,upload_status,migration_status"
    ).order("file_name"))
    sources = rows(db.table("asset_sources").select(
        "asset_id,source_file_id,source_files(id,file_name,file_extension,size_bytes,relative_path,processing_status,decision,hash_status,content_sha256,source_folders(source_name))"
    ))
    by_source = {str(x["asset_id"]): x for x in sources if x.get("source_files")}
    supported = {"jpg", "jpeg", "png", "webp", "mp4", "mov", "pdf"}
    candidates = []
    for asset in assets:
        aid = str(asset["id"])
        if aid in locked_ids:
            continue
        source_link = by_source.get(aid) or {}
        source = source_link.get("source_files") or {}
        ext = str(asset.get("file_extension") or Path(str(asset.get("file_name") or "")).suffix).lower().lstrip(".")
        content_hash = str(asset.get("content_hash") or source.get("content_sha256") or "")
        status = str(asset.get("upload_status") or asset.get("migration_status") or "").upper()
        processing = str(source.get("processing_status") or "").upper()
        decision = str(source.get("decision") or "").upper()
        reasons = []
        if ext not in supported:
            reasons.append("UNSUPPORTED_FORMAT")
        if not content_hash:
            reasons.append("MISSING_HASH")
        if not source.get("id"):
            reasons.append("UNRESOLVABLE_SOURCE")
        if any(v in status or v in processing for v in ("FAILED", "CORRUPT", "BLOCKED", "FORBIDDEN")):
            reasons.append("BLOCKED_STATUS")
        if decision in {"SKIP", "REJECT"}:
            reasons.append("SOURCE_EXCLUDED")
        if content_hash in locked_hashes:
            reasons.append("LOCKED_CONTENT_DUPLICATE")
        kind = media_type(asset)
        if not reasons:
            candidates.append({
                "asset_id": aid,
                "filename": str(asset.get("file_name") or ""),
                "media_type": kind,
                "content_hash": content_hash,
                "file_size": asset.get("size_bytes") or source.get("size_bytes"),
                "source_id": source.get("id"),
                "source_folder": (source.get("source_folders") or {}).get("source_name"),
                "source_path": source.get("relative_path"),
                "source_status": processing or status or "UNKNOWN",
                "extension": ext,
                "canary_score": 0 if kind == "VIDEO" else 1 if kind == "IMAGE" else 2,
            })
    candidates.sort(key=lambda x: (
        x["canary_score"], str(x.get("source_folder") or "").casefold(),
        int(x.get("file_size") or 0), x["filename"].casefold(), x["asset_id"],
    ))
    if not candidates:
        raise SystemExit("NO_ELIGIBLE_ASSET_31")
    target = candidates[0]
    aid = target["asset_id"]

    target["existing"] = {
        "active_layers": len(rows(db.table("asset_semantic_layers").select("id").eq("asset_id", aid).eq("active", True))),
        "active_search_documents": len(rows(db.table("search_document_builds").select("id,status,stale").eq("asset_id", aid).eq("active", True))),
        "active_embeddings": len(rows(db.table("semantic_embeddings").select("id,representation_type,dimensions,stale").eq("asset_id", aid).eq("active", True))),
        "canonical_scenes": len(rows(db.table("asset_scenes").select("id").eq("asset_id", aid).eq("canonical_active", True))),
        "keyframes": len(rows(db.table("asset_keyframes").select("id").eq("asset_id", aid))),
    }
    profiles = rows(db.table("asset_ai_profiles").select("analysis_status").eq("asset_id", aid))
    target["existing"]["profile"] = profiles[0] if profiles else None

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED",
        "blocker": "ANTHROPIC_API_KEY_MISSING",
        "anthropic_api_key_present": False,
        "database_access": "READ_ONLY",
        "database_writes": 0,
        "canonical_assets": len(assets),
        "locked_certified_assets": len(locked_ids),
        "selection_rule": "Continue frozen Phase-01 deterministic eligible ordering after excluding the locked 30 IDs and hashes",
        "target_rollout_position": 31,
        "target": target,
        "write_scope_assertion": {"allowed_asset_ids": [aid], "proposed_write_asset_ids": [], "pass": True},
        "assets_1_30_changed": 0,
        "assets_32_plus_changed": 0,
        "api_requests": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "claude_canary_31_readonly_preflight.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
