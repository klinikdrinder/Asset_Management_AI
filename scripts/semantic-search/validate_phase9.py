"""Validate Phase 9 artifacts and production preservation using SELECT only."""
from __future__ import annotations
import json, os
from pathlib import Path
import requests
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"reports/semantic-search/phase9";MANIFEST=json.loads((ROOT/"config/semantic-search/kdi_semantic_pilot_v1.json").read_text());SPEC_FP="ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"
def env():
    values={}
    for path in (ROOT/".env",ROOT/".env.local"):
        if path.exists():values.update({str(k).lstrip("\ufeff"):v for k,v in dotenv_values(path).items() if v})
    values.update(os.environ);return values
def counts(values):
    ref=values["NEXT_PUBLIC_SUPABASE_URL"].split("//",1)[1].split(".",1)[0]
    sql="""select jsonb_build_object('assets',(select count(*) from public.assets),'visual_embeddings',(select count(*) from public.asset_visual_embeddings),'text_embeddings',(select count(*) from public.asset_embeddings),'asset_ai_profiles',(select count(*) from public.asset_ai_profiles),'asset_search_documents',(select count(*) from public.asset_search_documents),'scene_search_documents',(select count(*) from public.scene_search_documents),'asset_scenes',(select count(*) from public.asset_scenes),'keyframes',(select count(*) from public.asset_keyframes),'production_transcript_chunks',(select count(*) from public.asset_transcript_chunks),'ocr_observations',(select count(*) from public.ocr_observations),'scene_narratives',(select count(*) from public.scene_narratives),'authorization_rows',(select count(*) from public.asset_access_control),'application_users',(select count(*) from auth.users),'source_files',(select count(*) from public.source_files),'asset_sources',(select count(*) from public.asset_sources),'asset_destinations',(select count(*) from public.asset_destinations)) counts"""
    response=requests.post(f"https://api.supabase.com/v1/projects/{ref}/database/query",headers={"Authorization":f"Bearer {values['SUPABASE_DASHBOARD_ACCESS_TOKEN']}"},json={"query":sql},timeout=60);response.raise_for_status();return response.json()[0]["counts"]
def main():
    before=counts(env());packages=[json.loads((OUT/f"{a['asset_id']}_consistency_validation.json").read_text()) for a in MANIFEST["assets"]];after=counts(env());rules=[r for p in packages for r in p["rule_results"]];issues=[i for p in packages for i in p["issues"]]
    checks={"specification_fingerprint":all(p["semantic_spec_fingerprint"]==SPEC_FP for p in packages),"exact_assets":len(packages)==10,"source_fingerprints":all(p["source_fingerprint"]==a["content_fingerprint"]["value"] for p,a in zip(packages,MANIFEST["assets"])),"rule_coverage":len(rules)==200 and all(len(p["rule_results"])==20 for p in packages),"identity_integrity":all(next(r for r in p["rule_results"] if r["rule_id"]=="IDENTITY_PROVENANCE")["state"]=="PASS" for p in packages),"no_p0":not any(i["priority"]=="P0" for i in issues),"img1238_review":next(p for p in packages if p["filename"]=="IMG_1238.MP4")["overall_consistency_state"]=="REVIEW_REQUIRED","image_conflicts":all(next(p for p in packages if p["filename"]==name)["overall_consistency_state"]=="CONFLICT" for name in ("DSC03753.JPG","DSC08097.JPG")),"no_forbidden_operations":all(not any(p["prohibitions"].values()) for p in packages),"production_preserved":before==after}
    validation={"status":"PASS" if all(checks.values()) else "FAIL","checks":checks,"assets":len(packages),"rule_evaluations":len(rules),"result_states":{state:sum(p["overall_consistency_state"]==state for p in packages) for state in ("PASS","PASS_WITH_UNCERTAINTY","INCOMPLETE","CONFLICT","REVIEW_REQUIRED","NOT_APPLICABLE")},"issue_severity":{level:sum(i["priority"]==level for i in issues) for level in ("P0","P1","P2","P3")},"production_counts_before":before,"production_counts_after":after,"database_operations":{"select_queries":2,"migrations":0,"writes":0}}
    (OUT/"phase9_validation.json").write_text(json.dumps(validation,indent=2)+"\n");print(json.dumps(validation));return 0 if validation["status"]=="PASS" else 1
if __name__=="__main__":raise SystemExit(main())
