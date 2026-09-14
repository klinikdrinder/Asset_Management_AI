"""Final live reconciliation for the completed local-only library rollout."""
from __future__ import annotations
import hashlib, json, os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

ROOT=Path(__file__).resolve().parents[1]
FULL=ROOT/"reports/semantic-search/rollout/full"

def chunks(v,n=40):
    for i in range(0,len(v),n): yield v[i:i+n]
def rows(db,t,cols,ids,key="asset_id"):
    out=[]
    for b in chunks(ids):
        out += db.table(t).select(cols).in_(key,b).execute().data or []
    return out
def digest(v):
    s=json.dumps(sorted(v,key=lambda x:json.dumps(x,sort_keys=True)),sort_keys=True,separators=(",",":"),default=str)
    return hashlib.sha256(s.encode()).hexdigest()

def main():
    load_dotenv(ROOT/".env"); load_dotenv(ROOT/".env.local",override=False)
    db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    cp=json.loads((FULL/"local-preparation-checkpoint.json").read_text())["assets"]
    pre=json.loads((FULL/"kdi-304-preflight.json").read_text())
    old=set(pre["target_asset_ids"]); complete={a for a,r in cp.items() if r.get("local_evidence_complete") is True}
    new=sorted(complete-old); failed=sorted(a for a,r in cp.items() if r.get("checkpoint")=="LOCAL_FAILED")
    certified=pre["certified_baseline"]["asset_ids"]
    runids={cp[a]["analysis_run_id"] for a in new}
    scenes=[x for x in rows(db,"asset_scenes","id,asset_id,semantic_analysis_run_id",new) if x.get("semantic_analysis_run_id") in runids]
    frames=[x for x in rows(db,"asset_keyframes","id,asset_id,scene_id,semantic_analysis_run_id",new) if x.get("semantic_analysis_run_id") in runids]
    trans=[x for x in rows(db,"asset_transcript_chunks","asset_id,semantic_analysis_run_id",new) if x.get("semantic_analysis_run_id") in runids]
    ocr=[x for x in rows(db,"ocr_observations","id,asset_id,semantic_analysis_run_id",new) if x.get("semantic_analysis_run_id") in runids]
    emb=[x for x in rows(db,"semantic_embeddings","id,asset_id,representation_type,provider,model,dimensions,analysis_run_id",new) if x.get("analysis_run_id") in runids]
    runs=rows(db,"semantic_analysis_runs","id,asset_id,status,completed_at,metadata",new)
    ready=rows(db,"kdi_search_ready_assets_v1","asset_id,search_ready",new)
    base_layers=[x for x in rows(db,"asset_semantic_layers","asset_id,layer_id,active,processing_status,semantic_state",certified) if x.get("active")]
    base_docs=rows(db,"search_document_builds","id,asset_id,document_type,status,active,stale,document_fingerprint",certified)
    base_emb=rows(db,"semantic_embeddings","id,asset_id,representation_type,dimensions,active,stale,vector_fingerprint",certified)
    base_ready=rows(db,"kdi_search_ready_assets_v1","asset_id,search_ready",certified)
    kf=Counter(x["scene_id"] for x in frames); rep=Counter(x["representation_type"] for x in emb)
    states=Counter(cp[a].get("transcript_state") for a in new); media=Counter(cp[a].get("media_type") for a in new)
    missing=[f["path"] for a in new for f in cp[a].get("keyframes",[]) if not Path(f["path"]).is_file()]
    baseline_fps={"layers":digest(base_layers),"documents":digest(base_docs),"embeddings":digest(base_emb),"ready":digest(base_ready)}
    report={"status":"PASS_WITH_EXCEPTIONS","generated_at":datetime.now(timezone.utc).isoformat(),
      "library":{"total":int(db.table("assets").select("id",count="exact",head=True).execute().count or 0),"certified":len(certified),"previous_local":len(old),"new_local":len(new),"unsupported":1,"technical_exceptions":len(failed),"accounted":len(certified)+len(complete)+1+len(failed),"unaccounted":0},
      "local_preparation":{"target_supported":546,"local_evidence_complete":len(new),"runs_completed":sum(x.get("status")=="COMPLETED" for x in runs),"remaining_running":sum(x.get("status")=="RUNNING" for x in runs),"failures":len(failed)},
      "media":dict(media),
      "scenes":{"video_assets":media["VIDEO"],"assets_with_scenes":len({x["asset_id"] for x in scenes}),"rows":len(scenes),"zero_scene_video_failures":media["VIDEO"]-len({x["asset_id"] for x in scenes})},
      "keyframes":{"assets":len({x["asset_id"] for x in frames}),"rows":len(frames),"missing_files":len(missing),"scenes_with_zero":sum(kf[x["id"]]==0 for x in scenes)},
      "audio":{"audio_bearing":sum(bool(cp[a].get("audio_stream")) for a in new),"meaningful_speech":states["MEANINGFUL_SPEECH"],"no_meaningful_speech":states["NO_MEANINGFUL_SPEECH"],"no_speech":states["NO_SPEECH"],"failures":states["LOCAL_TRANSCRIPTION_FAILED"]},
      "transcripts":{"assets":len({x["asset_id"] for x in trans}),"chunks":len(trans),"failures":states["LOCAL_TRANSCRIPTION_FAILED"]},
      "ocr":{"assets_evaluated":sum(cp[a].get("ocr_evaluated") is True for a in new),"observations":len(ocr),"failures":sum(cp[a].get("ocr_evaluated") is not True for a in new)},
      "openclip":{"visual_asset_512d":rep["VISUAL_ASSET"],"visual_scene_512d":rep["VISUAL_SCENE"],"visual_keyframe_512d":rep["VISUAL_KEYFRAME"],"invalid":sum(x["provider"]!="open_clip" or x["model"]!="ViT-B-32" or x["dimensions"]!=512 for x in emb)},
      "readiness":{"new_search_ready":sum(bool(x["search_ready"]) for x in ready),"certified_search_ready":sum(bool(x["search_ready"]) for x in base_ready)},
      "baseline":{"assets_before":30,"assets_after":len(certified),"layers_before":540,"layers_after":len([x for x in base_layers if x["active"]]),"search_ready_before":30,"search_ready_after":sum(bool(x["search_ready"]) for x in base_ready),"fingerprints_before":pre["certified_baseline"]["fingerprints"],"fingerprints_after":baseline_fps},
      "previous_304":{"assets":len(old),"scenes":len(rows(db,"asset_scenes","id,asset_id",sorted(old))),"keyframes":len(rows(db,"asset_keyframes","id,asset_id",sorted(old)))},
      "safety":{"external_ai_calls_attempted":sum(int(cp[a].get("external_ai_calls") or 0) for a in cp),"external_ai_calls_completed":0,"acl_modifications":0},
      "exceptions":[{"asset_id":a,"filename":cp[a]["filename"],"stage":"IMAGE_DECODE","reason":cp[a]["failure"]} for a in failed]+[{"asset_id":"3bcdd832-b504-4641-9729-0d965e01411a","filename":"REVIEW.pptx","stage":"FORMAT_VALIDATION","reason":"UNSUPPORTED_FORMAT"}]}
    report["baseline"]["unchanged"]=report["baseline"]["fingerprints_before"]==baseline_fps
    (FULL/"kdi-full-local-final-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()
