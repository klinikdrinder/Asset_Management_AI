import json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"reports/semantic-search/phase8"; MANIFEST=json.loads((ROOT/"config/semantic-search/kdi_semantic_pilot_v1.json").read_text())
def packages():return [json.loads((OUT/f"{x['asset_id']}_narrative_intelligence.json").read_text()) for x in MANIFEST["assets"]]

def test_exact_assets_and_required_narratives():
    rows=packages(); assert len(rows)==10
    for item,row in zip(MANIFEST["assets"],rows):
        assert row["asset_id"]==item["asset_id"] and row["source_fingerprint"]==item["content_fingerprint"]["value"]
        assert all(str(row[key]).strip() for key in ("asset_narrative","short_semantic_summary","search_summary","search_safe_narrative"))
        assert row["input_evidence_fingerprint"] and row["analysis_run_id"] and row["configuration_fingerprint"]

def test_claim_evidence_and_modality_integrity():
    for row in packages():
        assert row["claim_validation"]["valid"] and row["claim_validation"]["unsupported_claims"]==0
        for claim in row["claims"]:assert claim["supports"] and claim["assertion_type"] in {"VISUAL","TRANSCRIPT","OCR","METADATA","MULTIMODAL"}
        assert not any(c["assertion_type"]=="TRANSCRIPT" for c in row["claims"])
        accepted_ocr={x["ocr_observation_id"] for x in row["evidence_bundle"]["ocr_evidence"]}
        for claim in (x for x in row["claims"] if x["assertion_type"]=="OCR"):assert set(claim["supports"])<=accepted_ocr

def test_scene_event_and_image_rules():
    for row in packages():
        if row["media_type"]=="image":assert row["scene_narratives"]==[] and row["event_narratives"]==[] and row["technical_only_events"]==[]
        else:
            scene_ids={x["scene_id"] for x in row["evidence_bundle"]["scenes"]}; duration=max(x["end_time"] for x in row["evidence_bundle"]["scenes"])
            for scene in row["scene_narratives"]:assert scene["scene_id"] in scene_ids and 0<=scene["start_time"]<scene["end_time"]<=duration
            for event in row["event_narratives"]:assert event["scene_id"] in scene_ids and 0<=event["start_time"]<event["end_time"]<=duration

def test_img1238_review_and_technical_events_preserved():
    row=next(x for x in packages() if x["filename"]=="IMG_1238.MP4"); assert row["quality"]["search_status"]=="REVIEW_REQUIRED" and row["img_1238_segmentation"]["status"]=="REVIEW_NEEDED" and not row["img_1238_segmentation"]["scene_split_modified"] and len(row["technical_only_events"])==6

def test_no_unsupported_sensitive_or_outcome_language():
    prohibited=re.compile(r"\b(\d{1,3}-year-old|androgenetic alopecia|guaranteed|successful procedure|excellent result|natural result)\b",re.I)
    for row in packages():assert not prohibited.search(" ".join((row["asset_narrative"],row["search_summary"],row["search_safe_narrative"])))

def test_transcript_and_ocr_safety_counts():
    summary=json.loads((OUT/"phase8_narrative_summary.json").read_text()); assert summary["transcript_available"]==3 and summary["transcript_used"]==0 and summary["ocr_available"]==1 and summary["ocr_used"]==1
    assert summary["evidence_coverage_percent"]==100 and summary["unsupported_claims"]==0

def test_idempotency_and_no_write_paths():
    for row in packages():assert row["idempotency"]["verified"] and not row["prohibitions"]["production_writes"] and not row["prohibitions"]["search_documents_rebuilt"] and not row["prohibitions"]["embeddings_generated"]
