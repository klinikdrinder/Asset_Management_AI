"""Phase 10 review packets and strict human sign-off validation."""
from __future__ import annotations
import hashlib, json, uuid
from pathlib import Path
from typing import Any

NAMESPACE=uuid.UUID("b56f9382-4fd5-4b98-a805-0993e8cdf337")

def canonical_json(value:Any)->str:return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def fingerprint(value:Any)->str:return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def empty_decision(asset_id:str,layer:dict[str,Any])->dict[str,Any]:
    return {"review_id":str(uuid.uuid5(NAMESPACE,f"{asset_id}:layer:{layer['layer_number']}")),"layer_number":layer["layer_number"],"layer_id":layer["layer_id"],"layer_name":layer["layer_name"],"ai_original":{"applicability":layer["applicability"],"semantic_state":layer["semantic_state"],"structured_facts":layer["structured_facts"],"completeness":layer["completeness"]},"human_decision":None,"human_semantic_state":None,"human_value":None,"reason":None,"evidence_viewed":[],"reviewer_label":None,"review_started_at":None,"review_completed_at":None,"revision":0,"history":[]}

def validate_for_signoff(packet:dict[str,Any],allowed_decisions:set[str])->list[str]:
    errors=[];layers=packet.get("layer_decisions",[])
    if len(layers)!=18 or [x.get("layer_number") for x in layers]!=list(range(1,19)):errors.append("Exactly 18 ordered layer decisions are required")
    for layer in layers:
        decision=layer.get("human_decision")
        if decision not in allowed_decisions:errors.append(f"Layer {layer.get('layer_number')} has no valid human decision")
        if decision in {"CORRECT","REJECT"} and not str(layer.get("reason") or "").strip():errors.append(f"Layer {layer.get('layer_number')} requires a reason")
        if decision=="CORRECT" and layer.get("human_value") is None:errors.append(f"Layer {layer.get('layer_number')} requires a corrected value")
        if not layer.get("reviewer_label") or not layer.get("review_completed_at"):errors.append(f"Layer {layer.get('layer_number')} lacks human review provenance")
    for item in packet.get("critical_issue_decisions",[]):
        if item.get("priority") in {"P0","P1"} and not item.get("human_decision"):errors.append(f"Issue {item.get('issue_id')} is unresolved")
    if packet.get("media_type")=="video" and not packet.get("temporal_review",{}).get("human_decision"):errors.append("Video scene/event review is incomplete")
    if not packet.get("ocr_review",{}).get("human_decision"):errors.append("OCR review is incomplete")
    if packet.get("media_type")=="video" and not packet.get("transcript_review",{}).get("human_decision"):errors.append("Transcript/audio review is incomplete")
    if not packet.get("narrative_review",{}).get("human_decision"):errors.append("Narrative/search-summary review is incomplete")
    return errors

def gold_payload(packet:dict[str,Any],completed_at:str)->dict[str,Any]:
    payload={k:packet[k] for k in ("gold_standard_version","semantic_spec_version","pilot_manifest_version","asset_id","filename","media_type","source_fingerprint")}
    payload.update({"review":{"reviewer_label":packet["reviewer_label"],"status":"SIGNED_OFF","completed_at":completed_at,"revision":packet.get("revision",1)},"layers":packet["layer_decisions"],"scene_overrides":packet["temporal_review"].get("scene_overrides",[]),"event_overrides":packet["temporal_review"].get("event_overrides",[]),"transcript_overrides":packet["transcript_review"].get("overrides",[]),"ocr_overrides":packet["ocr_review"].get("overrides",[]),"narrative_overrides":packet["narrative_review"].get("overrides",[]),"resolved_conflicts":packet["critical_issue_decisions"],"precedence":"HUMAN_GOLD_OVERRIDE","source_review_packet_fingerprint":fingerprint(packet)})
    payload["gold_fingerprint"]=fingerprint(payload);return payload
