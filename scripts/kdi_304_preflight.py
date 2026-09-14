"""Read-only preflight for the frozen LOCAL_PREPARATION cohort."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "reports/semantic-search/rollout/full/local-preparation-checkpoint.json"


def groups(values, size=40):
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def rows_for(db, table, columns, ids, key="asset_id"):
    out = []
    for batch in groups(ids):
        out += db.table(table).select(columns).in_(key, batch).execute().data or []
    return out


def digest(rows):
    normalized = json.dumps(sorted(rows, key=lambda x: json.dumps(x, sort_keys=True)),
                            sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()


def main():
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=False)
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    cp = json.loads(CHECKPOINT.read_text(encoding="utf-8"))["assets"]
    complete_cp = {aid: row for aid, row in cp.items() if row.get("local_evidence_complete") is True}
    runs = (db.table("semantic_analysis_runs")
            .select("id,asset_id,run_type,status,completed_at,provider,model,model_version,source_fingerprint,metadata")
            .eq("run_type", "LOCAL_PREPARATION")
            .eq("metadata->>local_evidence_complete", "true").execute().data or [])
    target_ids = sorted({r["asset_id"] for r in runs})
    print(f"TARGET_ASSET_COUNT={len(target_ids)}")
    if len(target_ids) != 304:
        raise SystemExit("BLOCKED:TARGET_ASSET_COUNT_NOT_304")
    if set(target_ids) != set(complete_cp):
        raise SystemExit("BLOCKED:DATABASE_CHECKPOINT_COHORT_MISMATCH")
    assets = rows_for(db, "assets", "id,file_name,mime_type,file_extension,content_hash,checksum_sha256", target_ids, "id")
    acl = rows_for(db, "asset_access_control",
                   "asset_id,classification_status,internal_usage_status,external_ai_status,download_allowed",
                   target_ids)
    scenes = rows_for(db, "asset_scenes", "id,asset_id,scene_index,start_seconds,end_seconds,semantic_analysis_run_id", target_ids)
    frames = rows_for(db, "asset_keyframes", "id,asset_id,scene_id,timestamp_seconds,semantic_analysis_run_id", target_ids)
    layers_all = db.table("asset_semantic_layers").select("asset_id,layer_id,active,processing_status,semantic_state").eq("active", True).execute().data or []
    lc = Counter(x["asset_id"] for x in layers_all)
    certified = sorted(aid for aid, count in lc.items() if count == 18 and aid not in target_ids)
    if len(certified) != 30:
        raise SystemExit(f"BLOCKED:CERTIFIED_BASELINE_COUNT_{len(certified)}")
    base_layers = [x for x in layers_all if x["asset_id"] in certified]
    base_docs = rows_for(db, "search_document_builds", "id,asset_id,document_type,status,active,stale,document_fingerprint", certified)
    base_emb = rows_for(db, "semantic_embeddings", "id,asset_id,representation_type,dimensions,active,stale,vector_fingerprint", certified)
    base_ready = rows_for(db, "kdi_search_ready_assets_v1", "asset_id,search_ready", certified)
    scene_ids = {x["id"] for x in scenes}
    kf_counts = Counter(x["scene_id"] for x in frames)
    missing = [f["path"] for aid in target_ids for f in complete_cp[aid].get("keyframes", []) if not Path(f["path"]).is_file()]
    report = {
        "target_asset_ids": target_ids,
        "target_manifest_sha256": hashlib.sha256(("\n".join(target_ids) + "\n").encode()).hexdigest(),
        "media": dict(Counter("VIDEO" if (a.get("mime_type") or "").startswith("video/") else
                              "IMAGE" if (a.get("mime_type") or "").startswith("image/") else "DOCUMENT" for a in assets)),
        "runs": {"rows": len(runs), "assets": len(target_ids), "statuses": dict(Counter(r["status"] for r in runs))},
        "scenes": len(scenes), "assets_with_scenes": len({x["asset_id"] for x in scenes}),
        "scenes_with_zero_keyframes": sum(kf_counts[sid] == 0 for sid in scene_ids),
        "keyframes": len(frames), "assets_with_keyframes": len({x["asset_id"] for x in frames}),
        "missing_keyframe_paths": missing,
        "target_existing_active_layers": sum(lc[x] for x in target_ids),
        "authorization": {
            "authorized": sorted(x["asset_id"] for x in acl
                                 if x.get("classification_status") == "VERIFIED"
                                 and x.get("internal_usage_status") == "ALLOWED"
                                 and x.get("external_ai_status") == "ALLOWED"),
            "pending": sorted(x["asset_id"] for x in acl
                              if not (x.get("classification_status") == "VERIFIED"
                                      and x.get("internal_usage_status") == "ALLOWED"
                                      and x.get("external_ai_status") == "ALLOWED")),
            "distributions": {
                "classification_status": dict(Counter(x.get("classification_status") for x in acl)),
                "internal_usage_status": dict(Counter(x.get("internal_usage_status") for x in acl)),
                "external_ai_status": dict(Counter(x.get("external_ai_status") for x in acl)),
                "download_allowed": dict(Counter(str(x.get("download_allowed")) for x in acl)),
            },
        },
        "certified_baseline": {"asset_ids": certified, "layers": len(base_layers), "documents": len(base_docs),
                               "embeddings": len(base_emb), "ready": sum(bool(x["search_ready"]) for x in base_ready),
                               "fingerprints": {"layers": digest(base_layers), "documents": digest(base_docs),
                                                "embeddings": digest(base_emb), "ready": digest(base_ready)}},
    }
    out = ROOT / "reports/semantic-search/rollout/full/kdi-304-preflight.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "target_asset_ids"}, indent=2))


if __name__ == "__main__":
    main()
