from __future__ import annotations
import json, os
from collections import Counter
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
R=Path(__file__).resolve().parents[1]; e={}
for f in (R/'.env',R/'.env.local',R/'dashboard/.env.local'):
    if f.exists(): e.update({k:v for k,v in dotenv_values(f).items() if v})
e.update(os.environ); c=create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'],e['SUPABASE_SERVICE_ROLE_KEY'])
ids=['babae120-9372-42ad-b535-02a3276ea2be','c86344e9-5b32-4d86-9205-67952d508651','753eb5f3-82c7-4148-a226-d5b960fd8619','47611c6d-7923-42a4-87b6-c2a416a90f5c']
rows=c.table('asset_transcript_chunks').select('id,asset_id,scene_id,start_seconds,end_seconds,transcript_text,normalized_text,search_status,provider,model,version,semantic_analysis_run_id,source_text_fingerprint,provenance').in_('asset_id',ids).order('asset_id').order('start_seconds').execute().data or []
counts=Counter((x['asset_id'],float(x['start_seconds'] or 0),float(x['end_seconds'] or 0)) for x in rows)
dups=[x for x in rows if counts[(x['asset_id'],float(x['start_seconds'] or 0),float(x['end_seconds'] or 0))]>1]
emb=c.table('semantic_embeddings').select('id,asset_id,scene_id,keyframe_id,event_id,transcript_chunk_id,ocr_observation_id,representation_type,active,stale').in_('asset_id',ids).eq('active',True).eq('stale',False).execute().data or []
print(json.dumps({'transcript_duplicates':dups,'embeddings':emb},indent=2))
