"""Run the controlled 20-query Job 7 OpenCLIP/pgvector benchmark."""
from __future__ import annotations
import json,os,time
import re
from pathlib import Path
import requests
from dotenv import dotenv_values
from dashboard.visual_indexing.openclip_encoder import OpenClipEncoder

ROOT=Path(__file__).resolve().parents[1]
QUERIES=[
"close-up scalp","person sitting in consultation room","two people talking in clinic","hairline close-up",
"consultation footage","clinician pointing at hairline","video with frontal scalp","clinic B-roll",
"close-up video of a clinician examining the scalp","consultation with two people and hairline discussion context",
"social-media-friendly clinic footage","hair treatment procedure footage","FUE implantation recipient scalp",
"facial injection close-up","neck injection procedure","front-facing portrait","clinician using device on scalp",
"outdoor walking footage","dental surgery","car driving on highway"]

def filters_for(q):
    f={}
    if re.search(r'\b(video|videos|footage|clip|clips)\b',q,re.I): f['media_type']='video'
    if re.search(r'close[- ]?up',q,re.I): f['shot_type']='CLOSEUP'
    if re.search(r'frontal scalp',q,re.I): f['anatomy']='FRONTAL_SCALP'
    elif re.search(r'hairline',q,re.I): f['anatomy']='FRONTAL_HAIRLINE'
    elif re.search(r'scalp',q,re.I): f['anatomy']='SCALP'
    elif re.search(r'neck',q,re.I): f['anatomy']='NECK'
    if re.search(r'clinician|doctor',q,re.I): f['role']='CLINICIAN_LIKE'
    if re.search(r'examin',q,re.I): f['action']='EXAMINING'
    elif re.search(r'point',q,re.I): f['action']='POINTING'
    elif re.search(r'inject',q,re.I): f['action']='INJECTING'
    elif re.search(r'implant',q,re.I): f['action']='IMPLANTING_GRAFTS'
    if re.search(r'FUE implantation',q,re.I): f['treatment']='FUE_IMPLANTATION'
    return f

def main():
    raw={**dotenv_values(ROOT/'.env'),**dotenv_values(ROOT/'.env.local'),**os.environ}
    env={str(k).lstrip('\ufeff'):v for k,v in raw.items()}
    ref=str(env['NEXT_PUBLIC_SUPABASE_URL']).split('//')[1].split('.')[0]
    url=f'https://api.supabase.com/v1/projects/{ref}/database/query'; headers={'Authorization':f"Bearer {env['SUPABASE_DASHBOARD_ACCESS_TOKEN']}"}
    encoder=OpenClipEncoder(); rows=[]
    for query in QUERIES:
        t=time.perf_counter(); vector=encoder.embed_text(query); embed_ms=(time.perf_counter()-t)*1000
        literal='['+','.join(f'{v:.9g}' for v in vector)+']'
        escaped=query.replace("'","''")
        filters=filters_for(query); filters_sql=json.dumps(filters).replace("'","''")
        sql=f"""begin; select set_config('request.jwt.claims','{{\"sub\":\"3938c364-0250-40a1-8db6-9ef704ca0122\",\"iss\":\"https://wcqqjpndlwsvatjuqnol.supabase.co/auth/v1\",\"role\":\"authenticated\"}}',true); set local role authenticated; select asset_id,match_score,visual_asset_score,visual_scene_score,visual_keyframe_score,lexical_asset_score,lexical_scene_score,structured_score,filename_score,match_reason from public.hybrid_search_assets_v3('{escaped}','{literal}'::public.vector(512),'{filters_sql}'::jsonb,'{{}}',5,0,0.08); rollback;"""
        t=time.perf_counter(); response=requests.post(url,headers=headers,json={'query':sql},timeout=30); response.raise_for_status(); data=response.json(); db_ms=(time.perf_counter()-t)*1000
        if isinstance(data,dict): data=[data]
        if data and all(set(row)=={'set_config'} for row in data): data=[]
        if any('asset_id' not in row for row in data): raise RuntimeError({'query':query,'response':data})
        rows.append({'query':query,'interpreted_filters':filters,'returned_assets':[r['asset_id'] for r in data],'scores':[r['match_score'] for r in data],'result_count':len(data),'embedding_ms':round(embed_ms,2),'database_and_ranking_ms':round(db_ms,2),'total_ms':round(embed_ms+db_ms,2),'false_positives':None,'false_negatives':None,'notes':'Manual ground truth is recorded only where supported; no fabricated labels.'})
    out={'model':'OpenCLIP ViT-B-32 / laion2b_s34b_b79k','dimensions':512,'queries':rows,'performance':{'embedding_ms_median':sorted(r['embedding_ms'] for r in rows)[len(rows)//2],'database_and_ranking_ms_median':sorted(r['database_and_ranking_ms'] for r in rows)[len(rows)//2],'total_ms_median':sorted(r['total_ms'] for r in rows)[len(rows)//2]}}
    path=ROOT/'tmp/job7-benchmark.json'; path.write_text(json.dumps(out,indent=2),encoding='utf-8'); print(json.dumps({'status':'PASS','queries':len(rows),**out['performance']}))
if __name__=='__main__': main()
