"""Repair missing assertion/evidence lineage for three already-analyzed canonical scenes.

The scenes already have independent semantic runs, grounded descriptions, keyframes,
READY documents and vectors.  This script adds only the absent scene-level summary
assertion and same-scene keyframe evidence.  Scope is hard-coded and asserted.
"""
from __future__ import annotations
import json, os, uuid
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

R = Path(__file__).resolve().parents[1]
NS = uuid.UUID('2f5c8a71-6b3d-4e19-9f52-8c04a7d1be36')
TARGET_ASSETS = {
    '753eb5f3-82c7-4148-a226-d5b960fd8619',
    'c86344e9-5b32-4d86-9205-67952d508651',
}

def uid(seed: str) -> str: return str(uuid.uuid5(NS, seed))

e = {}
for f in (R / '.env', R / '.env.local', R / 'dashboard/.env.local'):
    if f.exists(): e.update({k: v for k, v in dotenv_values(f).items() if v})
e.update(os.environ)
c = create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'], e['SUPABASE_SERVICE_ROLE_KEY'])

layers = c.table('asset_semantic_layers').select('asset_id,processing_status').eq('active', True).execute().data or []
per = {}
for x in layers:
    v = per.setdefault(x['asset_id'], [0, 0]); v[0] += 1
    if x['processing_status'] == 'COMPLETE': v[1] += 1
cohort = {k for k, v in per.items() if v == [18, 18]}
if len(cohort) != 30 or not TARGET_ASSETS <= cohort:
    raise RuntimeError('WRITE_SCOPE_ASSERTION_FAILED')

repaired = []
for aid in sorted(TARGET_ASSETS):
    scenes = c.table('asset_scenes').select('id,scene_index,start_seconds,end_seconds,short_description,literal_description,semantic_analysis_run_id').eq('asset_id', aid).eq('canonical_active', True).order('scene_index').execute().data or []
    for s in scenes:
        existing = c.table('semantic_assertions').select('id').eq('scene_id', s['id']).eq('active', True).limit(1).execute().data or []
        if existing: continue
        kfs = c.table('asset_keyframes').select('id,timestamp_seconds,source_fingerprint').eq('scene_id', s['id']).order('timestamp_seconds').execute().data or []
        if not kfs: raise RuntimeError('MISSING_KEYFRAME:' + s['id'])
        kf = next((k for k in kfs if float(s['start_seconds']) <= float(k['timestamp_seconds']) <= float(s['end_seconds'])), None)
        if not kf: raise RuntimeError('KEYFRAME_OUTSIDE_SCENE:' + s['id'])
        desc = (s.get('literal_description') or s.get('short_description') or '').strip()
        if not desc: raise RuntimeError('MISSING_GROUNDED_DESCRIPTION:' + s['id'])
        run_id = s.get('semantic_analysis_run_id')
        if not run_id: raise RuntimeError('MISSING_ANALYSIS_RUN:' + s['id'])
        asid = uid(f'fullindex30:lineage:{s["id"]}:MEDIA_SUMMARY')
        row = {'id': asid, 'asset_id': aid, 'scene_id': s['id'], 'keyframe_id': kf['id'],
            'layer_id': 'GLOBAL_ASSET_UNDERSTANDING', 'subject_type': 'SCENE',
            'predicate': 'MEDIA_SUMMARY', 'canonical_concept_code': 'MEDIA_SUMMARY',
            'canonical_concept_type': 'SEMANTIC_CONCEPT', 'value_text': desc,
            'semantic_state': 'OBSERVED', 'confidence': 0.92, 'confidence_source': 'HIGH',
            'search_critical': False, 'analysis_run_id': run_id, 'origin': 'AI_MODEL',
            'ontology_version': 'KDI_SEMANTIC_V2', 'semantic_spec_version': 'semantic_index_v1',
            'human_review_status': 'PENDING', 'active': True,
            'source_fingerprint': kf['source_fingerprint'],
            'idempotency_key': f'fullindex30:lineage:{s["id"]}:MEDIA_SUMMARY'}
        c.table('semantic_assertions').upsert(row, on_conflict='id').execute()
        have = c.table('semantic_assertion_evidence').select('id').eq('assertion_id', asid).limit(1).execute().data or []
        if not have:
            ts = float(kf['timestamp_seconds'])
            c.table('semantic_assertion_evidence').insert({'assertion_id': asid,
                'evidence_type': 'KEYFRAME_LEVEL', 'polarity': 'POSITIVE', 'completeness': 'COMPLETE',
                'asset_id': aid, 'scene_id': s['id'], 'keyframe_id': kf['id'],
                'start_time': ts, 'end_time': ts, 'evidence_score': 0.92,
                'source_fingerprint': kf['source_fingerprint'], 'analysis_run_id': run_id}).execute()
        repaired.append({'asset_id': aid, 'scene_id': s['id'], 'scene_index': s['scene_index'],
                         'assertion_id': asid, 'keyframe_id': kf['id']})

out = R / 'reports/semantic-search/rollout/full-index-30/full_index_30_scene_lineage_repair.json'
out.write_text(json.dumps({'status': 'PASS', 'scope_assets': sorted(TARGET_ASSETS),
                           'repaired': repaired, 'count': len(repaired)}, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': 'PASS', 'repaired': len(repaired), 'rows': repaired}))
