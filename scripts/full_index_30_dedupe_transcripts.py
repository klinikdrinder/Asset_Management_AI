"""Delete only exact FULL_INDEX_30 transcript duplicates of preserved earlier truth."""
from __future__ import annotations
import json, os
from collections import defaultdict
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
R=Path(__file__).resolve().parents[1]; e={}
for f in (R/'.env',R/'.env.local',R/'dashboard/.env.local'):
    if f.exists(): e.update({k:v for k,v in dotenv_values(f).items() if v})
e.update(os.environ); c=create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'],e['SUPABASE_SERVICE_ROLE_KEY'])
layers=c.table('asset_semantic_layers').select('asset_id,processing_status').eq('active',True).execute().data or []
per=defaultdict(lambda:[0,0])
for x in layers:
    per[x['asset_id']][0]+=1
    if x['processing_status']=='COMPLETE': per[x['asset_id']][1]+=1
cohort={k for k,v in per.items() if v==[18,18]}
if len(cohort)!=30: raise RuntimeError('COHORT_NOT_30')
rows=c.table('asset_transcript_chunks').select('id,asset_id,start_seconds,end_seconds,normalized_text,source_text_fingerprint,provenance').in_('asset_id',sorted(cohort)).execute().data or []
groups=defaultdict(list)
for x in rows:
    groups[(x['asset_id'],float(x['start_seconds'] or 0),float(x['end_seconds'] or 0),x.get('source_text_fingerprint'),x.get('normalized_text'))].append(x)
delete=[]
for group in groups.values():
    if len(group)<2: continue
    old=[x for x in group if (x.get('provenance') or {}).get('origin')!='FULL_INDEX_30']
    new=[x for x in group if (x.get('provenance') or {}).get('origin')=='FULL_INDEX_30']
    if old: delete.extend(new)
if any(x['asset_id'] not in cohort for x in delete): raise RuntimeError('OUTSIDE_COHORT_DELETE')
for x in delete: c.table('asset_transcript_chunks').delete().eq('id',x['id']).eq('asset_id',x['asset_id']).execute()
out=R/'reports/semantic-search/rollout/full-index-30/full_index_30_transcript_deduplication.json'
out.write_text(json.dumps({'status':'PASS','deleted_exact_redundant_rows':len(delete),'deleted_ids':[x['id'] for x in delete],'preserved_prior_truth':True,'outside_cohort':0},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','deleted':len(delete),'ids':[x['id'] for x in delete]}))
