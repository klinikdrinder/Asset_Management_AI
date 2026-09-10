import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"reports/semantic-search/phase7"; MANIFEST=json.loads((ROOT/"config/semantic-search/kdi_semantic_pilot_v1.json").read_text())

def packages():return [json.loads((OUT/f"{x['asset_id']}_ocr_intelligence.json").read_text()) for x in MANIFEST["assets"]]

def test_exact_pilot_artifacts_and_fingerprints():
    rows=packages(); assert len(rows)==10
    for item,row in zip(MANIFEST["assets"],rows):
        assert row["asset_id"]==item["asset_id"] and row["source_fingerprint"]==item["content_fingerprint"]["value"]
        assert row["semantic_spec_fingerprint"]=="ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"

def test_complete_coverage_and_keyframe_priority():
    for row in packages():
        assert row["scan_coverage"]["scan_complete"] and row["scan_coverage"]["coverage_percent"]==100.0
        if row["media_type"]=="video":assert row["scan_coverage"]["frames_text_scanned"]==row["scan_coverage"]["frames_in_timeline"] and row["scan_coverage"]["phase3_keyframes_prioritized"]>0
        else:assert row["scan_coverage"]["full_image_scanned"]

def test_observation_provenance_and_search_safety():
    for package in packages():
        for row in package["ocr_observations"]:
            box=row["bounding_box"]; assert 0<=box["nx1"]<box["nx2"]<=1 and 0<=box["ny1"]<box["ny2"]<=1
            assert row["raw_text"] is not None and row["normalized_text"] is not None and row["search_status"] in {"ACCEPTED_FOR_SEARCH","REVIEW_REQUIRED","REJECTED_LOW_CONFIDENCE","REJECTED_GIBBERISH","DUPLICATE"}
            if row["search_status"]=="ACCEPTED_FOR_SEARCH":assert row["search_text"] and row["search_text_fingerprint"]
            if package["media_type"]=="video":assert row["frame_number"] is not None and row["timestamp_start"] is not None

def test_negative_and_external_safety():
    for row in packages():
        assert row["layer_15"]["applicability"]=="APPLICABLE" and row["layer_15"]["visible_text_state"] in {"OBSERVED","FALSE","UNKNOWN"}
        if row["layer_15"]["visible_text_state"]=="FALSE":assert row["scan_coverage"]["scan_complete"] and row["status"]=="COMPLETED"
        assert row["authorization"]["media_transmitted_externally"] is False and row["prohibitions"]["production_writes"] is False

def test_summary_and_embedding_deferment():
    summary=json.loads((OUT/"phase7_ocr_summary.json").read_text()); embedding=json.loads((OUT/"phase7_ocr_embedding_summary.json").read_text())
    assert summary["assets_scanned"]==10 and summary["videos"]==8 and summary["images"]==2
    assert embedding["status"]=="DEFERRED" and embedding["embeddings_generated"]==0
