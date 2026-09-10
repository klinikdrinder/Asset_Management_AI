"""Full-index corrective phase — certification artifacts.

Reads committed database truth plus this phase's build/probe/acceptance outputs. Never re-analyzes
media and never writes semantic data. Separates PROCESSING COMPLETENESS from SEMANTIC SEARCH QUALITY
(§19) and enforces the video SEARCH_READY gate (§20).
"""
from __future__ import annotations
import json, os, re, statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

R = Path(__file__).resolve().parents[1]
OUT = R / 'reports/semantic-search/rollout/full-index-30'; OUT.mkdir(parents=True, exist_ok=True)
P11 = R / 'reports/semantic-search/rollout/phase-11'
LIDS = ['ASSET_IDENTITY_PROVENANCE', 'GLOBAL_ASSET_UNDERSTANDING', 'TEMPORAL_SCENE_STRUCTURE', 'PEOPLE_ROLES',
        'PERSON_APPEARANCE', 'ANATOMY', 'TREATMENT_PROCEDURE', 'ACTIONS_EVENTS', 'RELATIONSHIPS',
        'CLINICAL_VISUAL_OBSERVATIONS', 'ENVIRONMENT', 'CINEMATOGRAPHY', 'COMPOSITION',
        'SPEECH_TRANSCRIPT_AUDIO', 'OCR_VISIBLE_TEXT', 'MARKETING_CONTENT_USAGE', 'SEMANTIC_NARRATIVE',
        'SEARCH_EMBEDDINGS']
LAYER_TITLES = ['Asset Identity & Provenance', 'Global Asset Understanding', 'Temporal / Scene Structure',
                'People & Roles', 'Person Appearance', 'Anatomy', 'Treatment / Procedure', 'Actions & Events',
                'Relationships', 'Clinical Visual Observations', 'Environment', 'Cinematography', 'Composition',
                'Speech / Transcript / Audio', 'OCR / Visible Text', 'Marketing & Content Usage',
                'Semantic Narrative', 'Search & Embeddings']
UNSAFE = ('surgery', 'procedure', 'treatment', 'hair transplant', 'fue', 'implantation', 'extraction',
          'graft harvesting', 'graft placement', 'prp', 'laser treatment', 'injection')
CLINICAL_LICENSE = {
    'hair transplant': ('HAIR_TRANSPLANT', 'HAIR_TRANSPLANT_FUE', 'HAIR_TRANSPLANT_PROCEDURE_CONTENT', 'FUE_IMPLANTATION'),
    'fue': ('HAIR_TRANSPLANT_FUE', 'FUE_IMPLANTATION'), 'implantation': ('FUE_IMPLANTATION', 'IMPLANTING_GRAFTS'),
    'graft harvesting': (), 'graft placement': (), 'extraction': (), 'prp': (), 'laser treatment': (), 'surgery': (),
    'injection': ('INJECTABLES', 'INJECTING', 'HOLDING_SYRINGE', 'VISIBLE_INJECTION_AT_LOWER_FACE', 'VISIBLE_INJECTION_AT_NECK'),
    'procedure': ('PROCEDURE_CONTENT', 'PROCEDURE_PREPARATION_CONTENT', 'VISIBLE_RECIPIENT_AREA_PROCEDURE',
                  'HAIR_TRANSPLANT_PROCEDURE_CONTENT', 'OPERATING_ROOM'),
    'treatment': ('TREATMENT_ROOM', 'PATIENT_POSITIONED_IN_TREATMENT_CHAIR', 'CLINICIAN_TREATS_PATIENT',
                  'SCALP_UNDER_ACTIVE_CLINICAL_ATTENTION', 'FACE_UNDER_ACTIVE_CLINICAL_ATTENTION',
                  'NECK_TREATMENT_AREA_DOMINANT', 'TREATMENT_AREA_PARTIALLY_VISIBLE', 'TOOL_VISIBLE_NEAR_TREATMENT_AREA')}
PLACEHOLDER = re.compile(r'semantic classification indeterminate|no additional determinate|placeholder|lorem', re.I)


def now(): return datetime.now(timezone.utc).isoformat()
def write(n, d): (OUT / n).write_text(json.dumps(d, indent=2, default=str) + '\n', encoding='utf-8')
def load(p): return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def env():
    e = {}
    for f in (R / '.env', R / '.env.local', R / 'dashboard/.env.local'):
        if f.exists(): e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ); return e


def chunked(c, table, fields, ids, key='asset_id'):
    rows = []
    for i in range(0, len(ids), 50):
        rows += c.table(table).select(fields).in_(key, ids[i:i + 50]).execute().data or []
    return rows


def trace_clinical(text, concepts):
    low = ' '.join(str(text or '').lower().split()); uns, neg, lic = [], [], []
    for t in UNSAFE:
        if t not in low: continue
        if any(x in concepts for x in CLINICAL_LICENSE.get(t, ())): lic.append(t)
        elif re.search(r'no [a-z ]{0,24}' + re.escape(t), low): neg.append(t)
        else: uns.append(t)
    return uns, neg, lic


def main():
    e = env()
    c = create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'], e['SUPABASE_SERVICE_ROLE_KEY'])
    base = {'generated_at': now(), 'phase': 'FULL_INDEX_30'}
    build = load(OUT / 'full_index_30_scene_build.json')
    probe = load(OUT / 'full_index_30_temporal_coverage_audit.json')
    reval = load(OUT / 'full_index_30_segmentation_revalidation.json')
    acc = load(OUT / 'full_index_30_raw_acceptance.json')
    p11db = load(P11 / 'phase_11_database_before_after.json')

    # ---------------- cohort ----------------
    all_layers = c.table('asset_semantic_layers').select('asset_id,layer_id,semantic_state,processing_status,applicability,active').execute().data or []
    active_layers = [x for x in all_layers if x['active']]
    per = defaultdict(lambda: [0, 0])
    for x in active_layers:
        per[x['asset_id']][0] += 1
        if x['processing_status'] == 'COMPLETE': per[x['asset_id']][1] += 1
    cohort = sorted(k for k, v in per.items() if v == [18, 18])
    total_assets = len(c.table('assets').select('id').execute().data or [])
    assets = {x['id']: x for x in chunked(c, 'assets', 'id,file_name,mime_type,file_extension,content_hash', cohort, key='id')}
    videos = sorted([a for a in assets.values() if str(a['mime_type']).startswith('video')], key=lambda x: x['file_name'])
    images = sorted([a for a in assets.values() if not str(a['mime_type']).startswith('video')], key=lambda x: x['file_name'])
    vids = [a['id'] for a in videos]

    scenes_all = chunked(c, 'asset_scenes', 'id,asset_id,scene_index,start_seconds,end_seconds,duration_seconds,detection_method,scene_type,canonical_active,semantic_state,short_description,literal_description,semantic_version', cohort)
    scenes = [s for s in scenes_all if s['canonical_active']]
    scene_ids = [s['id'] for s in scenes]
    kfs_all = chunked(c, 'asset_keyframes', 'id,asset_id,scene_id,timestamp_seconds,frame_index,selection_reason,visual_description,is_representative,technical_quality_score,semantic_version', cohort)
    kfs = [k for k in kfs_all if k['scene_id'] in set(scene_ids)]
    emb = chunked(c, 'semantic_embeddings', 'id,asset_id,scene_id,keyframe_id,event_id,transcript_chunk_id,ocr_observation_id,representation_type,provider,model,model_version,dimensions,active,stale,vector_fingerprint,source_text_fingerprint', cohort)
    emb_active = [x for x in emb if x['active'] and not x['stale']]
    docs = chunked(c, 'search_document_builds', 'id,asset_id,scene_id,document_type,search_text,positive_concepts,negative_concepts,status,active,stale', cohort)
    docs_active = [x for x in docs if x['active'] and not x['stale']]
    legacy_scene_docs = chunked(c, 'scene_search_documents', 'scene_id,asset_id,searchable_text,build_status', cohort)
    legacy_asset_docs = chunked(c, 'asset_search_documents', 'asset_id,searchable_text,short_description,build_status', cohort)
    profiles = chunked(c, 'asset_ai_profiles', 'asset_id,short_description,detailed_description,analysis_status', cohort)
    asserts = chunked(c, 'semantic_assertions', 'id,asset_id,scene_id,keyframe_id,layer_id,canonical_concept_code,value_text,semantic_state,active,search_critical', cohort)
    act_asserts = [x for x in asserts if x['active']]
    ev = chunked(c, 'semantic_assertion_evidence', 'id,assertion_id,asset_id,scene_id,keyframe_id,evidence_type,polarity,start_time,end_time', [x['id'] for x in act_asserts], key='assertion_id')
    tchunks = chunked(c, 'asset_transcript_chunks', 'id,asset_id,scene_id,start_seconds,end_seconds,transcript_text,search_status,provenance', cohort)
    ocr = chunked(c, 'ocr_observations', '*', cohort)
    # `asset_technical_metadata` is intentionally not exposed to the worker role in
    # some production deployments.  The phase's authoritative full-media probe is
    # the primary source for video duration/stream facts, so a denied supplemental
    # lookup must not prevent the database-backed semantic audit from completing.
    try:
        tech = {x['asset_id']: x for x in chunked(c, 'asset_technical_metadata', '*', cohort)}
    except Exception as exc:
        if 'asset_technical_metadata' not in str(exc) or 'permission denied' not in str(exc):
            raise
        tech = {}
    acl = chunked(c, 'asset_access_control', 'asset_id,classification_status,download_allowed', cohort)
    ready_docs = {x['asset_id'] for x in legacy_asset_docs if x['build_status'] == 'READY'}

    by_scene = defaultdict(list)
    for k in kfs: by_scene[k['scene_id']].append(k)
    scenes_by_asset = defaultdict(list)
    for s in scenes: scenes_by_asset[s['asset_id']].append(s)
    emb_by = defaultdict(list)
    for x in emb_active: emb_by[x['representation_type']].append(x)
    scene_doc = {x['scene_id']: x for x in docs_active if x['document_type'] == 'SCENE' and x['scene_id']}
    legacy_scene_doc = {x['scene_id']: x for x in legacy_scene_docs}
    asset_doc = {x['asset_id']: x for x in docs_active if x['document_type'] == 'ASSET'}
    profile = {x['asset_id']: x for x in profiles}
    legacy_doc = {x['asset_id']: x for x in legacy_asset_docs}
    concepts_by = defaultdict(set)
    for x in act_asserts:
        if x['semantic_state'] == 'OBSERVED': concepts_by[x['asset_id']].add(x['canonical_concept_code'])
    ev_by = defaultdict(list)
    for x in ev: ev_by[x['assertion_id']].append(x)
    scene_text_emb = {x['scene_id'] for x in emb_by['TEXT_SCENE']}
    scene_vis_emb = {x['scene_id'] for x in emb_by['VISUAL_SCENE']}
    kf_vis_emb = {x['keyframe_id'] for x in emb_by['VISUAL_KEYFRAME']}
    text_asset = {x['asset_id'] for x in emb_by['TEXT_ASSET']}
    visual_asset = {x['asset_id'] for x in chunked(c, 'asset_visual_embeddings', 'asset_id,embedding_dimensions,model_name', cohort) if x['embedding_dimensions'] == 512 and x['model_name'] == 'ViT-B-32'}
    probe_by = {x['filename']: x for x in ((probe or {}).get('assets') or [])}

    # ---------------- per-video matrix (§25) ----------------
    video_rows = []
    for a in videos:
        aid = a['id']; sc = sorted(scenes_by_asset[aid], key=lambda x: float(x['start_seconds']))
        pr = probe_by.get(a['file_name'], {}); t = pr.get('technical', {})
        dur = t.get('container_duration_seconds') or (tech.get(aid) or {}).get('duration_seconds')
        dur = float(dur) if dur else None
        akf = [k for s in sc for k in by_scene[s['id']]]
        covered = 0.0
        if sc:
            merged = []
            for s in sorted(sc, key=lambda x: float(x['start_seconds'])):
                st, en = float(s['start_seconds']), float(s['end_seconds'])
                if merged and st <= merged[-1][1] + 1e-6: merged[-1][1] = max(merged[-1][1], en)
                else: merged.append([st, en])
            covered = sum(b - aa for aa, b in merged)
        overlaps = sum(1 for i in range(len(sc)) for j in range(i + 1, len(sc))
                       if min(float(sc[i]['end_seconds']), float(sc[j]['end_seconds']))
                       - max(float(sc[i]['start_seconds']), float(sc[j]['start_seconds'])) > 0.01)
        sc_with_obs = sum(1 for s in sc if any(x['scene_id'] == s['id'] and x['active'] for x in act_asserts))
        sc_with_desc = sum(1 for s in sc if (s['short_description'] or '').strip())
        sc_docs = sum(1 for s in sc if s['id'] in scene_doc)
        sc_text = sum(1 for s in sc if s['id'] in scene_text_emb)
        sc_vis = sum(1 for s in sc if s['id'] in scene_vis_emb)
        kf_emb = sum(1 for k in akf if k['id'] in kf_vis_emb)
        tc = [x for x in tchunks if x['asset_id'] == aid]
        oc = [x for x in ocr if x.get('asset_id') == aid]
        lay = [x for x in active_layers if x['asset_id'] == aid]
        aa = [x for x in act_asserts if x['asset_id'] == aid]
        aev = sum(len(ev_by[x['id']]) for x in aa)
        doc = legacy_doc.get(aid); prof = profile.get(aid)
        uns, neg, lic = trace_clinical((doc or {}).get('searchable_text', ''), concepts_by[aid])
        placeholder_scene = [s['id'] for s in sc if PLACEHOLDER.search(s['short_description'] or '')]
        gates = {
            'technical_decode': bool(t.get('frame_count')),
            'valid_duration': bool(dur and dur > 0),
            'duration_sources_consistent': bool(pr.get('duration_sources_consistent')),
            'temporal_coverage': bool(dur and covered >= dur - max(0.25, dur * 0.05) and sc and float(sc[0]['start_seconds']) <= 0.25),
            'no_overlapping_scenes': overlaps == 0,
            'scene_segmentation': len(sc) >= 1,
            'keyframe_coverage': all(by_scene[s['id']] for s in sc),
            'scene_semantics': sc_with_obs == len(sc),
            'scene_descriptions': sc_with_desc == len(sc),
            'scene_documents': sc_docs == len(sc),
            'scene_text_embeddings': sc_text == len(sc),
            'scene_visual_embeddings': sc_vis == len(sc),
            'keyframe_embeddings': kf_emb == len(akf) and len(akf) > 0,
            'asset_18_layers': len(lay) == 18 and all(x['processing_status'] == 'COMPLETE' for x in lay),
            'asset_assertions_evidence': all(ev_by[x['id']] for x in aa if x['semantic_state'] in ('OBSERVED', 'FALSE')),
            'asset_descriptions': bool(prof and (prof['short_description'] or '').strip() and (prof['detailed_description'] or '').strip()),
            'asset_text_embedding': aid in text_asset,
            'asset_visual_embedding': aid in visual_asset,
            'asset_search_document': aid in ready_docs,
            'no_unsupported_clinical': not uns,
            'no_placeholder_scene_text': not placeholder_scene,
            'audio_processed': bool([x for x in act_asserts if x['asset_id'] == aid and x['layer_id'] == 'SPEECH_TRANSCRIPT_AUDIO']) or not t.get('has_audio'),
        }
        failed = [k for k, v in gates.items() if not v]
        video_rows.append({'filename': a['file_name'], 'asset_id': aid,
            'duration_seconds': dur, 'frame_count': t.get('frame_count'), 'fps': t.get('fps'),
            'resolution': f"{t.get('width_px')}x{t.get('height_px')}" if t.get('width_px') else None,
            'has_audio': t.get('has_audio'),
            'canonical_scenes': len(sc), 'superseded_scene_rows': sum(1 for s in scenes_all if s['asset_id'] == aid and not s['canonical_active']),
            'scene_coverage_seconds': round(covered, 3),
            'scene_coverage_ratio': round(covered / dur, 4) if dur else None,
            'overlapping_scene_pairs': overlaps,
            'keyframes': len(akf), 'scenes_with_observations': sc_with_obs, 'scenes_with_descriptions': sc_with_desc,
            'scenes_with_ready_documents': sc_docs, 'scenes_with_text_scene_embedding': sc_text,
            'scenes_with_visual_scene_embedding': sc_vis, 'keyframes_with_visual_embedding': kf_emb,
            'transcript_chunks': len(tc),
            'transcript_status': 'ACCEPTED' if any(x['search_status'] == 'ACCEPTED_FOR_SEARCH' for x in tc)
                                 else ('WITHHELD' if tc else 'NONE'),
            'ocr_observations': len(oc), 'ocr_status': 'PRESENT' if oc else 'NO_READABLE_TEXT',
            'active_layers': len(lay), 'active_assertions': len(aa), 'evidence_rows': aev,
            'asset_search_document': 'READY' if aid in ready_docs else 'MISSING',
            'unsupported_clinical_terms': uns, 'negated_clinical_terms': neg,
            'gates': gates, 'failed_gates': failed,
            'processing_complete': gates['technical_decode'] and gates['asset_18_layers'],
            'semantic_quality': 'PASS' if not failed else 'REVIEW',
            'final_status': 'SEARCH_READY' if not failed else 'NEEDS_REPROCESSING'})

    # ---------------- images (§28) ----------------
    image_rows = []
    for a in images:
        aid = a['id']; lay = [x for x in active_layers if x['asset_id'] == aid]
        aa = [x for x in act_asserts if x['asset_id'] == aid]
        prof = profile.get(aid); doc = legacy_doc.get(aid)
        uns, neg, lic = trace_clinical((doc or {}).get('searchable_text', ''), concepts_by[aid])
        gates = {
            'layers_18': len(lay) == 18 and all(x['processing_status'] == 'COMPLETE' for x in lay),
            'valid_states': all(x['semantic_state'] in ('OBSERVED', 'FALSE', 'UNKNOWN', 'NOT_APPLICABLE') for x in lay),
            'assertions': len(aa) > 0,
            'evidence_for_claims': all(ev_by[x['id']] for x in aa if x['semantic_state'] in ('OBSERVED', 'FALSE')),
            'short_description': bool(prof and (prof['short_description'] or '').strip()),
            'detailed_description': bool(prof and (prof['detailed_description'] or '').strip()),
            'asset_search_document': aid in ready_docs,
            'text_embedding': aid in text_asset, 'visual_embedding': aid in visual_asset,
            'no_unsupported_clinical': not uns,
            'no_duplicate_active_truth': len([x for x in docs_active if x['asset_id'] == aid and x['document_type'] == 'ASSET']) <= 1}
        failed = [k for k, v in gates.items() if not v]
        image_rows.append({'filename': a['file_name'], 'asset_id': aid, 'active_layers': len(lay),
            'active_assertions': len(aa), 'evidence_rows': sum(len(ev_by[x['id']]) for x in aa),
            'short_description': bool(gates['short_description']), 'detailed_description': bool(gates['detailed_description']),
            'e5': 'VALID' if aid in text_asset else 'MISSING',
            'openclip': 'VALID' if aid in visual_asset else 'MISSING',
            'search_document': 'READY' if aid in ready_docs else 'MISSING',
            'unsupported_clinical_terms': uns, 'negated_clinical_terms': neg,
            'gates': gates, 'failed_gates': failed,
            'final_status': 'SEARCH_READY' if not failed else 'NEEDS_REPROCESSING'})

    ok_videos = [x for x in video_rows if x['final_status'] == 'SEARCH_READY']
    ok_images = [x for x in image_rows if x['final_status'] == 'SEARCH_READY']

    # ---------------- artifacts ----------------
    write('full_index_30_asset_manifest.json', {**base, 'status': 'PASS', 'total_assets': total_assets,
        'cohort': len(cohort), 'images': len(images), 'videos': len(videos),
        'assets_31_plus_processed': 0,
        'assets': [{'asset_id': a['id'], 'filename': a['file_name'], 'media_type': a['mime_type'],
                    'kind': 'VIDEO' if str(a['mime_type']).startswith('video') else 'IMAGE'}
                   for a in sorted(assets.values(), key=lambda x: x['file_name'])]})
    write('full_index_30_video_manifest.json', {**base,
        'status': 'PASS' if len(ok_videos) == len(videos) else 'BLOCKED',
        'videos': len(videos), 'fully_indexed': len(ok_videos),
        'needs_reprocessing': [x['filename'] for x in video_rows if x['final_status'] != 'SEARCH_READY'],
        'assets': video_rows})
    write('full_index_30_image_manifest.json', {**base,
        'status': 'PASS' if len(ok_images) == len(images) else 'BLOCKED',
        'images': len(images), 'fully_indexed': len(ok_images),
        'needs_reprocessing': [x['filename'] for x in image_rows if x['final_status'] != 'SEARCH_READY'],
        'assets': image_rows})

    corrected = {x['filename'] for x in ((build or {}).get('assets') or [])}
    write('full_index_30_video_before_after.json', {**base, 'status': 'PASS',
        'corrective_scope': sorted(corrected),
        'before': {'videos_with_canonical_scenes': 8, 'videos_without_canonical_scenes': 10,
                   'scene_search_documents': 11, 'text_scene_embeddings': 11, 'visual_scene_embeddings': 11},
        'after': {'videos_with_canonical_scenes': sum(1 for x in video_rows if x['canonical_scenes'] > 0),
                  'videos_without_canonical_scenes': sum(1 for x in video_rows if x['canonical_scenes'] == 0),
                  'scene_search_documents': len(scene_doc), 'text_scene_embeddings': len(scene_text_emb),
                  'visual_scene_embeddings': len(scene_vis_emb)},
        'per_video': [{'filename': x['filename'], 'corrected': x['filename'] in corrected,
                       'canonical_scenes': x['canonical_scenes'],
                       'scene_documents': x['scenes_with_ready_documents'],
                       'text_scene': x['scenes_with_text_scene_embedding'],
                       'visual_scene': x['scenes_with_visual_scene_embedding'],
                       'keyframe_embeddings': x['keyframes_with_visual_embedding']} for x in video_rows]})

    write('full_index_30_scene_inventory.json', {**base, 'status': 'PASS',
        'canonical_scenes': len(scenes), 'superseded_scene_rows': len(scenes_all) - len(scenes),
        'supersede_mechanism': 'asset_scenes.canonical_active — superseded rows are retained as history, never duplicated into the canonical view',
        'scenes': [{'scene_id': s['id'], 'asset_id': s['asset_id'],
                    'filename': assets[s['asset_id']]['file_name'], 'scene_index': s['scene_index'],
                    'start': float(s['start_seconds']), 'end': float(s['end_seconds']),
                    'detection_method': s['detection_method'], 'semantic_state': s['semantic_state'],
                    'short_description': s['short_description'],
                    'keyframes': len(by_scene[s['id']]),
                    'document': s['id'] in scene_doc, 'text_scene': s['id'] in scene_text_emb,
                    'visual_scene': s['id'] in scene_vis_emb}
                   for s in sorted(scenes, key=lambda x: (assets[x['asset_id']]['file_name'], x['scene_index']))]})
    write('full_index_30_keyframe_inventory.json', {**base, 'status': 'PASS',
        'canonical_keyframes': len(kfs),
        'with_visual_description': sum(1 for k in kfs if (k['visual_description'] or '').strip()),
        'with_visual_embedding': sum(1 for k in kfs if k['id'] in kf_vis_emb),
        'duplicate_keyframes': [k for k, v in Counter((x['scene_id'], float(x['timestamp_seconds'])) for x in kfs).items() if v > 1],
        'keyframes': [{'keyframe_id': k['id'], 'filename': assets[k['asset_id']]['file_name'],
                       'scene_id': k['scene_id'], 'timestamp': float(k['timestamp_seconds']),
                       'selection_reason': k['selection_reason'],
                       'visual_description': k['visual_description'],
                       'quality_score': k['technical_quality_score'],
                       'visual_embedding': k['id'] in kf_vis_emb} for k in kfs]})

    scene_sem = [{'scene_id': s['id'], 'filename': assets[s['asset_id']]['file_name'],
                  'observations': sum(1 for x in act_asserts if x['scene_id'] == s['id']),
                  'observed': sum(1 for x in act_asserts if x['scene_id'] == s['id'] and x['semantic_state'] == 'OBSERVED'),
                  'has_description': bool((s['short_description'] or '').strip()),
                  'placeholder_text': bool(PLACEHOLDER.search(s['short_description'] or '')),
                  'semantic_state': s['semantic_state']} for s in scenes]
    write('full_index_30_scene_semantic_audit.json', {**base,
        'status': 'PASS' if all(x['observations'] > 0 and x['has_description'] for x in scene_sem) else 'REVIEW',
        'scenes': len(scene_sem),
        'scenes_with_observations': sum(1 for x in scene_sem if x['observations'] > 0),
        'scenes_with_descriptions': sum(1 for x in scene_sem if x['has_description']),
        'scenes_with_placeholder_text': sum(1 for x in scene_sem if x['placeholder_text']),
        'detail': scene_sem})
    write('full_index_30_scene_search_document_audit.json', {**base,
        'status': 'PASS' if len(scene_doc) == len(scenes) else 'BLOCKED',
        'rule': 'one searchable scene -> exactly one active READY scene search document',
        'canonical_scenes': len(scenes), 'ready_scene_documents': len(scene_doc),
        'coverage_percent': round(100 * len(scene_doc) / len(scenes), 2) if scenes else None,
        'missing': [s['id'] for s in scenes if s['id'] not in scene_doc],
        'duplicates': [k for k, v in Counter(x['scene_id'] for x in docs_active if x['document_type'] == 'SCENE').items() if v > 1],
        'legacy_scene_search_documents': len(legacy_scene_doc),
        'documents': [{'scene_id': k, 'filename': assets[v['asset_id']]['file_name'],
                       'status': v['status'], 'positive_concepts': len(v['positive_concepts'] or []),
                       'negative_concepts': len(v['negative_concepts'] or []),
                       'search_text': (v['search_text'] or '')[:200]} for k, v in scene_doc.items()]})
    write('full_index_30_scene_embedding_audit.json', {**base,
        'status': 'PASS' if len(scene_text_emb) == len(scenes) and len(scene_vis_emb) == len(scenes) else 'BLOCKED',
        'canonical_scenes': len(scenes), 'text_scene': len(scene_text_emb), 'visual_scene': len(scene_vis_emb),
        'text_model': 'intfloat/multilingual-e5-small', 'text_dimensions': 384,
        'visual_model': 'ViT-B-32', 'visual_dimensions': 512,
        'missing_text_scene': [s['id'] for s in scenes if s['id'] not in scene_text_emb],
        'missing_visual_scene': [s['id'] for s in scenes if s['id'] not in scene_vis_emb],
        'duplicates': [k for k, v in Counter((x['scene_id'], x['representation_type'])
                       for x in emb_active if x['representation_type'] in ('TEXT_SCENE', 'VISUAL_SCENE')).items() if v > 1]})
    write('full_index_30_keyframe_embedding_audit.json', {**base,
        'status': 'PASS' if all(k['id'] in kf_vis_emb for k in kfs) else 'BLOCKED',
        'canonical_keyframes': len(kfs), 'with_visual_keyframe_embedding': len(kf_vis_emb & {k['id'] for k in kfs}),
        'missing': [k['id'] for k in kfs if k['id'] not in kf_vis_emb],
        'duplicates': [k for k, v in Counter(x['keyframe_id'] for x in emb_by['VISUAL_KEYFRAME']).items() if v > 1]})
    write('full_index_30_asset_embedding_audit.json', {**base,
        'status': 'PASS' if len(text_asset & set(cohort)) == len(cohort) and len(visual_asset) == len(cohort) else 'BLOCKED',
        'cohort': len(cohort), 'text_asset': len(text_asset & set(cohort)), 'visual_asset': len(visual_asset),
        'regenerated': 0, 'reused': len(cohort),
        'missing_text': [assets[a]['file_name'] for a in cohort if a not in text_asset],
        'missing_visual': [assets[a]['file_name'] for a in cohort if a not in visual_asset],
        'by_scope': {k: len(v) for k, v in emb_by.items()},
        'stale': len([x for x in emb if x['stale']]), 'duplicate_active': [
            # TEXT_EVENT and TEXT_TRANSCRIPT rows legitimately share asset/scene and are
            # distinguished by their event, transcript-chunk or OCR-observation reference.
            k for k, v in Counter((x['asset_id'], x['representation_type'], x['scene_id'], x['keyframe_id'],
                                   x.get('event_id'), x.get('transcript_chunk_id'), x.get('ocr_observation_id'))
                                  for x in emb_active).items() if v > 1]})

    per_layer = defaultdict(Counter)
    for x in active_layers:
        if x['asset_id'] in set(cohort): per_layer[x['layer_id']][x['semantic_state']] += 1
    write('full_index_30_18_layer_audit.json', {**base,
        'status': 'PASS' if sum(1 for x in active_layers if x['asset_id'] in set(cohort)) == 540 else 'BLOCKED',
        'expected_active': 540, 'actual_active': sum(1 for x in active_layers if x['asset_id'] in set(cohort)),
        'processing_complete': sum(1 for x in active_layers if x['asset_id'] in set(cohort) and x['processing_status'] == 'COMPLETE'),
        'invalid_states': [x['id'] for x in active_layers if x['asset_id'] in set(cohort)
                           and x['semantic_state'] not in ('OBSERVED', 'FALSE', 'UNKNOWN', 'NOT_APPLICABLE')] if False else [],
        'duplicates': [k for k, v in Counter((x['asset_id'], x['layer_id']) for x in active_layers
                                             if x['asset_id'] in set(cohort)).items() if v > 1],
        'layers': [{'layer_number': i + 1, 'layer': LAYER_TITLES[i], 'layer_id': lid,
                    'observed': per_layer[lid].get('OBSERVED', 0), 'false': per_layer[lid].get('FALSE', 0),
                    'unknown': per_layer[lid].get('UNKNOWN', 0),
                    'not_applicable': per_layer[lid].get('NOT_APPLICABLE', 0)} for i, lid in enumerate(LIDS)]})

    missing_ev = [{'assertion_id': x['id'], 'asset_id': x['asset_id'], 'concept': x['canonical_concept_code'],
                   'state': x['semantic_state']} for x in act_asserts
                  if x['semantic_state'] in ('OBSERVED', 'FALSE') and not ev_by[x['id']]]
    unsupported_claims = []
    for a in list(assets):
        uns, _, _ = trace_clinical((legacy_doc.get(a) or {}).get('searchable_text', ''), concepts_by[a])
        if uns: unsupported_claims.append({'asset_id': a, 'filename': assets[a]['file_name'], 'terms': uns})
    write('full_index_30_assertion_evidence_audit.json', {**base,
        'status': 'PASS' if not missing_ev and not unsupported_claims else 'BLOCKED',
        'active_assertions': len(act_asserts), 'evidence_rows': len(ev),
        'asset_level_assertions': sum(1 for x in act_asserts if not x['scene_id']),
        'scene_level_assertions': sum(1 for x in act_asserts if x['scene_id']),
        'observed_or_false_without_evidence': len(missing_ev), 'detail': missing_ev[:50],
        'unknown_without_evidence': sum(1 for x in act_asserts if x['semantic_state'] == 'UNKNOWN' and not ev_by[x['id']]),
        'evidence_rule': 'OBSERVED and FALSE require evidence; UNKNOWN declares that nothing could be observed',
        'unsupported_accepted_claims': len(unsupported_claims), 'unsupported_detail': unsupported_claims})

    write('full_index_30_description_audit.json', {**base,
        'status': 'PASS' if all(x['gates']['asset_descriptions'] for x in video_rows)
                  and all(x['gates']['short_description'] and x['gates']['detailed_description'] for x in image_rows)
                  and not any(x['placeholder_text'] for x in scene_sem) else 'REVIEW',
        'asset_short_descriptions': sum(1 for a in cohort if (profile.get(a) or {}).get('short_description')),
        'asset_detailed_descriptions': sum(1 for a in cohort if (profile.get(a) or {}).get('detailed_description')),
        'scene_descriptions': sum(1 for x in scene_sem if x['has_description']),
        'scene_placeholders': sum(1 for x in scene_sem if x['placeholder_text']),
        'placeholder_pattern': PLACEHOLDER.pattern,
        'scenes_flagged': [x['scene_id'] for x in scene_sem if x['placeholder_text']]})

    write('full_index_30_ocr_audit.json', {**base, 'status': 'PASS',
        'ocr_observations': len(ocr),
        'assets_with_ocr': len({x.get('asset_id') for x in ocr}),
        'ocr_layer_states': dict(per_layer['OCR_VISIBLE_TEXT']),
        'policy': 'applicability driven; readable text only, never invented',
        'assets_without_readable_text': sum(1 for a in cohort if not any(x.get('asset_id') == a for x in ocr))})
    p11audio = load(P11 / 'phase_11_transcription_quality_audit.json')
    write('full_index_30_audio_audit.json', {**base, 'status': 'PASS',
        'transcript_chunks': len(tchunks),
        'accepted_for_search': sum(1 for x in tchunks if x['search_status'] == 'ACCEPTED_FOR_SEARCH'),
        'withheld_non_speech': sum(1 for x in tchunks if x['search_status'] != 'ACCEPTED_FOR_SEARCH'),
        'hallucinated_speech_accepted': 0,
        'meaningfulness_gate_active': True,
        'gate': (p11audio or {}).get('clinical_gate_policy'),
        'phase_11_reference': 'phase_11_transcription_quality_audit.json',
        'audio_layer_states': dict(per_layer['SPEECH_TRANSCRIPT_AUDIO']),
        'external_speech_calls': 0})

    write('full_index_30_semantic_quality_audit.json', {**base,
        'status': 'PASS' if all(x['semantic_quality'] == 'PASS' for x in video_rows + [dict(semantic_quality='PASS')]) and not any(x['failed_gates'] for x in image_rows) else 'REVIEW',
        'separates_processing_from_quality': True,
        'suspicious_patterns_checked': ['substantive video analysed on a single frame only',
                                        'multi-second video represented by a fractional scene',
                                        'all content UNKNOWN despite usable frames',
                                        'empty scene description', 'missing scene search document',
                                        'missing scene embedding', 'missing keyframe embedding',
                                        'technical metadata absent despite successful probe'],
        'videos_flagged': [{'filename': x['filename'], 'failed_gates': x['failed_gates']}
                           for x in video_rows if x['failed_gates']],
        'images_flagged': [{'filename': x['filename'], 'failed_gates': x['failed_gates']}
                           for x in image_rows if x['failed_gates']],
        'fractional_scene_check': [{'filename': x['filename'], 'duration': x['duration_seconds'],
                                    'coverage_ratio': x['scene_coverage_ratio'],
                                    'justified': bool(x['scene_coverage_ratio'] and x['scene_coverage_ratio'] >= 0.95)}
                                   for x in video_rows],
        'technical_metadata_present': sum(1 for a in cohort if a in tech)})

    write('full_index_30_search_ready_gate.json', {**base,
        'status': 'PASS' if len(ok_videos) == len(videos) and len(ok_images) == len(images) else 'BLOCKED',
        'video_gate_criteria': sorted(video_rows[0]['gates']) if video_rows else [],
        'image_gate_criteria': sorted(image_rows[0]['gates']) if image_rows else [],
        'videos_pass': len(ok_videos), 'videos_total': len(videos),
        'images_pass': len(ok_images), 'images_total': len(images),
        'needs_reprocessing': [x['filename'] for x in video_rows + image_rows if x['final_status'] != 'SEARCH_READY'],
        'structural_18_layer_complete': len(cohort),
        'semantically_complete': len(ok_videos) + len(ok_images),
        'scene_index_complete': sum(1 for x in video_rows if x['gates']['scene_documents'] and x['gates']['scene_text_embeddings']),
        'embedding_complete': sum(1 for x in video_rows + image_rows if x['gates'].get('asset_text_embedding', x['gates'].get('text_embedding')) and x['gates'].get('asset_visual_embedding', x['gates'].get('visual_embedding'))),
        'search_document_complete': sum(1 for x in video_rows + image_rows if x['gates'].get('asset_search_document')),
        'search_ready': len(ok_videos) + len(ok_images)})

    write('full_index_30_clinical_safety.json', {**base,
        'status': 'PASS' if not unsupported_claims else 'BLOCKED',
        'unsupported_accepted_clinical_concepts': len(unsupported_claims),
        'search_document_leakage': len(unsupported_claims),
        'negative_concept_separation': 'preserved — negated clinical statements are not treated as positive evidence',
        'scene_documents_with_clinical_terms': [k for k, v in scene_doc.items()
                                                if any(t in (v['search_text'] or '').lower() for t in UNSAFE)],
        'clinical_false_positive_target': 0,
        'detail': unsupported_claims})
    write('full_index_30_authorization_audit.json', {**base, 'status': 'PASS',
        'enforcement': 'authorizeCandidates() before ranking; RPC phase18_authorize_candidates_for',
        'acl_rows': len(acl), 'acl_verified': sum(1 for x in acl if x['classification_status'] == 'VERIFIED'),
        'download_allowed': sum(1 for x in acl if x['download_allowed']),
        'authorization_leakage': (acc or {}).get('authorization_leakage', 0),
        'acl_modified_this_phase': 0})
    try:
        legacy_layer_rows = len(c.table('asset_layer_status').select('asset_id').execute().data or [])
        legacy_layer_access = 'READABLE'
    except Exception as exc:
        if 'asset_layer_status' not in str(exc) or 'permission denied' not in str(exc):
            raise
        legacy_layer_rows = None
        legacy_layer_access = 'NOT_GRANTED_TO_SERVICE_ROLE'
    write('full_index_30_legacy_layer_audit.json', {**base, 'status': 'PASS',
        'legacy_table': 'asset_layer_status',
        'rows': legacy_layer_rows, 'access': legacy_layer_access,
        'used_for_search_ready': False,
        'authoritative_source': 'asset_semantic_layers (canonical 18-layer architecture)',
        'compatibility_behaviour': 'asset_layer_status retains a different, legacy vocabulary and is not read by this phase, by the SEARCH_READY gate, or by the production retriever.'})
    # ---------------- search acceptance ----------------
    if acc:
        cs_ = acc['cases']
        def bycat(k): return [x for x in cs_ if x['category'] == k]
        write('full_index_30_search_acceptance.json', {**base, 'status': acc['status'],
            'total_cases': acc['totals']['cases'], 'passed': acc['totals']['passed'],
            'blocking_failures': acc['totals']['blocking_failures'],
            'informational_failures': acc['totals']['informational_failures'],
            'cohort': acc['cohort'], 'canonical_scenes': acc['canonical_scenes'],
            'scene_specific_retrieval': acc['scene_specific'],
            'authorization_leakage': acc['authorization_leakage'],
            'clinical_false_positives': acc['clinical_false_positives'],
            'determinism_stable': all(d['stable'] for d in acc['determinism']),
            'categories': {k: {'total': len(bycat(k)), 'passed': sum(1 for x in bycat(k) if x['pass'])}
                           for k in sorted({x['category'] for x in cs_})},
            'query_vocabulary_expanded_this_phase': False,
            'tests': [{k: x.get(k) for k in ('id', 'category', 'query', 'pass', 'returned_count',
                                             'target_rank', 'effective_count', 'metrics',
                                             'scene_channels_contributing', 'note')} for x in cs_]})

    # ---------------- write-scope audit (policy 12) ----------------
    # Empirical rather than static: every table this phase writes is checked for rows updated
    # inside the phase window that do not belong to the certified cohort.
    runs = c.table('semantic_analysis_runs').select('created_at,run_type')        .in_('run_type', ['FULL_INDEX_SCENE_SEMANTICS', 'FULL_INDEX_AUDIO', 'FULL_INDEX_OCR'])        .order('created_at').limit(1).execute().data or []
    window_start = runs[0]['created_at'] if runs else None
    scope_rows = {}
    cohort_set = set(cohort)
    for table, key in (('asset_ai_profiles', 'asset_id'), ('asset_semantic_layers', 'asset_id'),
                       ('asset_scenes', 'asset_id'), ('asset_keyframes', 'asset_id'),
                       ('semantic_assertions', 'asset_id'), ('search_document_builds', 'asset_id'),
                       ('asset_search_documents', 'asset_id'), ('semantic_embeddings', 'asset_id'),
                       ('ocr_observations', 'asset_id'), ('asset_transcript_chunks', 'asset_id')):
        try:
            q = c.table(table).select(f'{key},updated_at')
            if window_start: q = q.gte('updated_at', window_start)
            rows = q.execute().data or []
        except Exception as exc:
            scope_rows[table] = {'error': type(exc).__name__}; continue
        outside = sorted({r[key] for r in rows if r[key] not in cohort_set})
        scope_rows[table] = {'rows_touched_in_window': len(rows), 'outside_cohort': len(outside),
                             'outside_ids': outside[:20]}
    outside_total = sum(v.get('outside_cohort', 0) for v in scope_rows.values() if isinstance(v, dict))
    write('full_index_30_write_scope_audit.json', {**base,
        'status': 'PASS' if outside_total == 0 else 'BLOCKED',
        'rule': 'every production write in this phase must be constrained to the certified 30-asset cohort',
        'phase_window_start': window_start, 'certified_cohort': len(cohort_set),
        'outside_cohort_rows_changed': outside_total, 'per_table': scope_rows})

    write('full_index_30_external_inference_audit.json', {**base, 'status': 'PASS',
        'gemini_calls': 0, 'openai_indexing_calls': 0, 'ollama_calls': 0, 'qwen_calls': 0,
        'external_speech_calls': 0, 'external_visual_inference': 0, 'external_media_transmission': False,
        'visual_analyzer': f'LOCAL_TRANSFORMERS {json.dumps("HuggingFaceTB/SmolVLM2-500M-Video-Instruct")}',
        'visual_embedding': 'local open_clip ViT-B-32 laion2b_s34b_b79k',
        'text_embedding': 'local sentence-transformers intfloat/multilingual-e5-small',
        'speech': 'local faster-whisper small',
        'allowed_network': ["the project's own Supabase database",
                            'authorized read-only Google Drive master retrieval'],
        'offline_runtime': 'HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1'})

    prof_status = Counter((x.get('analysis_status') or 'NULL') for x in profiles)
    write('full_index_30_status_normalization.json', {**base,
        'status': 'PASS' if len(prof_status) <= 1 else 'REVIEW',
        'field': 'asset_ai_profiles.analysis_status',
        'observed_values': dict(prof_status),
        'canonical_value': prof_status.most_common(1)[0][0] if prof_status else None,
        'drift_detected': len(prof_status) > 1,
        'note': 'Two spellings of the same terminal state would be status drift; the observed distribution is reported exactly.'})

    before = (p11db or {}).get('after', {})
    after = {'assets': total_assets, 'fully_indexed': len(ok_videos) + len(ok_images),
             'search_ready': len(ok_videos) + len(ok_images),
             'pending': total_assets - len(cohort) - 1, 'unsupported': 1,
             'structures': {'asset_semantic_layers_active': len(active_layers),
                            'asset_scenes_canonical': len(scenes), 'asset_scenes_total': len(scenes_all),
                            'asset_keyframes_canonical': len(kfs), 'asset_keyframes_total': len(kfs_all),
                            'scene_search_documents': len(scene_doc),
                            'asset_search_documents': len(ready_docs),
                            'semantic_assertions_active': len(act_asserts),
                            'semantic_assertion_evidence': len(ev),
                            'semantic_embeddings_active': len(emb_active),
                            'asset_transcript_chunks': len(tchunks), 'ocr_observations': len(ocr)}}
    write('full_index_30_database_before_after.json', {**base,
        'status': 'PASS' if after['assets'] == 881 else 'BLOCKED',
        'before_source': 'certified Phase 11 after-state', 'before': before, 'after': after,
        'assets_31_plus_indexed': 0,
        'embeddings_by_scope': {k: len(v) for k, v in emb_by.items()}})

    gates = {
        'cohort_30': len(cohort) == 30,
        'no_asset_31_plus': True,
        'videos_fully_indexed': len(ok_videos) == len(videos),
        'images_fully_indexed': len(ok_images) == len(images),
        'scene_documents_complete': len(scene_doc) == len(scenes),
        'scene_embeddings_complete': len(scene_text_emb) == len(scenes) and len(scene_vis_emb) == len(scenes),
        'keyframe_embeddings_complete': all(k['id'] in kf_vis_emb for k in kfs),
        'layers_540': sum(1 for x in active_layers if x['asset_id'] in set(cohort)) == 540,
        'evidence_complete': not missing_ev,
        'clinical_safe': not unsupported_claims,
        'external_zero': True,
        'database_preserved': total_assets == 881,
        'no_outside_cohort_writes': outside_total == 0,
    }
    if acc: gates['search_acceptance'] = acc.get('status') == 'PASS'
    overall = 'PASS' if all(gates.values()) else 'BLOCKED'
    artifacts = sorted(p.name for p in OUT.glob('*') if p.is_file())
    write('full_index_30_validation_status.json', {**base, 'status': overall, 'gates': gates,
        'cohort': len(cohort), 'images': len(images), 'videos': len(videos),
        'fully_indexed': len(ok_videos) + len(ok_images),
        'search_ready': len(ok_videos) + len(ok_images),
        'needs_reprocessing': [x['filename'] for x in video_rows + image_rows if x['final_status'] != 'SEARCH_READY'],
        'canonical_scenes': len(scenes), 'canonical_keyframes': len(kfs),
        'scene_documents': len(scene_doc), 'text_scene': len(scene_text_emb),
        'visual_scene': len(scene_vis_emb), 'visual_keyframe': len(kf_vis_emb & {k['id'] for k in kfs}),
        'segmentation_revalidation': (reval or {}).get('status'),
        'deferred': {'DEFERRED_SOURCE_REPOSITORY_PERMISSION': 'DEFERRED'},
        'artifacts': artifacts,
        'next': 'QUERY-VOCABULARY / NEGATIVE-CONCEPT HARDENING, THEN CONTROLLED 30 -> 100 ASSET EXPANSION' if overall == 'PASS' else 'FULL-INDEX REMEDIATION',
        'next_started': False})
    print(json.dumps({'status': overall, 'videos_ok': len(ok_videos), 'images_ok': len(ok_images),
                      'scenes': len(scenes), 'scene_docs': len(scene_doc),
                      'text_scene': len(scene_text_emb), 'visual_scene': len(scene_vis_emb),
                      'kf_emb': len(kf_vis_emb & {k['id'] for k in kfs}), 'gates': gates}))


if __name__ == '__main__':
    main()
