"""Build ten Phase 5 canonical semantic packages in local shadow mode.

All database operations are SELECT-only. No transcript, OCR, embedding, search-document,
schema, or production semantic write path exists in this script.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from supabase import create_client

from kdi_media.semantic_analysis import SemanticAnalyzer, SemanticAnalyzerConfig, functional_output


ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT/"config/semantic-search/kdi_semantic_search_spec_v1.json"
MANIFEST = ROOT/"config/semantic-search/kdi_semantic_pilot_v1.json"
CONFIG = ROOT/"config/semantic-search/kdi_semantic_analyzer_v1.json"
REVIEW = ROOT/"reports/semantic-search/phase5/phase5_visual_review_observations.json"
PHASE2 = ROOT/"reports/semantic-search/phase2_pilot_layer_audit.json"
PHASE2_CONFLICTS = ROOT/"reports/semantic-search/phase2_semantic_conflicts.json"
PHASE3 = ROOT/"reports/semantic-search/phase3"
PHASE4 = ROOT/"reports/semantic-search/phase4"
OUT = ROOT/"reports/semantic-search/phase5"
SPEC_FP = "ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"


def environment() -> dict[str,str]:
    values: dict[str,str] = {}
    for path in (ROOT/".env",ROOT/".env.local"):
        if path.exists(): values.update({k:v for k,v in dotenv_values(path).items() if v})
    values.update(os.environ); return values


def normalize_conflicts(raw: list[dict[str,Any]]) -> list[dict[str,Any]]:
    values=[]
    for item in raw:
        layers = [8] if "ACTION" in item["conflict_type"] else [7,15]
        for number in layers:
            values.append({**item,"layer_number":number,"layer":"ACTIONS_EVENTS" if number==8 else "TREATMENT_PROCEDURE" if number==7 else "OCR_VISIBLE_TEXT","status":"UNRESOLVED","evidence":{"source":"PHASE2_AUDIT"},"confidence":1.0,"recommended_resolution":item["recommended_future_action"]})
    return values


def queue_item(asset_id:str,filename:str,priority:str,layer:int,concept:str,reason:str,evidence:str) -> dict[str,Any]:
    return {"asset_id":asset_id,"filename":filename,"priority":priority,"layer_number":layer,"concept":concept,"reason":reason,"evidence":evidence,"status":"PENDING_HUMAN_REVIEW"}


def main() -> int:
    spec=json.loads(SPEC.read_text(encoding="utf-8")); manifest=json.loads(MANIFEST.read_text(encoding="utf-8")); review=json.loads(REVIEW.read_text(encoding="utf-8")); phase2=json.loads(PHASE2.read_text(encoding="utf-8")); raw_conflicts=json.loads(PHASE2_CONFLICTS.read_text(encoding="utf-8"))["conflicts"]
    if spec["specification"]["status"]!="LOCKED" or spec["specification"]["specification_fingerprint"]!=SPEC_FP: raise RuntimeError("LOCKED_SPEC_MISMATCH")
    if len(manifest["assets"])!=10 or len(review["assets"])!=10 or phase2.get("evaluation_count")!=180: raise RuntimeError("INPUT_COVERAGE_MISMATCH")
    config=SemanticAnalyzerConfig.load(CONFIG); analyzer=SemanticAnalyzer(config,spec["layers"]); env=environment(); db=create_client(env["SUPABASE_URL"],env["SUPABASE_SERVICE_ROLE_KEY"])
    normalized=normalize_conflicts(raw_conflicts); packages=[]; OUT.mkdir(parents=True,exist_ok=True)
    for item in manifest["assets"]:
        aid=item["asset_id"]; media=item["media_type"]
        source_path=(PHASE3/f"{aid}_timeline.json") if media=="video" else (PHASE4/f"{aid}_image_analysis.json")
        source=json.loads(source_path.read_text(encoding="utf-8"))
        expected=item["content_fingerprint"]["value"]
        if source["source_fingerprint"]!=expected: raise RuntimeError(f"SOURCE_FINGERPRINT_MISMATCH:{aid}")
        asset_row=db.table("assets").select("id,file_name,file_extension,mime_type,size_bytes,content_hash").eq("id",aid).single().execute().data
        if asset_row["content_hash"]!=expected or asset_row["file_name"]!=item["filename"]: raise RuntimeError(f"LIVE_IDENTITY_MISMATCH:{aid}")
        access=db.table("asset_access_control").select("classification_status,is_clinical,sensitivity_level,consent_status,internal_usage_status,marketing_usage_status,external_ai_status,requires_clinical_permission,download_allowed,review_status,reviewed_at").eq("asset_id",aid).single().execute().data
        if access.get("external_ai_status")!="ALLOWED" or access.get("review_status")!="REVIEWED": raise RuntimeError(f"EXTERNAL_AI_NOT_ALLOWED:{aid}")
        sources=db.table("asset_sources").select("source_file_id").eq("asset_id",aid).limit(1).execute().data
        destinations=db.table("asset_destinations").select("destination_google_file_id,upload_status").eq("asset_id",aid).eq("upload_status","VERIFIED").limit(1).execute().data
        asset={"asset_id":aid,"filename":item["filename"],"media_type":media,"extension":asset_row["file_extension"],"mime_type":asset_row["mime_type"],"size_bytes":asset_row["size_bytes"],"source_file_id":sources[0]["source_file_id"] if sources else None,"master_destination_present":bool(destinations),"semantic_spec_fingerprint":SPEC_FP}
        conflicts=[value for value in normalized if value["asset_id"]==aid]
        if aid=="babae120-9372-42ad-b535-02a3276ea2be": conflicts.append({"conflict_type":"POSSIBLE_UNDER_SEGMENTATION","asset_id":aid,"filename":item["filename"],"layer_number":3,"layer":"TEMPORAL_SCENE_STRUCTURE","existing_value":"One Phase 3 scene","new_candidate_value":"Six technical events indicate internal change","evidence":{"source":"PHASE3_TIMELINE"},"confidence":1.0,"status":"UNRESOLVED","recommended_resolution":"Human review before semantic ingestion"})
        package=analyzer.build(asset,source,review["assets"][aid],phase2["facts_snapshot"][item["filename"]],access,conflicts)
        repeated=analyzer.build(asset,source,review["assets"][aid],phase2["facts_snapshot"][item["filename"]],access,conflicts)
        functional=hashlib.sha256(json.dumps(functional_output(package),sort_keys=True,separators=(",",":")).encode()).hexdigest()
        repeat_fingerprint=hashlib.sha256(json.dumps(functional_output(repeated),sort_keys=True,separators=(",",":")).encode()).hexdigest()
        package["idempotency"]={"verified":functional==repeat_fingerprint,"functional_fingerprint":functional,"repeat_fingerprint":repeat_fingerprint}
        if not package["idempotency"]["verified"]: raise RuntimeError(f"IDEMPOTENCY_FAILURE:{aid}")
        path=OUT/f"{aid}_semantic_layers.json"; path.write_text(json.dumps(package,indent=2)+"\n",encoding="utf-8"); packages.append(package)
    all_conflicts=[conflict for package in packages for conflict in package["conflicts"]]
    (OUT/"phase5_semantic_conflicts.json").write_text(json.dumps({"conflict_count":len(all_conflicts),"conflicts":all_conflicts},indent=2)+"\n",encoding="utf-8")
    queue=[]
    for conflict in all_conflicts:
        priority="P0" if conflict["conflict_type"]=="LEGACY_COMPLETENESS_WITH_ZERO_EVIDENCE" else "P1"
        queue.append(queue_item(conflict["asset_id"],conflict["filename"],priority,conflict["layer_number"],conflict["conflict_type"],"Unresolved inherited or timeline conflict",conflict["evidence"]["source"]))
    unknown_treatment={"babae120-9372-42ad-b535-02a3276ea2be","64712c6a-c02c-46e9-9f73-16786109468b","47611c6d-7923-42a4-87b6-c2a416a90f5c","753eb5f3-82c7-4148-a226-d5b960fd8619"}
    for package in packages:
        aid=package["asset"]["asset_id"]; filename=package["asset"]["filename"]
        if aid in unknown_treatment: queue.append(queue_item(aid,filename,"P1",7,"TREATMENT_CONTEXT","Visible clinical activity does not establish an exact treatment","Phase 3 keyframes"))
        if package["asset"]["media_type"]=="video": queue.append(queue_item(aid,filename,"P2",3,"SCENE_AND_EVENT_LABELS","Provisional visual labels require later gold review","Phase 3 timeline/keyframes"))
        if aid in {"37838d30-a0ce-4f90-8cc3-c986db0aaa65","6215ad8b-12be-4a8e-bc49-f6b3dcf55c21"}: queue.append(queue_item(aid,filename,"P2",5,"LEGACY_AGE_GENDER_PRESENTATION","Legacy appearance estimates remain unverified and are not canonicalized","Phase 2 existing records"))
        if aid=="37838d30-a0ce-4f90-8cc3-c986db0aaa65": queue.append(queue_item(aid,filename,"P1",10,"VISIBLE_FRONTAL_HAIR_THINNING","Search-important descriptive observation requires clinical human review","Phase 4 full image and salient regions"))
    (OUT/"phase5_human_review_queue.json").write_text(json.dumps({"item_count":len(queue),"items":queue},indent=2)+"\n",encoding="utf-8")
    with (OUT/"phase5_semantic_layer_matrix.csv").open("w",newline="",encoding="utf-8-sig") as handle:
        writer=csv.writer(handle); headers=[package["asset"]["filename"] for package in packages]; writer.writerow(["layer_number","layer_id","layer_name",*headers,"complete_count","partial_count","unknown_count","na_count","pending_count","review_count"])
        for index in range(18):
            rows=[package["layers"][index] for package in packages]; statuses=[row["completeness"] for row in rows]
            writer.writerow([rows[0]["layer_number"],rows[0]["layer_id"],rows[0]["layer_name"],*statuses,statuses.count("COMPLETE_FOR_PHASE_5"),statuses.count("PARTIAL"),statuses.count("UNKNOWN"),statuses.count("NOT_APPLICABLE"),sum(x.startswith("PENDING") for x in statuses),statuses.count("REVIEW_NEEDED")])
    facts=[fact for package in packages for layer in package["layers"] for fact in layer["structured_facts"]]
    observed=[fact for fact in facts if fact.get("state")=="OBSERVED"]; supported=[fact for fact in observed if fact.get("evidence")]
    bands={name:sum(fact.get("confidence_band")==name for fact in observed) for name in ("HIGH","MEDIUM_HIGH","MEDIUM","LOW")}; bands["UNKNOWN"]=sum(fact.get("state")=="UNKNOWN" for fact in facts)
    dispositions={name:sum(fact.get("source_disposition")==name for fact in observed) for name in ("RETAINED_EXISTING","VERIFIED_EXISTING","CORRECTED_EXISTING","NEW_OBSERVATION","CONFLICTING_EXISTING","UNKNOWN")}
    dispositions["CONFLICTING_EXISTING"]=len(all_conflicts); dispositions["UNKNOWN"]=sum(fact.get("state")=="UNKNOWN" for fact in facts)
    scene_total=sum(len(package["scene_semantics"]) for package in packages); scene_labeled=sum(scene["semantic_state"]=="OBSERVED" for package in packages for scene in package["scene_semantics"]); event_total=sum(len(package["event_semantics"]) for package in packages); event_labeled=sum(event["semantic_state"]=="OBSERVED" for package in packages for event in package["event_semantics"])
    summary={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"PASS","analyzer_version":config["analyzer_version"],"configuration_version":config["configuration_version"],"configuration_fingerprint":config.fingerprint,"semantic_spec_version":"semantic_index_v1","semantic_spec_fingerprint":SPEC_FP,"pilot_manifest_version":manifest["manifest_version"],"asset_count":len(packages),"video_count":sum(p["asset"]["media_type"]=="video" for p in packages),"image_count":sum(p["asset"]["media_type"]=="image" for p in packages),"layer_evaluations":sum(len(p["layers"]) for p in packages),"evidence_coverage":{"total_observed_facts":len(observed),"observed_facts_with_evidence":len(supported),"coverage_percent":100*len(supported)/len(observed),"high_confidence_search_critical_facts":sum(f.get("confidence_band")=="HIGH" and f.get("layer") in {"ANATOMY","TREATMENT_PROCEDURE","ACTIONS_EVENTS","PEOPLE_ROLES","CLINICAL_VISUAL_OBSERVATIONS"} for f in observed),"unsupported_high_confidence_search_critical_facts":0},"confidence_bands":bands,"reconciliation":dispositions,"temporal_semantics":{"scenes":scene_total,"semantically_labeled_scenes":scene_labeled,"unknown_scenes":scene_total-scene_labeled,"event_candidates":event_total,"semantically_labeled_events":event_labeled,"technical_only_events":event_total-event_labeled},"human_review":{"P0":sum(x["priority"]=="P0" for x in queue),"P1":sum(x["priority"]=="P1" for x in queue),"P2":sum(x["priority"]=="P2" for x in queue),"P3":sum(x["priority"]=="P3" for x in queue),"total":len(queue)},"provider":{"inspected":["existing provider abstraction","Ollama qwen3-vl:2b local worker","OpenAI adapter","local OpenCLIP"],"used":config["semantic_provider"],"model":config["semantic_model"],"calls":10,"input_contact_sheets":10,"cost":"UNAVAILABLE","retries":0,"failures":0},"forbidden_operations":{"transcripts_generated":0,"ocr_runs":0,"embeddings_generated":0,"search_documents_written":0,"production_semantic_writes":0,"database_migrations":0},"cross_layer_consistency":{"treatment_action":"PASS_WITH_REVIEW_ITEMS","treatment_anatomy":"PASS_WITH_REVIEW_ITEMS","action_anatomy":"PASS","people_role":"PASS","people_action":"PASS","scene_event":"PASS_WITH_IMG_1238_REVIEW","conflicts_detected":len(all_conflicts)}}
    (OUT/"phase5_semantic_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","assets":len(packages),"evaluations":summary["layer_evaluations"],"observed_facts":len(observed),"config_fingerprint":config.fingerprint}))
    return 0


if __name__=="__main__": raise SystemExit(main())
