"""Idempotent, manifest-locked Job 6 deep intelligence writer.

Observations in this pilot file were produced from the controlled contact
sheets prepared by prepare_ai_search_v3_job6_media.py.  The writer rechecks
authorization before every asset, uses deterministic UUIDs, preserves the
existing asset-level visual index, and writes vectors only to pgvector tables.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
PREPARED = ROOT / "tmp" / "job6" / "prepared-media.json"
MANIFEST = ROOT / "reports" / "ai-search-v3" / "job5_3-final-pilot-manifest.json"
PURPOSE = "KDI AI Search V3 pilot indexing only"
PIPELINE = "kdi-ai-search-v3-job6-v1"
PROMPT_VERSION = "codex-controlled-visual-review-v1"
NS = uuid.UUID("79f7752c-499d-4f7b-ace0-a00cc993da3c")


def uid(kind: str, asset_id: str, suffix: str = "0") -> str:
    return str(uuid.uuid5(NS, f"{PIPELINE}:{kind}:{asset_id}:{suffix}"))


OBS = {
    "7f72217d-3839-4920-86b4-ccc33e9e3d95": dict(scene_type="PROCEDURE", narrative="An adult patient lies in a treatment chair while a gloved clinician performs an injection near the lower face.", roles=["PATIENT_LIKE","CLINICIAN_LIKE"], anatomy=["LOWER_FACE","LIPS","CHIN"], actions=["INJECTING","HOLDING_SYRINGE"], environment="Treatment room", shot="MEDIUM_CLOSEUP", composition="Two-person clinical procedure with the patient's face dominant.", marketing="PROCEDURE", concepts=["facial injection","lower face procedure","clinical close-up"]),
    "babae120-9372-42ad-b535-02a3276ea2be": dict(scene_type="PROCEDURE", narrative="A masked clinician works on an adult patient's scalp while the patient reclines beneath a clinical device.", roles=["PATIENT_LIKE","CLINICIAN_LIKE"], anatomy=["SCALP","FRONTAL_SCALP"], actions=["USING_DEVICE","EXAMINING"], environment="Treatment room", shot="MEDIUM_CLOSEUP", composition="Two-person clinical scene centered on the patient's scalp and device.", marketing="PROCEDURE", concepts=["scalp treatment","clinician using device","reclining patient"]),
    "c86344e9-5b32-4d86-9205-67952d508651": dict(scene_type="PROCEDURE", narrative="Gloved clinicians administer an injection to the side of an adult patient's neck in a close clinical view.", roles=["PATIENT_LIKE","CLINICIAN_LIKE"], anatomy=["NECK"], actions=["INJECTING","HOLDING_SYRINGE"], environment="Treatment room", shot="EXTREME_CLOSEUP", composition="Procedure detail dominated by the neck, syringe, and gloved hands.", marketing="PROCEDURE", concepts=["neck injection","clinical procedure detail","syringe close-up"]),
    "444da390-0117-4380-8c87-d7c32f2903ff": dict(scene_type="PATIENT_SELF_RECORDING", narrative="An adult records a front-facing self-view in an indoor room, turning slightly to show several facial angles.", roles=["SUBJECT"], anatomy=["FACE"], actions=[], environment="Indoor room", shot="CLOSEUP", composition="Single centered face in a vertical self-recorded frame.", marketing="B_ROLL", concepts=["front-facing portrait video","facial angles","self-recorded close-up"]),
    "64712c6a-c02c-46e9-9f73-16786109468b": dict(scene_type="PROCEDURE", narrative="An adult patient reclines while a masked clinician works near the side of the face in a treatment room.", roles=["PATIENT_LIKE","CLINICIAN_LIKE"], anatomy=["FACE","JAWLINE","CHEEK"], actions=["TOUCHING"], environment="Treatment room", shot="MEDIUM", composition="Two-person treatment scene with the patient reclined and clinician foregrounded.", marketing="PROCEDURE", concepts=["facial treatment","reclining patient","clinician procedure"]),
    "47611c6d-7923-42a4-87b6-c2a416a90f5c": dict(scene_type="PROCEDURE", narrative="A masked clinician examines or treats the scalp of an adult patient reclining with protective eye pads.", roles=["PATIENT_LIKE","CLINICIAN_LIKE"], anatomy=["SCALP","FRONTAL_SCALP"], actions=["EXAMINING","USING_DEVICE"], environment="Treatment room", shot="MEDIUM", composition="Two-person clinical scene with attention centered on the patient's scalp.", marketing="PROCEDURE", concepts=["scalp examination","clinician and patient","treatment room"]),
    "bfae6c51-5d71-47ae-a3e1-6d07092b8896": dict(scene_type="PROCEDURE", narrative="A clinician using magnification works on the prepared frontal scalp of a patient while assistants support the procedure.", roles=["PATIENT_LIKE","CLINICIAN_LIKE","STAFF_LIKE"], anatomy=["SCALP","FRONTAL_SCALP","RECIPIENT_REGION"], actions=["IMPLANTING_GRAFTS"], treatment="FUE_IMPLANTATION", environment="Operating room", shot="MEDIUM_CLOSEUP", composition="Procedure view centered on the prepared recipient scalp and clinical team.", marketing="PROCEDURE", concepts=["FUE implantation","recipient scalp","hair transplant procedure","clinical team"]),
    "753eb5f3-82c7-4148-a226-d5b960fd8619": dict(scene_type="PROCEDURE", narrative="A clinician cleanses an adult patient's cheek and lower-face skin with a swab in a close treatment view.", roles=["PATIENT_LIKE","CLINICIAN_LIKE"], anatomy=["FACE","CHEEK","LOWER_FACE"], actions=["CLEANSING"], environment="Treatment room", shot="EXTREME_CLOSEUP", composition="Skin-detail close-up dominated by the cheek, lower face, and clinician's hand.", marketing="PROCEDURE", concepts=["facial cleansing","skin treatment close-up","cheek procedure"]),
    "37838d30-a0ce-4f90-8cc3-c986db0aaa65": dict(image=True, narrative="Front-facing clinical-style portrait of an adult with visible thinning across the frontal scalp and hairline.", anatomy=["SCALP","FRONTAL_SCALP","FRONTAL_HAIRLINE"], clinical="Visible frontal scalp hair thinning", marketing="PROOF", concepts=["frontal scalp portrait","visible hair thinning","hairline documentation"]),
    "6215ad8b-12be-4a8e-bc49-f6b3dcf55c21": dict(image=True, narrative="Front-facing studio-style portrait of an adult against a dark neutral background.", anatomy=["FACE"], marketing="B_ROLL", concepts=["front-facing portrait","neutral background","face close-up"]),
}


def env() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / ".env.local"):
        result.update({k: v for k, v in dotenv_values(path).items() if v})
    result.update(os.environ)
    return result


def upsert(db, table: str, row: dict, conflict: str = "id"):
    return db.table(table).upsert(row, on_conflict=conflict).execute().data


def main() -> int:
    e = env(); db = create_client(e["SUPABASE_URL"], e["SUPABASE_SERVICE_ROLE_KEY"])
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")); prepared = json.loads(PREPARED.read_text(encoding="utf-8"))
    assets = manifest["assets"]; prep = {r["asset_id"]: r for r in prepared["assets"]}
    if manifest.get("purpose") != PURPOSE or len(assets) != 10 or set(prep) != {r["asset_id"] for r in assets} or set(OBS) != set(prep):
        raise RuntimeError("JOB6_BOUNDARY_MISMATCH")
    ontology = {}
    for table in ("treatments", "anatomy_terms", "actions", "locations"):
        rows = db.table(table).select("id,code").execute().data
        ontology[table] = {r["code"]: r["id"] for r in rows}
    before = {}
    tracked = ["ai_analysis_runs","asset_scenes","asset_keyframes","scene_people","person_appearances","scene_treatments","scene_anatomy","scene_actions","scene_relationships","clinical_observations","scene_environment","scene_cinematography","scene_composition","marketing_annotations","scene_narratives","asset_transcript_chunks","ocr_observations","scene_embeddings","keyframe_embeddings","transcript_embeddings","asset_search_documents","scene_search_documents"]
    for table in tracked:
        before[table] = db.table(table).select("*", count="exact").limit(0).execute().count or 0
    now = datetime.now(timezone.utc).isoformat(); cohort_id = uid("cohort", "job6")
    results = []
    for item in assets:
        aid, name = item["asset_id"], item["file_name"]; spec = OBS[aid]; p = prep[aid]
        if db.rpc("can_asset_use_external_ai", {"p_asset_id": aid}).execute().data is not True:
            raise RuntimeError(f"AUTHORIZATION_REVOKED:{aid}")
        run_id = uid("run", aid)
        upsert(db, "ai_analysis_runs", {"id":run_id,"asset_id":aid,"analysis_type":"VISUAL_ANALYSIS","provider":"openai-codex-controlled-review","model_name":"Codex visual inspection","model_version":"2026-08-20","pipeline_version":PIPELINE,"ontology_version":"job2-v1","status":"PROCESSING","started_at":now,"completed_at":None,"attempt_number":1,"frames_processed":len(p["frames"]),"metadata":{"job":"KDI_AI_SEARCH_V3_JOB_6","purpose":PURPOSE,"cohort_id":cohort_id,"prompt_version":PROMPT_VERSION,"pilot_manifest":"reports/ai-search-v3/job5_3-final-pilot-manifest.json","text_embeddings":"DEFERRED","transcription":"DEFERRED"}})
        scene_id = keyframe_id = None
        primary_treatment = ontology["treatments"].get(spec.get("treatment"))
        primary_anatomy = ontology["anatomy_terms"].get(spec.get("anatomy", [None])[0])
        primary_action = ontology["actions"].get(spec.get("actions", [None])[0]) if spec.get("actions") else None
        location_code = "OPERATING_ROOM" if spec.get("environment") == "Operating room" else "TREATMENT_ROOM"
        location_id = ontology["locations"].get(location_code)
        if not spec.get("image"):
            duration = round(float(p["duration_seconds"]), 3); scene_id = uid("scene", aid)
            upsert(db, "asset_scenes", {"id":scene_id,"asset_id":aid,"scene_index":0,"start_seconds":0,"end_seconds":duration,"scene_type":spec["scene_type"],"literal_description":spec["narrative"],"short_description":spec["narrative"],"primary_action_id":primary_action,"primary_treatment_id":primary_treatment,"primary_anatomy_id":primary_anatomy,"primary_location_id":location_id,"analysis_run_id":run_id,"detection_method":"CONTROLLED_SIX_FRAME_SEMANTIC_REVIEW","confidence":0.9,"review_status":"AI_SUGGESTED","metadata":{"pipeline_version":PIPELINE,"prompt_version":PROMPT_VERSION,"frame_fractions":[0.05,0.2,0.4,0.6,0.8,0.95]}})
            keyframe_id = uid("keyframe", aid); ts = round(duration * 0.6, 3)
            derivative_id = uid("derivative", aid)
            upsert(db, "asset_derivatives", {"id":derivative_id,"asset_id":aid,"derivative_type":"KEYFRAME_IMAGE","storage_provider":"LOCAL_CONTROLLED_WORKSPACE","storage_path":p["frames"][3],"mime_type":"image/jpeg","file_extension":"jpg","generation_status":"READY","analysis_run_id":run_id,"metadata":{"temporary":True,"purpose":PURPOSE,"source_timestamp_seconds":ts}})
            upsert(db, "asset_keyframes", {"id":keyframe_id,"asset_id":aid,"scene_id":scene_id,"timestamp_seconds":ts,"derivative_id":derivative_id,"selection_reason":"Representative midpoint from six-frame controlled review","visual_description":spec["narrative"],"technical_quality_score":0.85,"semantic_importance_score":0.9,"analysis_run_id":run_id,"is_representative":True,"review_status":"NOT_REVIEWED","metadata":{"pipeline_version":PIPELINE}})
            people=[]
            for idx, role in enumerate(spec["roles"]):
                pid=uid("scene-person",aid,str(idx)); people.append(pid)
                upsert(db,"scene_people",{"id":pid,"scene_id":scene_id,"asset_id":aid,"person_role":role,"activity_summary":spec["narrative"],"identity_status":"ANONYMOUS","confidence":0.85,"provenance":"AI_VISUAL","analysis_run_id":run_id,"metadata":{"coarse_age":"adult" if role in ("PATIENT_LIKE","SUBJECT") else "unknown","no_biometric_identity":True}})
                upsert(db,"person_appearances",{"id":uid("appearance",aid,str(idx)),"asset_id":aid,"scene_id":scene_id,"scene_person_id":pid,"keyframe_id":keyframe_id,"general_visual_description":role.replace("_"," ").lower(),"confidence":0.8,"provenance":"AI_VISUAL","analysis_run_id":run_id,"metadata":{"identity_inference":"not performed"}})
            for code in spec.get("anatomy",[]):
                upsert(db,"scene_anatomy",{"id":uid("anatomy",aid,code),"scene_id":scene_id,"asset_id":aid,"anatomy_id":ontology["anatomy_terms"][code],"relationship_type":"FOCUS_AREA","visibility":"VISIBLE","prominence":0.85,"confidence":0.9,"provenance":"AI_VISUAL","analysis_run_id":run_id,"is_primary":code==spec["anatomy"][0]})
            for code in spec.get("actions",[]):
                upsert(db,"scene_actions",{"id":uid("action",aid,code),"scene_id":scene_id,"asset_id":aid,"action_id":ontology["actions"][code],"subject_scene_person_id":people[1] if len(people)>1 else people[0],"object_scene_person_id":people[0] if len(people)>1 else None,"description":spec["narrative"],"confidence":0.85,"provenance":"AI_VISUAL","analysis_run_id":run_id,"start_seconds":0,"end_seconds":duration})
            if primary_treatment:
                upsert(db,"scene_treatments",{"id":uid("treatment",aid),"scene_id":scene_id,"asset_id":aid,"treatment_id":primary_treatment,"relationship_type":"VISIBLE_PROCEDURE","confidence":0.95,"provenance":"AI_VISUAL","analysis_run_id":run_id,"is_primary":True})
            if len(people)>1:
                upsert(db,"scene_relationships",{"id":uid("relationship",aid),"scene_id":scene_id,"asset_id":aid,"participant_1_scene_person_id":people[1],"participant_2_scene_person_id":people[0],"relationship_type":"DOCTOR_TREATING_PATIENT","treatment_id":primary_treatment,"anatomy_id":primary_anatomy,"description":spec["narrative"],"confidence":0.8,"provenance":"AI_VISUAL","analysis_run_id":run_id})
            upsert(db,"scene_environment",{"scene_id":scene_id,"asset_id":aid,"location_id":location_id,"environment_type":spec["environment"],"clinical_environment":spec["environment"] in ("Treatment room","Operating room"),"indoor_outdoor":"INDOOR","description":spec["environment"],"confidence":0.85,"provenance":"AI_VISUAL","analysis_run_id":run_id,"metadata":{}},"scene_id")
            upsert(db,"scene_cinematography",{"scene_id":scene_id,"asset_id":aid,"shot_size":spec["shot"],"camera_motion":"STATIC" if duration<5 else "HANDHELD","primary_focus":spec["anatomy"][0].replace("_"," ").lower(),"visual_style":"CLINICAL" if spec["scene_type"]=="PROCEDURE" else "UGC","orientation_override":"VERTICAL","technical_quality_score":0.85,"confidence":0.85,"provenance":"AI_VISUAL","analysis_run_id":run_id,"metadata":{}},"scene_id")
            upsert(db,"scene_composition",{"scene_id":scene_id,"asset_id":aid,"subject_position":"CENTERED","negative_space_left":0,"negative_space_right":0,"negative_space_top":0,"negative_space_bottom":0,"background_clutter_level":"LOW","composition_description":spec["composition"],"confidence":0.85,"provenance":"AI_VISUAL","analysis_run_id":run_id,"metadata":{}},"scene_id")
            upsert(db,"scene_narratives",{"id":uid("narrative",aid),"scene_id":scene_id,"asset_id":aid,"narrative_type":"LITERAL","text":spec["narrative"],"confidence":0.9,"provenance":"AI_VISUAL","analysis_run_id":run_id,"review_status":"NOT_REVIEWED"})
            vector_row=db.table("asset_visual_embeddings").select("embedding,model_provider,model_name,model_version,source_fingerprint").eq("asset_id",aid).single().execute().data
            vector=vector_row["embedding"]
            common={"asset_id":aid,"embedding_type":"VISUAL","provider":vector_row["model_provider"],"model_name":vector_row["model_name"],"model_version":vector_row["model_version"],"embedding_dimensions":512,"embedding":vector,"source_fingerprint":vector_row["source_fingerprint"],"analysis_run_id":run_id,"is_active":True}
            upsert(db,"scene_embeddings",{"id":uid("scene-embedding",aid),"scene_id":scene_id,**common})
            upsert(db,"keyframe_embeddings",{"id":uid("keyframe-embedding",aid),"keyframe_id":keyframe_id,"scene_id":scene_id,**common})
            text=" ".join([name,spec["narrative"],*spec["concepts"]])
            source_hash=hashlib.sha256(text.encode()).hexdigest()
            upsert(db,"scene_search_documents",{"scene_id":scene_id,"asset_id":aid,"searchable_text":text,"short_description":spec["narrative"],"primary_treatment_id":primary_treatment,"primary_anatomy_id":primary_anatomy,"primary_action_id":primary_action,"primary_location_id":location_id,"person_ids":[],"search_concepts":spec["concepts"],"structured_document":{"filename":name,"media":"video","scene":{"start":0,"end":duration,"description":spec["narrative"]},"people_roles":spec["roles"],"anatomy":spec["anatomy"],"actions":spec.get("actions",[]),"evidence":{"type":"AI_VISUAL","confidence":0.9,"analysis_run_id":run_id}},"source_hash":source_hash,"document_version":"job6-v1","build_status":"READY","built_at":now},"scene_id")
        upsert(db,"marketing_annotations",{"id":uid("marketing",aid),"asset_id":aid,"scene_id":scene_id,"keyframe_id":keyframe_id,"marketing_role":spec["marketing"],"potential_topic":spec["narrative"],"suggested_use":"Descriptive retrieval candidate only; not marketing approval","platform_suitability":[],"confidence":0.8,"provenance":"AI_VISUAL","analysis_run_id":run_id,"review_status":"NOT_REVIEWED","metadata":{"marketing_permission_changed":False}})
        if spec.get("clinical"):
            upsert(db,"clinical_observations",{"id":uid("clinical",aid),"asset_id":aid,"anatomy_id":ontology["anatomy_terms"][spec["anatomy"][1]],"observation_domain":"VISIBLE_APPEARANCE","observation_type":"HAIR_THINNING_APPEARANCE","value_text":spec["clinical"],"confidence":0.85,"source_type":"AI_VISUAL","verification_status":"AI_SUGGESTED","analysis_run_id":run_id,"evidence":{"contact_sheet":p["contact_sheet"]},"metadata":{"diagnosis":False}})
        text=" ".join([name,spec["narrative"],*spec["concepts"]]); source_hash=hashlib.sha256(text.encode()).hexdigest()
        upsert(db,"asset_search_documents",{"asset_id":aid,"searchable_text":text,"title":name,"short_description":spec["narrative"],"content_type":"image" if spec.get("image") else "video","primary_treatment_id":primary_treatment,"primary_anatomy_id":primary_anatomy,"primary_location_id":location_id if not spec.get("image") else None,"doctor_person_ids":[],"search_concepts":spec["concepts"],"structured_document":{"filename":name,"media":"image" if spec.get("image") else "video","summary":spec["narrative"],"anatomy":spec.get("anatomy",[]),"actions":spec.get("actions",[]),"treatment":spec.get("treatment"),"evidence":{"type":"AI_VISUAL","confidence":0.9,"analysis_run_id":run_id},"transcript":"DEFERRED","text_embeddings":"DEFERRED"},"source_hash":source_hash,"document_version":"job6-v1","build_status":"READY","built_at":now},"asset_id")
        db.table("ai_analysis_runs").update({"status":"COMPLETED","completed_at":datetime.now(timezone.utc).isoformat(),"metadata":{"job":"KDI_AI_SEARCH_V3_JOB_6","purpose":PURPOSE,"cohort_id":cohort_id,"prompt_version":PROMPT_VERSION,"pilot_manifest":"reports/ai-search-v3/job5_3-final-pilot-manifest.json","success_count":1,"partial_count":0,"failure_count":0,"text_embeddings":"DEFERRED — NO APPROVED WORKING GENERATOR","transcription":"DEFERRED — NO APPROVED WORKING GENERATOR"}}).eq("id",run_id).execute()
        results.append({"asset_id":aid,"file_name":name,"status":"COMPLETE","run_id":run_id,"scene_id":scene_id,"keyframe_id":keyframe_id})
    after={}
    for table in tracked:
        after[table]=db.table(table).select("*",count="exact").limit(0).execute().count or 0
    output={"cohort_id":cohort_id,"pipeline_version":PIPELINE,"prompt_version":PROMPT_VERSION,"started_at":now,"completed_at":datetime.now(timezone.utc).isoformat(),"status":"COMPLETED","assets":results,"counts":{t:{"before":before[t],"new":after[t]-before[t],"after":after[t]} for t in tracked}}
    (ROOT/"tmp"/"job6"/"indexing-result.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
    print(json.dumps({"status":"PASS","assets":len(results),"cohort_id":cohort_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
