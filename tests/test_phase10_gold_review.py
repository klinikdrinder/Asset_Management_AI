import json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from kdi_media.gold_standard_review import validate_for_signoff

OUT=ROOT/"reports/semantic-search/phase10/review";MANIFEST=json.loads((ROOT/"config/semantic-search/kdi_semantic_pilot_v1.json").read_text());DECISIONS={"APPROVE_AS_IS","CORRECT","REJECT","CONFIRM_UNKNOWN","NOT_APPLICABLE"}
def packets():return [json.loads((OUT/f"{a['asset_id']}_review_packet.json").read_text()) for a in MANIFEST["assets"]]

def test_ten_draft_packets_and_180_empty_human_decisions():
    values=packets();assert len(values)==10;assert sum(len(x["layer_decisions"]) for x in values)==180
    assert all(x["review_status"]=="AWAITING_HUMAN_REVIEW" and not x["explicit_signoff"] for x in values)
    assert all(layer["human_decision"] is None for x in values for layer in x["layer_decisions"])

def test_source_identity_and_evidence_fingerprints():
    for packet,asset in zip(packets(),MANIFEST["assets"]):
        assert packet["asset_id"]==asset["asset_id"] and packet["filename"]==asset["filename"]
        assert packet["source_fingerprint"]==asset["content_fingerprint"]["value"]
        assert len(packet["input_evidence_fingerprint"])==64 and len(packet["review_packet_fingerprint"])==64

def test_all_p1_issues_are_present_and_unresolved():
    issues=[item for packet in packets() for item in packet["critical_issue_decisions"]]
    assert len(issues)==5 and all(item["priority"]=="P1" and item["human_decision"] is None for item in issues)

def test_signoff_is_blocked_without_real_human_decisions():
    for packet in packets():assert validate_for_signoff(packet,DECISIONS)

def test_images_are_non_temporal_and_no_gold_exists():
    images=[x for x in packets() if x["media_type"]=="image"]
    assert all(not x["temporal_review"]["ai_scenes"] and x["transcript_review"]["human_decision"]=="NOT_APPLICABLE" for x in images)
    gold=ROOT/"reports/semantic-search/phase10/gold";assert not gold.exists() or not list(gold.glob("*_gold_standard.json"))

