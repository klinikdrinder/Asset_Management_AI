from __future__ import annotations
import json, os
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

R = Path(__file__).resolve().parents[1]
IDS = ['753eb5f3-82c7-4148-a226-d5b960fd8619', 'c86344e9-5b32-4d86-9205-67952d508651']

e = {}
for f in (R / '.env', R / '.env.local', R / 'dashboard/.env.local'):
    if f.exists(): e.update({k: v for k, v in dotenv_values(f).items() if v})
e.update(os.environ)
c = create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'], e['SUPABASE_SERVICE_ROLE_KEY'])

out = {}
for aid in IDS:
    scenes = c.table('asset_scenes').select('id,scene_index,start_seconds,end_seconds,short_description,literal_description,semantic_state,semantic_analysis_run_id').eq('asset_id', aid).eq('canonical_active', True).order('scene_index').execute().data or []
    rows = []
    for s in scenes:
        rows.append({**s,
            'keyframes': c.table('asset_keyframes').select('id,timestamp_seconds,visual_description,source_fingerprint').eq('scene_id', s['id']).order('timestamp_seconds').execute().data or [],
            'documents': c.table('search_document_builds').select('id,search_text,positive_concepts,status,active,stale,source_fingerprint').eq('scene_id', s['id']).eq('document_type', 'SCENE').eq('active', True).execute().data or [],
            'assertions': c.table('semantic_assertions').select('id,layer_id,canonical_concept_code,value_text,semantic_state,keyframe_id,active,source_fingerprint').eq('scene_id', s['id']).eq('active', True).execute().data or []})
    out[aid] = rows
print(json.dumps(out, indent=2))
