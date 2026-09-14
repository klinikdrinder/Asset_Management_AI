"""Validate Phase 10 preparation and production preservation using SELECT only."""
from __future__ import annotations
import json,os
from pathlib import Path
import requests
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"reports/semantic-search/phase10";MANIFEST=json.loads((ROOT/"config/semantic-search/kdi_semantic_pilot_v1.json").read_text())
BASELINE={"assets":881,"visual_embeddings":875,"text_embeddings":20,"asset_ai_profiles":16,"asset_search_documents":10,"scene_search_documents":10,"asset_scenes":301,"keyframes":301,"production_transcript_chunks":0,"ocr_observations":0,"scene_narratives":16,"authorization_rows":881,"application_users":2,"source_files":890,"asset_sources":881,"asset_destinations":881}
def env():
    values={}
    for p in (ROOT/".env",ROOT/".env.local"):
        if p.exists():values.update({str(k).lstrip("\ufeff"):v for k,v in dotenv_values(p).items() if v})
    values.update(os.environ);return values
def counts(values):
    ref=values["NEXT_PUBLIC_SUPABASE_URL"].split("//",1)[1].split(".",1)[0];sql="""select jsonb_build_object('assets',(select count(*) from public.assets),'visual_embeddings',(select count(*) from public.asset_visual_embeddings),'text_embeddings',(select count(*) from public.asset_embeddings),'asset_ai_profiles',(select count(*) from public.asset_ai_profiles),'asset_search_documents',(select count(*) from public.asset_search_documents),'scene_search_documents',(select count(*) from public.scene_search_documents),'asset_scenes',(select count(*) from public.asset_scenes),'keyframes',(select count(*) from public.asset_keyframes),'production_transcript_chunks',(select count(*) from public.asset_transcript_chunks),'ocr_observations',(select count(*) from public.ocr_observations),'scene_narratives',(select count(*) from public.scene_narratives),'authorization_rows',(select count(*) from public.asset_access_control),'application_users',(select count(*) from auth.users),'source_files',(select count(*) from public.source_files),'asset_sources',(select count(*) from public.asset_sources),'asset_destinations',(select count(*) from public.asset_destinations)) counts""";r=requests.post(f"https://api.supabase.com/v1/projects/{ref}/database/query",headers={"Authorization":f"Bearer {values['SUPABASE_DASHBOARD_ACCESS_TOKEN']}"},json={"query":sql},timeout=60);r.raise_for_status();return r.json()[0]["counts"]
def main():
    packets=[json.loads((OUT/"review"/f"{a['asset_id']}_review_packet.json").read_text()) for a in MANIFEST["assets"]];after=counts(env());gold=list((OUT/"gold").glob("*_gold_standard.json")) if (OUT/"gold").exists() else []
    checks={"ten_packets":len(packets)==10,"layer_slots":sum(len(p["layer_decisions"]) for p in packets)==180,"no_fabricated_decisions":all(x["human_decision"] is None for p in packets for x in p["layer_decisions"]),"five_p1_unresolved":sum(len(p["critical_issue_decisions"]) for p in packets)==5 and all(x["human_decision"] is None for p in packets for x in p["critical_issue_decisions"]),"no_signed_off_assets":all(p["review_status"]=="AWAITING_HUMAN_REVIEW" and not p["explicit_signoff"] for p in packets),"no_gold_packages":not gold,"production_preserved":after==BASELINE}
    result={"phase":"PHASE_10","status":"AWAITING_HUMAN_REVIEW" if all(checks.values()) else "FAIL","checks":checks,"review_packets":10,"human_layer_decisions":{"required":180,"completed":0},"p1_resolutions":{"required":5,"completed":0},"assets_signed_off":0,"gold_packages":0,"gold_manifest":"NOT_CREATED","production_counts_before":BASELINE,"production_counts_after":after,"database_operations":{"select_queries":1,"writes":0,"migrations":0},"ready_for_phase11":False};(OUT/"phase10_validation.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result));return 0 if result["status"]=="AWAITING_HUMAN_REVIEW" else 1
if __name__=="__main__":raise SystemExit(main())
