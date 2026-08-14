from pathlib import Path
import base64,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from supabase import create_client
from visual_indexing.openclip_encoder import OpenClipEncoder,MODEL_PROVIDER,MODEL_NAME,MODEL_VERSION

ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parent
env={}
for p in (PROJECT/".env",PROJECT/".env.local",ROOT/".env.local"):env.update({k:v for k,v in dotenv_values(p).items() if v})
url=env.get("NEXT_PUBLIC_SUPABASE_URL") or env["SUPABASE_URL"];admin=create_client(url,env["SUPABASE_SERVICE_ROLE_KEY"])
link=admin.auth.admin.generate_link({"type":"magiclink","email":"kdimediaautomation@gmail.com"})
reader=create_client(url,env["NEXT_PUBLIC_SUPABASE_ANON_KEY"]);auth=reader.auth.verify_otp({"token_hash":link.properties.hashed_token,"type":"email"})
if not auth.session:raise SystemExit("restricted reader session unavailable")
queries=("doctor talking to patient","consultation inside clinic","scalp close up","hair before and after","doctor speaking to camera","procedure being performed","female patient consultation","patient sitting with doctor","clinic room","woman with long hair")
encoder=OpenClipEncoder();results=[]
for query in queries:
    rows=reader.rpc("hybrid_search_assets_v2",{"search_query":query,"visual_query_embedding":encoder.embed_text(query),"visual_provider":MODEL_PROVIDER,"visual_model":MODEL_NAME,"visual_version":MODEL_VERSION,"qwen_query_embedding":None,"qwen_provider":None,"qwen_model":None,"qwen_version":None,"filter_category":None,"filter_extension":None,"result_limit":5,"result_offset":0}).execute().data or []
    ids=[r["asset_id"] for r in rows];names={r["id"]:r["file_name"] for r in (reader.table("assets").select("id,file_name").in_("id",ids).execute().data or [])}
    results.append({"query":query,"relevance":"MANUAL RELEVANCE REVIEW REQUIRED","top_results":[{"rank":i,"asset_id":r["asset_id"],"filename":names.get(r["asset_id"],"[permission-filtered]"),"visual_score":r.get("visual_score"),"semantic_score":r.get("semantic_score"),"text_score":r.get("text_score"),"structured_score":r.get("structured_score"),"filename_score":r.get("filename_score"),"final_score":r.get("match_score")}for i,r in enumerate(rows,1)]})
report={"model":{"provider":MODEL_PROVIDER,"name":MODEL_NAME,"version":MODEL_VERSION,"dimensions":512},"queries_tested":len(results),"manual_review_required":True,"queries":results}
target=ROOT/"reports"/"visual-search-benchmark-2026-08-13.json";target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(report,indent=2),encoding="utf-8");print(json.dumps({"report":str(target),"queries_tested":len(results)},indent=2))
