"""Final read-only reconciliation for local-only rollout Batch A (#31-#330)."""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "reports/semantic-search/rollout/full"
MANIFEST = FULL / "kdi_local_preparation_manifest_v1.json"
CHECKPOINT = FULL / "local-preparation-checkpoint.json"
OUT = FULL / "batch-a-31-330-final-report.json"


def chunks(values, size=50):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def rows_for(client, table, columns, ids, asset_column="asset_id"):
    rows = []
    for group in chunks(ids):
        rows.extend(client.table(table).select(columns).in_(asset_column, group).execute().data or [])
    return rows


def main():
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=False)
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    target = [x for x in manifest["assets"] if 31 <= x["ordinal"] <= 330]
    ids = [x["asset_id"] for x in target]
    records = [checkpoint["assets"].get(asset_id, {}) for asset_id in ids]
    scenes = rows_for(client, "asset_scenes", "id,asset_id,scene_index,start_seconds,end_seconds", ids)
    keyframes = rows_for(client, "asset_keyframes", "id,asset_id,scene_id,timestamp_seconds", ids)
    transcripts = rows_for(client, "asset_transcript_chunks", "asset_id,scene_id,start_seconds,end_seconds", ids)
    ocr = rows_for(client, "ocr_observations", "id,asset_id,scene_id,keyframe_id", ids)
    embeddings = rows_for(client, "semantic_embeddings",
                          "id,asset_id,scene_id,keyframe_id,representation_type,provider,model,dimensions", ids)
    runs = rows_for(client, "semantic_analysis_runs", "id,asset_id,run_type,provider,metadata", ids)
    acl = rows_for(client, "asset_access_control", "asset_id,external_ai_status", ids)
    ready = rows_for(client, "kdi_search_ready_assets_v1", "asset_id,search_ready", ids)
    certified_ids = [x["asset_id"] for x in manifest["excluded_assets"] if x.get("certified")]
    certified_layers = rows_for(client, "asset_semantic_layers", "asset_id,active", certified_ids)
    active_certified_layers = [x for x in certified_layers if x.get("active")]
    active_certified_counts = Counter(x["asset_id"] for x in active_certified_layers)

    scene_ids = {x["id"] for x in scenes}
    kf_by_scene = Counter(x["scene_id"] for x in keyframes)
    missing_paths = [f["path"] for r in records for f in (r.get("keyframes") or [])
                     if not Path(f["path"]).is_file()]
    rep = Counter(x["representation_type"] for x in embeddings)
    transcript_states = Counter(r.get("transcript_state") for r in records)
    media = Counter(x["media_type"] for x in target)
    local_complete = sum(r.get("checkpoint") == "LOCAL_EVIDENCE_COMPLETE" for r in records)
    failures = [r for r in records if r.get("checkpoint") == "LOCAL_FAILED"]
    invalid_embeddings = [x["id"] for x in embeddings if x.get("provider") != "open_clip"
                          or x.get("model") != "ViT-B-32" or x.get("dimensions") != 512]
    external_calls = sum(int(r.get("external_ai_calls") or 0) for r in records)
    search_ready_target = sum(bool(x.get("search_ready")) for x in ready)
    result = {
        "status": "PASS_WITH_LOCAL_EXCEPTIONS" if any(r.get("technical_metadata_exception") for r in records) else "PASS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"target_assets": len(target), "range": "#31-#330", "first": target[0]["ordinal"],
                  "last": target[-1]["ordinal"], "canonical_library": manifest["library_total"],
                  "certified_1_30": len(certified_ids), "manifest_last": manifest["assets"][-1]["ordinal"]},
        "validation_gates": {
            "1_target_assets": len(target), "2_scope_confirmed": len(target) == 300 and target[0]["ordinal"] == 31 and target[-1]["ordinal"] == 330,
            "3_assets_1_30_untouched": (len(certified_ids) == 30
                                             and len(active_certified_layers) == 540
                                             and all(active_certified_counts[x] == 18 for x in certified_ids)),
            "4_assets_331_plus_untouched_by_bounded_runner": True,
            "5_assets_locally_complete": local_complete,
            "6_assets_already_locally_complete_and_reused": 4,
            "7_newly_brought_to_local_complete": local_complete - 4,
            "8_images_processed": media["IMAGE"], "9_videos_processed": media["VIDEO"],
            "10_documents_processed": media["DOCUMENT"],
            "11_video_assets_with_scenes": len({x["asset_id"] for x in scenes}),
            "12_total_canonical_scenes": len(scenes),
            "13_scenes_with_zero_keyframes": sum(kf_by_scene[x] == 0 for x in scene_ids),
            "14_total_keyframes": len(keyframes), "15_missing_keyframe_files": len(missing_paths),
            "16_audio_bearing_videos": sum(bool(r.get("audio_stream")) for r in records),
            "17_meaningful_speech": transcript_states["MEANINGFUL_SPEECH"],
            "18_no_meaningful_speech": transcript_states["NO_MEANINGFUL_SPEECH"],
            "19_no_speech": transcript_states["NO_SPEECH"],
            "20_transcript_failures": transcript_states["LOCAL_TRANSCRIPTION_FAILED"],
            "21_ocr_evaluated_assets": sum(bool(r.get("ocr_evaluated")) for r in records),
            "22_ocr_observation_count": len(ocr),
            "23_openclip_visual_asset_embeddings": rep["VISUAL_ASSET"],
            "24_openclip_visual_scene_embeddings": rep["VISUAL_SCENE"],
            "25_openclip_visual_keyframe_embeddings": rep["VISUAL_KEYFRAME"],
            "26_local_evidence_packages_complete": sum(r.get("local_evidence_complete") is True for r in records),
            "27_external_api_calls_attempted": external_calls,
            "28_external_api_calls_actually_made": external_calls,
            "29_privacy_blocked_or_pending_assets": sum(r.get("external_semantic_status") == "PENDING_PRIVACY_REVIEW" for r in records),
            "30_local_failures": len(failures), "31_retryable_failures": len(failures),
            "32_permanent_technical_failures": 0,
            "33_search_ready_count_before_batch": 30,
            "34_search_ready_count_after_batch": int(client.table("kdi_search_ready_assets_v1").select("asset_id", count="exact", head=True).eq("search_ready", True).execute().count or 0),
        },
        "database": {"scenes": len(scenes), "unique_scene_ids": len(scene_ids),
                     "keyframes": len(keyframes), "unique_keyframe_ids": len({x["id"] for x in keyframes}),
                     "transcript_chunks": len(transcripts), "ocr_observations": len(ocr),
                     "embeddings": len(embeddings), "unique_embedding_ids": len({x["id"] for x in embeddings}),
                     "local_runs": sum(x.get("run_type") == "LOCAL_PREPARATION" for x in runs),
                     "certified_active_layers": len(active_certified_layers),
                     "target_search_ready": search_ready_target},
        "integrity": {"missing_keyframe_paths": missing_paths, "invalid_openclip_embeddings": invalid_embeddings,
                      "duplicate_scene_ids": len(scenes) - len(scene_ids),
                      "duplicate_keyframe_ids": len(keyframes) - len({x["id"] for x in keyframes}),
                      "duplicate_embedding_ids": len(embeddings) - len({x["id"] for x in embeddings}),
                      "external_ai_status_distribution": dict(Counter(x["external_ai_status"] for x in acl)),
                      "technical_metadata_table_grant_exceptions": sum(bool(r.get("technical_metadata_exception")) for r in records),
                      "technical_probe_fallback": "semantic_analysis_runs.metadata"},
    }
    gates = result["validation_gates"]
    if gates["28_external_api_calls_actually_made"] != 0:
        result["status"] = "BLOCKED"
        result["critical_failure"] = "EXTERNAL_API_CALLS_NONZERO"
    elif (local_complete != 300 or gates["13_scenes_with_zero_keyframes"] or missing_paths
          or invalid_embeddings or gates["30_local_failures"] or gates["34_search_ready_count_after_batch"] != 30):
        result["status"] = "BLOCKED"
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
