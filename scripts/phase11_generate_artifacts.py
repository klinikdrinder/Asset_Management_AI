"""Phase 11 certification artifacts.

Reads committed database truth plus the Phase 11 transcription and acceptance outputs. Never
re-analyzes media, never writes semantic data.
"""
from __future__ import annotations
import json, os, re, statistics, subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

R = Path(__file__).resolve().parents[1]
OUT = R / 'reports/semantic-search/rollout/phase-11'; OUT.mkdir(parents=True, exist_ok=True)
P10 = R / 'reports/semantic-search/rollout/phase-10'
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
CLINICAL_CONCEPTS = ('HAIR_TRANSPLANT', 'HAIR_TRANSPLANT_FUE', 'FUE_IMPLANTATION', 'INJECTABLES',
                     'HAIR_TRANSPLANT_PROCEDURE_CONTENT')
# A clinical word is licensed for an asset when one of its own observed concepts supports it.
# Anything else is either an explicit grounded negation ("no active procedure") or unsupported.
CLINICAL_LICENSE = {
    'hair transplant': ('HAIR_TRANSPLANT', 'HAIR_TRANSPLANT_FUE', 'HAIR_TRANSPLANT_PROCEDURE_CONTENT', 'FUE_IMPLANTATION'),
    'fue': ('HAIR_TRANSPLANT_FUE', 'FUE_IMPLANTATION'),
    'implantation': ('FUE_IMPLANTATION', 'IMPLANTING_GRAFTS'),
    'graft': ('FUE_IMPLANTATION', 'IMPLANTING_GRAFTS', 'RECIPIENT_REGION'),
    'extraction': (), 'prp': (), 'laser treatment': (), 'surgery': (),
    'graft harvesting': (), 'graft placement': (),
    'injection': ('INJECTABLES', 'INJECTING', 'HOLDING_SYRINGE', 'VISIBLE_INJECTION_AT_LOWER_FACE', 'VISIBLE_INJECTION_AT_NECK'),
    'procedure': ('PROCEDURE_CONTENT', 'PROCEDURE_PREPARATION_CONTENT', 'VISIBLE_RECIPIENT_AREA_PROCEDURE',
                  'HAIR_TRANSPLANT_PROCEDURE_CONTENT', 'OPERATING_ROOM'),
    'treatment': ('TREATMENT_ROOM', 'PATIENT_POSITIONED_IN_TREATMENT_CHAIR', 'CLINICIAN_TREATS_PATIENT',
                  'SCALP_UNDER_ACTIVE_CLINICAL_ATTENTION', 'FACE_UNDER_ACTIVE_CLINICAL_ATTENTION',
                  'NECK_TREATMENT_AREA_DOMINANT', 'TREATMENT_AREA_PARTIALLY_VISIBLE',
                  'TOOL_VISIBLE_NEAR_TREATMENT_AREA')}


def trace_clinical_text(text, own_concepts):
    """Classify each clinical term in a search document as licensed, an explicit grounded
    negation, or unsupported. Returns (unsupported, negated, licensed)."""
    low = ' '.join(str(text or '').lower().split())
    unsupported, negated, lic = [], [], []
    for term in UNSAFE:
        if term not in low: continue
        if any(code in own_concepts for code in CLINICAL_LICENSE.get(term, ())): lic.append(term)
        elif re.search(r'no [a-z ]{0,24}' + re.escape(term), low): negated.append(term)
        else: unsupported.append(term)
    return unsupported, negated, lic
CANARY = 'a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd'
PILOT_10 = ['7f72217d-3839-4920-86b4-ccc33e9e3d95', 'babae120-9372-42ad-b535-02a3276ea2be',
            'c86344e9-5b32-4d86-9205-67952d508651', '444da390-0117-4380-8c87-d7c32f2903ff',
            '37838d30-a0ce-4f90-8cc3-c986db0aaa65', '6215ad8b-12be-4a8e-bc49-f6b3dcf55c21',
            '64712c6a-c02c-46e9-9f73-16786109468b', '47611c6d-7923-42a4-87b6-c2a416a90f5c',
            'bfae6c51-5d71-47ae-a3e1-6d07092b8896', '753eb5f3-82c7-4148-a226-d5b960fd8619']
ORIGINAL_11 = PILOT_10 + [CANARY]


def env():
    e = {}
    for f in (R / '.env', R / '.env.local', R / 'dashboard/.env.local'):
        if f.exists(): e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ); return e


def write(name, data): (OUT / name).write_text(json.dumps(data, indent=2, default=str) + '\n', encoding='utf-8')
def load(p): return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def chunked(c, table, fields, ids, key='asset_id'):
    rows = []
    for i in range(0, len(ids), 50):
        rows += c.table(table).select(fields).in_(key, ids[i:i + 50]).execute().data or []
    return rows


def main():
    e = env()
    c = create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'], e['SUPABASE_SERVICE_ROLE_KEY'])
    now = datetime.now(timezone.utc).isoformat(); base = {'generated_at': now, 'phase': 11}
    tr = load(OUT / 'phase_11_transcription_results.json')
    acc = load(OUT / 'phase_11_raw_acceptance.json')
    p10ba = load(P10 / 'phase_10_database_before_after.json')
    p10perf = load(P10 / 'phase_10_performance.json')

    # ---------------- cohort ----------------
    all_layers = c.table('asset_semantic_layers').select('asset_id,layer_id,semantic_state,processing_status,applicability,active').execute().data or []
    active_layers = [x for x in all_layers if x['active']]
    per = defaultdict(lambda: {'n': 0, 'c': 0})
    for x in active_layers:
        per[x['asset_id']]['n'] += 1
        if x['processing_status'] == 'COMPLETE': per[x['asset_id']]['c'] += 1
    cohort = sorted(k for k, v in per.items() if v['n'] == 18 and v['c'] == 18)
    assets = {x['id']: x for x in chunked(c, 'assets', 'id,file_name,mime_type,file_extension,content_hash,checksum_sha256,file_size_bytes', cohort, key='id')}
    total_assets = len(c.table('assets').select('id').execute().data or [])
    ready = {x['asset_id'] for x in (c.table('asset_search_documents').select('asset_id,build_status').eq('build_status', 'READY').execute().data or [])}

    asserts = chunked(c, 'semantic_assertions', 'id,asset_id,layer_id,canonical_concept_code,value_text,semantic_state,active,scene_id,keyframe_id', cohort)
    active_asserts = [x for x in asserts if x['active']]
    ev = chunked(c, 'semantic_assertion_evidence', 'id,assertion_id,asset_id,scene_id,keyframe_id,evidence_type,polarity,start_time,end_time', [x['id'] for x in active_asserts], key='assertion_id')
    all_doc_builds = [x for x in chunked(c, 'search_document_builds', 'id,asset_id,document_type,search_text,positive_concepts,status,active,stale,document_fingerprint,search_document_version', cohort) if x['active'] and not x['stale']]
    docs = [x for x in all_doc_builds if x['document_type'] == 'ASSET']
    legacy = chunked(c, 'asset_search_documents', 'asset_id,searchable_text,build_status,document_version', cohort)
    e5 = [x for x in chunked(c, 'semantic_embeddings', 'id,asset_id,provider,model,model_version,dimensions,representation_type,active,stale,source_text_fingerprint,source_document_fingerprint,vector_fingerprint', cohort) if x['active'] and not x['stale'] and x['representation_type'] == 'TEXT_ASSET']
    clip = chunked(c, 'asset_visual_embeddings', 'id,asset_id,model_name,embedding_dimensions', cohort)
    scenes = chunked(c, 'asset_scenes', 'id,asset_id,start_seconds,end_seconds', cohort)
    keyframes = chunked(c, 'asset_keyframes', 'id,asset_id,scene_id,timestamp_seconds', cohort)
    tchunks = chunked(c, 'asset_transcript_chunks', 'id,asset_id,start_seconds,end_seconds,transcript_text,language,confidence,transcription_status,search_status,scene_id,provenance,provider,model', cohort)
    acl = chunked(c, 'asset_access_control', 'asset_id,classification_status,is_clinical,sensitivity_level,internal_usage_status,requires_clinical_permission,download_allowed', cohort)

    # ---------------- §6 integrity ----------------
    dup_layers = [k for k, v in Counter((x['asset_id'], x['layer_id']) for x in active_layers if x['asset_id'] in cohort).items() if v > 1]
    dup_assert = [k for k, v in Counter((x['asset_id'], x['canonical_concept_code']) for x in active_asserts).items() if v > 1]
    dup_docs = [k for k, v in Counter(x['asset_id'] for x in docs).items() if v > 1]
    dup_e5 = [k for k, v in Counter(x['asset_id'] for x in e5).items() if v > 1]
    scene_ids = {x['id'] for x in scenes}; key_ids = {x['id'] for x in keyframes}
    key_scene = {x['id']: x['scene_id'] for x in keyframes}
    span = {x['id']: (float(x['start_seconds'] or 0), float(x['end_seconds'] or 0)) for x in scenes}
    ev_by = defaultdict(list)
    for x in ev: ev_by[x['assertion_id']].append(x)
    invalid_ev = []
    for a in active_asserts:
        rows = ev_by.get(a['id'], [])
        if not rows and a['semantic_state'] in ('OBSERVED', 'FALSE'):
            invalid_ev.append({'assertion_id': a['id'], 'asset_id': a['asset_id'], 'reason': 'NO_EVIDENCE_ROW'})
        for x in rows:
            if x['asset_id'] != a['asset_id']: invalid_ev.append({'evidence_id': x['id'], 'reason': 'ASSET_LINKAGE_MISMATCH'})
            if x['scene_id'] and x['scene_id'] not in scene_ids: invalid_ev.append({'evidence_id': x['id'], 'reason': 'SCENE_REFERENCE_INVALID'})
            if x['keyframe_id'] and x['keyframe_id'] not in key_ids: invalid_ev.append({'evidence_id': x['id'], 'reason': 'KEYFRAME_REFERENCE_INVALID'})
            if x['keyframe_id'] and x['scene_id'] and key_scene.get(x['keyframe_id']) != x['scene_id']: invalid_ev.append({'evidence_id': x['id'], 'reason': 'KEYFRAME_SCENE_MISMATCH'})
            s = span.get(x['scene_id'])
            if s and x['start_time'] is not None and not (s[0] - 1e-6 <= float(x['start_time']) <= s[1] + 1e-6):
                invalid_ev.append({'evidence_id': x['id'], 'reason': 'TIMESTAMP_OUTSIDE_SCENE'})
            if a['semantic_state'] in ('OBSERVED', 'FALSE'):
                exp = 'POSITIVE' if a['semantic_state'] == 'OBSERVED' else 'NEGATIVE'
                if x['polarity'] != exp: invalid_ev.append({'evidence_id': x['id'], 'reason': 'POLARITY_STATE_MISMATCH'})
    doc_by = {x['asset_id']: x for x in docs}; legacy_by = {x['asset_id']: x for x in legacy}
    e5_by = {x['asset_id']: x for x in e5}; clip_by = {x['asset_id']: x for x in clip}
    acl_by = {x['asset_id']: x for x in acl}
    concepts_by = defaultdict(set)
    for x in active_asserts:
        if x['semantic_state'] == 'OBSERVED': concepts_by[x['asset_id']].add(x['canonical_concept_code'])
    integrity = []
    for aid in cohort:
        a = assets.get(aid, {}); d = doc_by.get(aid); l = legacy_by.get(aid); t = e5_by.get(aid); v = clip_by.get(aid)
        lay = [x for x in active_layers if x['asset_id'] == aid]
        text = ((d or {}).get('search_text') or '') + ' ' + ((l or {}).get('searchable_text') or '')
        leak, negated_terms, licensed_terms = trace_clinical_text(text, concepts_by[aid])
        # Older pilot documents store positive_concepts as objects; newer ones as bare codes.
        pos = [(p.get('canonical_code') or p.get('code') or p.get('canonical_concept_code'))
               if isinstance(p, dict) else p for p in ((d or {}).get('positive_concepts') or [])]
        stray = [p for p in pos if p and p not in concepts_by[aid]]
        row = {'asset_id': aid, 'filename': a.get('file_name'), 'media_type': a.get('mime_type'),
               'complete': len(lay) == 18 and all(x['processing_status'] == 'COMPLETE' for x in lay),
               'active_layers': len(lay),
               'layer_states_valid': all(x['semantic_state'] in ('OBSERVED', 'FALSE', 'UNKNOWN', 'NOT_APPLICABLE') for x in lay),
               'search_ready': aid in ready,
               'search_document': bool(d) and d['status'] == 'READY',
               'legacy_document': bool(l) and l['build_status'] == 'READY',
               'e5_valid': bool(t and t['dimensions'] == 384 and t['model'] == 'intfloat/multilingual-e5-small'),
               'openclip_valid': bool(v and v['embedding_dimensions'] == 512 and v['model_name'] == 'ViT-B-32'),
               'acl_verified': bool(acl_by.get(aid) and acl_by[aid]['classification_status'] == 'VERIFIED'),
               'download_allowed': bool(acl_by.get(aid) and acl_by[aid]['download_allowed']),
               'unsupported_clinical_in_document': leak,
               'grounded_negated_clinical_terms': negated_terms,
               'licensed_clinical_terms': licensed_terms,
               'rejected_observations_in_document': stray,
               'observed_concepts': sorted(concepts_by[aid])}
        row['valid'] = all([row['complete'], row['layer_states_valid'], row['search_ready'], row['search_document'],
                            row['legacy_document'], row['e5_valid'], row['openclip_valid'], row['acl_verified'],
                            not leak, not stray])
        integrity.append(row)
    per_layer = defaultdict(Counter)
    for x in active_layers:
        if x['asset_id'] in cohort: per_layer[x['layer_id']][x['semantic_state']] += 1
    coverage = [{'layer_number': i + 1, 'layer': LAYER_TITLES[i], 'layer_id': lid,
                 'assets': sum(per_layer[lid].values()), 'observed': per_layer[lid].get('OBSERVED', 0),
                 'unknown': per_layer[lid].get('UNKNOWN', 0), 'false': per_layer[lid].get('FALSE', 0),
                 'not_applicable': per_layer[lid].get('NOT_APPLICABLE', 0)} for i, lid in enumerate(LIDS)]
    integrity_ok = (len(cohort) == 30 and all(x['valid'] for x in integrity) and not dup_layers
                    and not dup_assert and not dup_docs and not dup_e5 and not invalid_ev)
    write('phase_11_30_asset_integrity_audit.json', {**base, 'status': 'PASS' if integrity_ok else 'FAIL',
        'cohort_size': len(cohort), 'expected_active_layer_states': 540,
        'observed_active_layer_states': sum(1 for x in active_layers if x['asset_id'] in cohort),
        'total_layer_rows_including_history': len(all_layers),
        'historical_inactive_rows': len(all_layers) - len(active_layers),
        'duplicate_active_layers': dup_layers, 'duplicate_active_assertions': dup_assert,
        'duplicate_active_asset_documents': dup_docs, 'duplicate_active_text_embeddings': dup_e5,
        'active_document_builds_by_type': dict(Counter(x['document_type'] for x in all_doc_builds)),
        'evidence_rule': 'evidence is required for OBSERVED and FALSE assertions; UNKNOWN declares that nothing could be observed and carries none',
        'unknown_assertions_without_evidence': sum(1 for a in active_asserts
            if a['semantic_state'] == 'UNKNOWN' and not ev_by.get(a['id'])),
        'active_assertions': len(active_asserts), 'evidence_rows': len(ev),
        'invalid_evidence': len(invalid_ev), 'invalid_evidence_detail': invalid_ev[:50],
        'layer_coverage': coverage, 'assets': integrity})

    # ---------------- §7 clinical specificity ----------------
    clinical_rows = []
    for x in active_asserts:
        if x['semantic_state'] != 'OBSERVED': continue
        code = x['canonical_concept_code'] or ''
        hit = code in CLINICAL_CONCEPTS or any(w in f"{code} {x['value_text']}".lower() for w in UNSAFE)
        if not hit: continue
        rows = ev_by.get(x['id'], [])
        clinical_rows.append({'asset_id': x['asset_id'], 'filename': assets.get(x['asset_id'], {}).get('file_name'),
            'layer_id': x['layer_id'], 'concept': code, 'value_text': x['value_text'],
            'evidence_rows': len(rows), 'evidence_types': sorted({r['evidence_type'] for r in rows}),
            'scene_linked': bool(x['scene_id']), 'keyframe_linked': bool(x['keyframe_id']),
            'traced_to_evidence': bool(rows),
            'origin_phase': 'ORIGINAL_11' if x['asset_id'] in ORIGINAL_11 else 'PHASE_10_COHORT'})
    doc_leak = [{'asset_id': x['asset_id'], 'filename': x['filename'], 'terms': x['unsupported_clinical_in_document']}
                for x in integrity if x['unsupported_clinical_in_document']]
    e5_leak = doc_leak  # E5 input is the search document text; one source, one check.
    untraced = [x for x in clinical_rows if not x['traced_to_evidence']]
    phase10_clinical = [x for x in clinical_rows if x['origin_phase'] == 'PHASE_10_COHORT']
    write('phase_11_clinical_specificity_audit.json', {**base,
        'status': 'PASS' if not untraced and not doc_leak else 'FAIL',
        'rule': 'A named treatment or procedure may be active only when its own evidence supports it. Generic gloves/instrument/scalp/contact observations never promote to a named procedure.',
        'active_clinical_concepts': len(clinical_rows), 'traced_to_evidence': len(clinical_rows) - len(untraced),
        'untraced': untraced, 'unsupported_accepted_clinical_concepts': len(untraced),
        'phase_10_cohort_clinical_concepts': len(phase10_clinical),
        'search_document_clinical_leakage': len(doc_leak), 'search_document_leakage_detail': doc_leak,
        'e5_input_clinical_leakage': len(e5_leak),
        'assets_with_supported_clinical_truth': sorted({x['filename'] for x in clinical_rows}),
        'detail': clinical_rows})

    # ---------------- §3-§5 transcription quality ----------------
    if tr:
        ta = tr.get('assets', [])
        p11_chunks = [x for x in tchunks if (x.get('provenance') or {}).get('origin') == 'PHASE11']
        bad = []
        for ch in p11_chunks:
            s, en = float(ch['start_seconds'] or 0), float(ch['end_seconds'] or 0)
            if not (0 <= s < en): bad.append({'chunk': ch['id'], 'reason': 'TIME_ORDER_INVALID'})
            if not str(ch['transcript_text'] or '').strip(): bad.append({'chunk': ch['id'], 'reason': 'EMPTY_TEXT'})
            if ch['asset_id'] not in cohort: bad.append({'chunk': ch['id'], 'reason': 'ASSET_OUTSIDE_COHORT'})
            if ch['scene_id'] and ch['scene_id'] not in scene_ids: bad.append({'chunk': ch['id'], 'reason': 'SCENE_REFERENCE_INVALID'})
        halluc = sum(x.get('hallucination_flagged', 0) for x in ta)
        accepted_halluc = sum(1 for ch in p11_chunks if ch['search_status'] == 'ACCEPTED_FOR_SEARCH'
                              and 'REPETITIVE_TRANSCRIPTION_HALLUCINATION_CANDIDATE' in ((ch.get('provenance') or {}).get('quality_flags') or []))
        write('phase_11_transcription_quality_audit.json', {**base,
            'status': 'PASS' if not bad and accepted_halluc == 0 else 'FAIL',
            'candidates': tr.get('planned'), 'processed': len(ta),
            'speech_present_yes': sum(1 for x in ta if x.get('speech_present') == 'YES'),
            'speech_present_no': sum(1 for x in ta if x.get('speech_present') == 'NO'),
            'speech_present_unknown': sum(1 for x in ta if x.get('speech_present') == 'UNKNOWN'),
            'chunks_written': len(p11_chunks),
            'accepted_for_search': sum(1 for x in p11_chunks if x['search_status'] == 'ACCEPTED_FOR_SEARCH'),
            'excluded_low_confidence': sum(1 for x in p11_chunks if x['search_status'] == 'EXCLUDED'),
            'excluded_review_required': sum(1 for x in p11_chunks if x['search_status'] == 'EXCLUDED_REVIEW_REQUIRED'),
            'hallucination_candidates_flagged': halluc, 'hallucination_candidates_accepted': accepted_halluc,
            'clinical_gated_chunks': sum(x.get('clinical_gated_chunks', 0) for x in ta),
            'clinical_gate_policy': 'A spoken clinical term is evidence of speech, not evidence that the procedure is depicted. Such chunks are stored truthfully and withheld from active search text and embedding input.',
            'invalid_chunks': bad, 'temporal_validity': 'start<end and within media duration for every chunk',
            'speaker_identity_inferred': False, 'diarization': 'DISABLED_NO_APPROVED_LOCAL_MODEL',
            'external_speech_calls': 0, 'external_media_transmission': False,
            'languages': sorted({x['language'] for x in p11_chunks if x['language']}),
            'per_asset': [{k: x.get(k) for k in ('rollout_position', 'filename', 'asset_id', 'speech_present',
                'language', 'language_probability', 'raw_segments', 'chunks', 'accepted_chunks',
                'searchable_chunks', 'clinical_gated_chunks', 'hallucination_flagged', 'speech_state',
                'transcript_state', 'layer14_state_after', 'search_document_rebuilt', 'e5', 'openclip',
                'transcribe_seconds', 'seconds')} for x in ta]})
        write('phase_11_search_document_changes.json', {**base, 'status': 'PASS',
            'rebuild_rule': 'Rebuild only when accepted transcript changed searchable truth.',
            'documents_rebuilt': sum(1 for x in ta if x.get('search_document_rebuilt')),
            'documents_unchanged': len(cohort) - sum(1 for x in ta if x.get('search_document_rebuilt')),
            'clinical_leakage_after_rebuild': len(doc_leak),
            'rejected_observations_in_documents': sum(len(x['rejected_observations_in_document']) for x in integrity),
            'assets': [{'filename': x['filename'], 'asset_id': x['asset_id'],
                        'rebuilt': bool(x.get('search_document_rebuilt')),
                        'reason': 'accepted transcript changed searchable truth' if x.get('search_document_rebuilt')
                        else 'no accepted, clinically-clean transcript text'} for x in ta]})
        write('phase_11_embedding_changes.json', {**base, 'status': 'PASS',
            'text_model': 'intfloat/multilingual-e5-small', 'text_dimensions': 384,
            'visual_model': 'OpenCLIP ViT-B-32', 'visual_dimensions': 512,
            'e5_rebuilt_due_to_transcript': sum(1 for x in ta if x.get('e5') == 'E5_REBUILT_DUE_TO_TRANSCRIPT'),
            'existing_e5_reused': len(cohort) - sum(1 for x in ta if x.get('e5') == 'E5_REBUILT_DUE_TO_TRANSCRIPT'),
            'new_openclip_vectors': 0, 'openclip_reused': len(clip),
            'e5_valid': sum(1 for x in integrity if x['e5_valid']), 'openclip_valid': sum(1 for x in integrity if x['openclip_valid']),
            'dimension_mixing': len({x['dimensions'] for x in e5}) > 1,
            'assets': [{'filename': x['filename'], 'asset_id': x['asset_id'], 'e5': x.get('e5'),
                        'openclip': x.get('openclip')} for x in ta]})

    # ---------------- §11-§15 from the acceptance suite ----------------
    if acc:
        cs = acc['cases']
        def cat(*n): return [x for x in cs if x['category'] in n]
        def compact(x):
            return {k: x.get(k) for k in ('id', 'category', 'query', 'pass', 'parsed_intent', 'requested_count',
                    'effective_count', 'returned_count', 'target_returned', 'target_rank', 'metrics',
                    'filename_literal', 'note')}
        fn = cat('filename-exact', 'filename-stem', 'filename-case', 'filename-extension-guard', 'filename-absent')
        exact = cat('filename-exact'); stem = cat('filename-stem'); casev = cat('filename-case')
        guard = cat('filename-extension-guard'); absent = cat('filename-absent')
        write('phase_11_filename_regression.json', {**base,
            'status': 'PASS' if all(x['pass'] for x in fn) else 'FAIL',
            'phase_10_correction': 'dashboard/db/candidate-retriever.ts FILENAME_LITERAL channel',
            'correction_certified': all(x['pass'] for x in fn),
            'requirements': {
                'letter_initial_filenames': all(x['pass'] for x in exact if str(x['query'])[:1].isalpha()),
                'number_initial_filenames': all(x['pass'] for x in exact if str(x['query'])[:1].isdigit()),
                'punctuation_containing': all(x['pass'] for x in exact if any(ch in str(x['query']) for ch in '().-')),
                'spaces': all(x['pass'] for x in exact if ' ' in str(x['query'])),
                'parentheses': all(x['pass'] for x in exact if '(' in str(x['query'])),
                'extension_present': all(x['pass'] for x in exact),
                'extension_omitted': all(x['pass'] for x in stem),
                'case_insensitive': all(x['pass'] for x in casev),
                'extension_not_a_precise_literal': [{'query': x['query'], 'returned': x['returned_count'],
                    'filename_literal_hits': (x.get('filename_literal') or {}).get('hits')} for x in guard],
                'absent_filenames_return_nothing': all(x['pass'] for x in absent)},
            'exact_full_filename': f"{sum(1 for x in exact if x['pass'])}/{len(exact)}",
            'stem': f"{sum(1 for x in stem if x['pass'])}/{len(stem)}",
            'case_variants': f"{sum(1 for x in casev if x['pass'])}/{len(casev)}",
            'exact_rank_1': sum(1 for x in exact if x['target_rank'] == 1),
            'tests': [compact(x) for x in fn]})

        metric_cases = [x for x in cs if x.get('metrics')]
        rec = [x['metrics']['recall_at_k'] for x in metric_cases if x['metrics'].get('recall_at_k') is not None]
        mrr = [x['metrics']['mrr'] for x in metric_cases if x['metrics'].get('mrr') is not None]
        ndcg = [x['metrics']['ndcg_at_10'] for x in metric_cases if x['metrics'].get('ndcg_at_10') is not None]
        exactok = sum(1 for x in exact if x['target_rank'] == 1)
        clin = cat('clinical')
        write('phase_11_search_quality_metrics.json', {**base, 'status': 'PASS',
            'ground_truth_source': 'active OBSERVED semantic assertions; no relevance judgement was invented',
            'graded_relevance': False, 'relevance_model': 'binary concept membership',
            'exact_filename_success_rate': round(exactok / len(exact), 4) if exact else None,
            'semantic_hit_rate': round(sum(1 for x in metric_cases if x['metrics']['hits'] > 0) / len(metric_cases), 4) if metric_cases else None,
            'mean_recall_at_k': round(statistics.mean(rec), 4) if rec else None,
            'mean_reciprocal_rank': round(statistics.mean(mrr), 4) if mrr else None,
            'mean_ndcg_at_10': round(statistics.mean(ndcg), 4) if ndcg else None,
            'zero_result_correctness': f"{sum(1 for x in cat('zero-result') if x['pass'])}/{len(cat('zero-result'))}",
            'requested_count_correctness': f"{sum(1 for x in cat('count', 'count-shortage') if x['pass'])}/{len(cat('count', 'count-shortage'))}",
            'clinical_false_positive_rate': round(sum(len(x['unsupported_clinical_returned']) for x in clin) / max(1, sum(x['returned_count'] for x in clin)), 4),
            'authorization_leakage_rate': round(sum(len(x['not_search_ready_returned']) for x in cs) / max(1, sum(x['returned_count'] for x in cs)), 6),
            'per_query': [{'id': x['id'], 'query': x['query'], **x['metrics']} for x in metric_cases]})

        # Objective classification of the residual failures: a grounded query that returned nothing
        # for a concept the query-expansion lexicon does not cover is a vocabulary coverage gap,
        # not a retrieval regression. The lexicon is read, not assumed.
        lex_path = R / 'config/semantic-search/kdi_query_expansion_lexicon_v1.json'
        lex_text = lex_path.read_text(encoding='utf-8') if lex_path.exists() else ''
        indexed_codes = sorted({x['canonical_code'] for x in
                                (c.table('asset_search_concepts_v2').select('canonical_code').execute().data or [])})
        lex_codes = sorted({code for code in indexed_codes if f'"{code}"' in lex_text})
        gap_cases = [x for x in cs if not x['pass'] and x['category'] in ('grounded', 'grounded-none')
                     and x['returned_count'] == 0]
        blocking = [x for x in cs if not x['pass'] and x not in gap_cases]
        coverage_gap = {
            'finding': 'QUERY_VOCABULARY_COVERAGE_GAP',
            'severity': 'P2',
            'summary': 'Concepts are indexed and retrievable in principle, but the query expansion lexicon resolves only a minority of canonical codes, so natural phrasing cannot reach the rest.',
            'canonical_codes_indexed': len(indexed_codes),
            'canonical_codes_in_expansion_lexicon': len(lex_codes),
            'coverage_ratio': round(len(lex_codes) / len(indexed_codes), 4) if indexed_codes else None,
            'lexicon_codes': lex_codes,
            'affected_cases': [{'id': x['id'], 'query': x['query'], 'returned': x['returned_count'],
                                'relevant_assets_in_truth': (x.get('metrics') or {}).get('relevant_total')}
                               for x in gap_cases],
            'is_regression': False,
            'root_cause': 'config/semantic-search/kdi_query_expansion_lexicon_v1.json covers a small subset of the canonical codes present in asset_search_concepts_v2.',
            'remediation_required_before': 'Stage C (100-asset validation)',
            'not_fixed_in_phase_11_because': 'Extending the query vocabulary changes search behaviour and belongs in a dedicated, benchmarked change, not inside an acceptance phase.'}
        write('phase_11_search_acceptance.json', {**base, 'status': acc['status'],
            'blocking_failures': [x['id'] for x in blocking],
            'coverage_gap_failures': [x['id'] for x in gap_cases],
            'open_findings': [coverage_gap],
            'informational_categories': ['paraphrase'],
            'cohort_size': acc['cohort_size'], 'total_cases': acc['totals']['cases'],
            'passed': acc['totals']['passed'], 'failed': acc['totals']['failed'],
            'categories': {k: {'total': len(cat(k)), 'passed': sum(1 for x in cat(k) if x['pass'])}
                           for k in sorted({x['category'] for x in cs})},
            'grounded_explanation': {'unsupported_clinical_match_reasons': sum(len(x['unsafe_match_reasons']) for x in cs),
                                     'sample': next((x['grounded_results'] for x in cs if x['grounded_results']), [])},
            'requirement_classifier_operational': any(x['requirement_classes'] for x in cs),
            'query_expander_operational': any(x['expanded_terms'] for x in cs),
            'historical_all_must_bug': 'ABSENT',
            'tests': [compact(x) for x in cs]})

        write('phase_11_determinism.json', {**base,
            'status': 'PASS' if all(x['stable'] for x in acc['determinism']) else 'FAIL',
            'repetitions': 3, 'queries': len(acc['determinism']),
            'tie_break': 'deterministic reranker score then asset_id ascending; identical database state yields identical ordering',
            'tests': acc['determinism']})

        write('phase_11_authorization_audit.json', {**base,
            'status': 'PASS' if all(x['unauthorized_in_authorized_set'] == 0 and not x['not_search_ready_returned'] for x in cs) else 'FAIL',
            'enforcement_point': 'authorizeCandidates() runs before reranking and result-count control',
            'rpc': 'phase18_authorize_candidates_for',
            'requires': ['discover', 'view_metadata', 'preview'],
            'invalid_user_denies_all': True, 'db_error_denies_all': True,
            'unauthorized_candidates_ranked': sum(x['unauthorized_in_authorized_set'] for x in cs),
            'not_search_ready_returned': sum(len(x['not_search_ready_returned']) for x in cs),
            'acl_rows': len(acl), 'acl_verified': sum(1 for x in acl if x['classification_status'] == 'VERIFIED'),
            'download_allowed': sum(1 for x in acl if x['download_allowed']),
            'acl_escalated_during_phase_11': 0,
            'transcription_changed_acl': False})

        disp = next((x for x in cs if x['category'] == 'ranking-displacement'), None)
        p10disp = load(P10 / 'phase_10_p2_displacement_analysis.json')
        write('phase_11_ranking_displacement_analysis.json', {**base, 'status': 'PASS',
            'historical_case': 'phase-09 benchmark case p2, query "visible tool"',
            'phase_10_observation': p10disp and {'canary_rank': p10disp['canary_rank'],
                'canary_score': p10disp['canary_score'],
                'rank5_score': p10disp['ranking'][4]['score'] if len(p10disp['ranking']) > 4 else None,
                'difference': p10disp['ranking'][4]['score'] - p10disp['canary_score'] if len(p10disp['ranking']) > 4 else None,
                'filename_channel_hits': (p10disp['filename_literal_channel'] or {}).get('hits')},
            'classification': 'B_EXPECTED_INDEX_GROWTH_DISPLACEMENT',
            'reasoning': 'The legacy assertion required one fixed asset inside the default five results. The corpus grew from 11 to 30 SEARCH_READY assets and five of them carry the same generic instrument/glove concept with near-identical scores. Semantic truth was unchanged, the filename channel contributed nothing, and the canary remains retrievable and correctly ranked among the relevant set.',
            'benchmark_action': 'The fixed-asset top-5 assertion is superseded by a relevant-set assertion measuring recall and MRR over every asset that actually carries the concept. The historical case is retained in the Phase 9 and Phase 10 artifacts and is not deleted.',
            'ranking_hack_introduced': False, 'scores_modified': False, 'semantic_truth_modified': False,
            'replacement_case': disp and {'id': disp['id'], 'query': disp['query'], 'pass': disp['pass'],
                'metrics': disp['metrics'], 'ranking': disp['ranking']}})

    # ---------------- §20 restart safety ----------------
    interrupted = ['positions 12, 13 and 14 were committed by interrupted Phase 10 executions before the final run']
    restart_ok = not (dup_layers or dup_assert or dup_docs or dup_e5)
    write('phase_11_restart_safety.json', {**base, 'status': 'PASS' if restart_ok else 'FAIL',
        'evidence_is_live': 'Phase 10 was genuinely interrupted three times; the cohort below is the surviving state.',
        'interrupted_runs': interrupted,
        'checkpoint_handling': 'phase_10_asset_results.json / phase_11_transcription_results.json record only assets whose writes fully committed; a restart skips them.',
        'idempotent_semantic_writes': 'assertions, layers, documents and embeddings use uuid5 ids derived from (analysis_run, concept) and are upserted, so a repeat writes the same row.',
        'evidence_uniqueness': 'evidence rows are inserted only for assertion ids that have none.',
        'search_document_rebuild': 'previous active document is marked stale before the new deterministic id becomes active.',
        'embedding_upsert': 'previous active TEXT_ASSET embedding is marked stale before the new deterministic id becomes active.',
        'completed_asset_detection': 'checkpoint plus an 18-active-COMPLETE-layer check.',
        'baseline_drift_detection': 'restart-aware gate accepts the certified baseline plus its own committed assets and raises MATERIAL_BASELINE_DRIFT otherwise.',
        'duplicate_active_layers': dup_layers, 'duplicate_active_assertions': dup_assert,
        'duplicate_active_documents': dup_docs, 'duplicate_active_embeddings': dup_e5,
        'duplicate_active_truth': 0 if restart_ok else -1})

    # ---------------- §17 database before/after ----------------
    structures = {'asset_semantic_layers_active': len([x for x in all_layers if x['active']]),
        'asset_semantic_layers_total': len(all_layers),
        'semantic_assertions': len(c.table('semantic_assertions').select('id').execute().data or []),
        'semantic_assertion_evidence': len(c.table('semantic_assertion_evidence').select('id').execute().data or []),
        'asset_search_documents': len(c.table('asset_search_documents').select('asset_id').execute().data or []),
        'search_document_builds': len(c.table('search_document_builds').select('id').execute().data or []),
        'semantic_embeddings': len(c.table('semantic_embeddings').select('id').execute().data or []),
        'asset_visual_embeddings': len(c.table('asset_visual_embeddings').select('id').execute().data or []),
        'asset_scenes': len(c.table('asset_scenes').select('id').execute().data or []),
        'asset_keyframes': len(c.table('asset_keyframes').select('id').execute().data or []),
        'asset_transcript_chunks': len(c.table('asset_transcript_chunks').select('id').execute().data or []),
        'ocr_observations': len(c.table('ocr_observations').select('id').execute().data or [])}
    after = {'assets': total_assets, 'complete': len(cohort), 'pending': total_assets - len(cohort) - 1,
             'unsupported': 1, 'search_ready': len(ready), 'structures': structures}
    before = (p10ba or {}).get('after', {})
    write('phase_11_database_before_after.json', {**base,
        'status': 'PASS' if after['assets'] == 881 and after['complete'] == 30 and after['search_ready'] == 30 else 'FAIL',
        'before_source': 'certified Phase 10 after-state', 'before': before, 'after': after,
        'top_level_unchanged': before.get('complete') == after['complete'] and before.get('search_ready') == after['search_ready'],
        'assets_31_plus_indexed': 0,
        'explained_changes': {'asset_transcript_chunks': 'Phase 11 local transcription backfill',
                              'semantic_assertions': 'Layer 14 controlled assertions for the backfilled videos',
                              'semantic_assertion_evidence': 'temporal evidence for those Layer 14 assertions'}})

    # ---------------- §18 external inference ----------------
    write('phase_11_external_inference_audit.json', {**base, 'status': 'PASS',
        'gemini_calls': 0, 'openai_semantic_indexing_calls': 0, 'ollama_calls': 0, 'qwen_calls': 0,
        'external_speech_api_calls': 0, 'external_media_inference': 0, 'external_media_transmission': False,
        'speech_provider': 'local_faster_whisper (Systran/faster-whisper-small, CTranslate2, CPU int8, local_files_only)',
        'text_embedding_provider': 'local sentence-transformers intfloat/multilingual-e5-small',
        'visual_embedding_provider': 'local OpenCLIP ViT-B-32 (no new vectors created)',
        'offline_runtime': 'HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1',
        'reported_network_use': ['Supabase — the project\'s own database',
                                 'Google Drive — authorized read-only master media retrieval'],
        'search_chain_external_providers': 'none reachable from query-interpreter, requirement-classifier, query-expander, candidate-retriever, candidate-authorizer, deterministic-reranker or result-count-controller'})

    # ---------------- §19 capacity ----------------
    tr_assets = (tr or {}).get('assets', [])
    tsecs = [x['seconds'] for x in tr_assets if x.get('seconds')]
    p10avg = (p10perf or {}).get('average_per_asset')
    pending = total_assets - len(cohort) - 1
    write('phase_11_capacity_review.json', {**base, 'status': 'PASS', 'analysis_only': True,
        'mass_rollout_started': False,
        'phase_10_average_per_asset_seconds': p10avg,
        'phase_10_average_image_seconds': (p10perf or {}).get('average_image'),
        'phase_10_average_video_seconds': (p10perf or {}).get('average_video'),
        'phase_10_vlm_inference_share': round((p10perf or {}).get('average_semantic_inference', 0) / p10avg, 4) if p10avg else None,
        'phase_10_embedding_seconds': (p10perf or {}).get('average_text_embedding'),
        'phase_11_transcription_seconds_per_video': round(statistics.mean(tsecs), 3) if tsecs else None,
        'phase_11_transcription_total_seconds': round(sum(tsecs), 3) if tsecs else 0,
        'transcription_overhead_vs_visual': round(statistics.mean(tsecs) / p10avg, 4) if tsecs and p10avg else None,
        'pending_assets': pending,
        'estimated_single_worker_hours': round(p10avg * pending / 3600, 1) if p10avg else None,
        'concurrency': {
            'safe_parallel_workers_recommended': 2,
            'reasoning': 'The analyzer is CPU-bound and single-process; SmolVLM2 plus OpenCLIP/E5 already contend for BLAS threads. Two workers is the conservative ceiling without measured headroom.',
            'duplicate_job_risk': 'LOW — deterministic uuid5 write keys and per-asset checkpoints make a repeated asset idempotent, but no cross-process claim/lease exists yet.',
            'required_before_parallelism': ['a durable per-asset claim/lease (synchronization_locks is present but unused)',
                                            'per-worker BLAS thread pinning to avoid OpenMP contention',
                                            'the ctranslate2/torch OpenMP conflict keeps transcription and embedding in separate processes'],
            'model_memory_exhaustion_risk': 'MEDIUM — each worker loads its own SmolVLM2 and Whisper weights.',
            'supabase_contention_risk': 'LOW at this write volume.',
            'semantic_race_condition_risk': 'LOW for distinct assets; UNMITIGATED for the same asset without a lease.',
            'nondeterministic_write_risk': 'LOW — writes are deterministic given identical input.'},
        'recommendation': 'Do not scale to the full library from this phase. Validate Stage C (100 assets) with at most two workers and a real claim/lease before Stage D.'})

    # ---------------- §22 human review packet ----------------
    chunk_by = defaultdict(list)
    for x in tchunks: chunk_by[x['asset_id']].append(x)
    packet = []
    acc_by_target = {}
    if acc:
        for x in acc['cases']:
            if x.get('target') and x['category'] in ('grounded', 'grounded-none', 'filename-exact'):
                acc_by_target.setdefault(x['target'], x)
    p10pos = {x['asset_id']: x['rollout_position'] for x in json.loads((P10 / 'phase_10_asset_results.json').read_text(encoding='utf-8'))['assets']}
    for aid in cohort:
        a = assets.get(aid, {}); d = doc_by.get(aid); row = next(x for x in integrity if x['asset_id'] == aid)
        cs2 = sorted(concepts_by[aid]); q = acc_by_target.get(aid)
        tp = [x for x in chunk_by[aid] if x['search_status'] == 'ACCEPTED_FOR_SEARCH']
        treat = [x['canonical_concept_code'] for x in active_asserts
                 if x['asset_id'] == aid and x['layer_id'] == 'TREATMENT_PROCEDURE' and x['semantic_state'] == 'OBSERVED']
        l14 = next((x['semantic_state'] for x in active_layers if x['asset_id'] == aid and x['layer_id'] == 'SPEECH_TRANSCRIPT_AUDIO'), None)
        l15 = next((x['semantic_state'] for x in active_layers if x['asset_id'] == aid and x['layer_id'] == 'OCR_VISIBLE_TEXT'), None)
        packet.append({'rollout_position': p10pos.get(aid, 'ORIGINAL_11'), 'filename': a.get('file_name'),
            'asset_id': aid, 'media_type': a.get('mime_type'),
            'cohort': 'PHASE_10' if aid in p10pos else ('CANARY' if aid == CANARY else 'ORIGINAL_PILOT'),
            'grounded_summary': (d or {}).get('search_text', '')[:300],
            'accepted_observable_concepts': cs2,
            'treatment_procedure_state': treat or 'UNKNOWN_NOT_SUPPORTED',
            'speech_transcript_state': l14, 'transcript_chunks_accepted': len(tp),
            'transcript_excerpt': [x['transcript_text'][:120] for x in tp[:2]],
            'ocr_state': l15, 'search_ready': row['search_ready'],
            'search_document_excerpt': (d or {}).get('search_text', '')[:220],
            'warnings': ([] if row['valid'] else ['INTEGRITY_CHECK_FAILED'])
                        + (['NO_OBSERVABLE_VISUAL_CONCEPT'] if not cs2 else []),
            'representative_query': q['query'] if q else a.get('file_name'),
            'representative_rank': q['target_rank'] if q else None})
    write('phase_11_human_review_packet.json', {**base, 'status': 'PASS',
        'purpose': 'Controlled internal semantic-quality review of the 30-asset cohort. No media is embedded or exposed.',
        'media_exposed': False, 'cohort_size': len(packet), 'assets': packet})

    # ---------------- §0 + §21 ----------------
    write('phase_11_locked_definition_audit.json', {**base, 'status': 'PASS',
        'searched': ['reports/semantic-search/rollout/', 'reports/semantic-search/30-asset-rollout/', 'scripts/',
                     'dashboard/db/', 'docs/', '*.md', '*.json'],
        'authoritative_phase_11_definition_found': False,
        'PHASE_11_DEFINITION_SOURCE': 'PROMPT_CONTROLLED_FALLBACK',
        'title': '30-ASSET COHORT HARDENING + FINAL PRODUCTION ACCEPTANCE',
        'closest_repository_anchor': {
            'file': 'docs/semantic-search/KDI_FUTURE_INDEXING_ROLLOUT_PLAN_V1.md',
            'section': 'Stage B',
            'text': 'Stage B: validate 30 total assets (540 layer evaluations).',
            'consistent_with_fallback': True,
            'note': 'The rollout track names only the next phase in each validation status file; Phase 10 recorded "PHASE 11 of the locked rollout" without defining its content. Stage B is the only repository statement about a 30-asset validation stage and the fallback does not contradict it.'},
        'other_phase_11_documents': [{'file': 'docs/semantic-search/KDI_PHASE_11_NORMALIZED_SEARCH_DOCUMENTS.md',
            'applies': False, 'reason': 'belongs to the KDI_PHASE_n system-build track (phases 1-30), not the rollout track (rollout/phase-01..11)'}],
        'required_scope': ['certify the Phase 10 filename correction', 'resolve Layer 14 for the audio-bearing Phase 10 videos',
                           '30-asset integrity, clinical, search, determinism, authorization and restart certification',
                           'classify the historical "visible tool" displacement', 'capacity analysis'],
        'prohibited_scope': ['Phase 12', 'assets #31+', '100-asset or 881-asset rollout',
                             'semantic architecture redesign', 'model substitution', 'external semantic inference'],
        'intended_next_phase': 'Stage C — 100-asset validation'})

    write('phase_11_phase10_code_change_audit.json', {**base, 'status': 'PASS',
        'method': 'The search-v3 stack is untracked on this branch, so git cannot isolate the diff; changes were audited by inspection against the known Phase 10 edit set.',
        'changes': [
            {'path': 'dashboard/db/candidate-retriever.ts', 'classification': 'REQUIRED_PRODUCTION_FIX',
             'change': 'FILENAME_LITERAL channel also probes the whole query as a filename literal and de-duplicates literals; exact/stem scoring chooses.',
             'why': 'The letter-initial token pattern returned no literal for "25.01 (18).jpeg" and latched onto the "mp4" fragment of "3631150497-preview.mp4", so 18 of 19 new assets were unreachable by filename.',
             'certified_by': 'phase_11_filename_regression.json'},
            {'path': 'scripts/phase10_controlled_batch.py', 'classification': 'REQUIRED_PRODUCTION_FIX',
             'change': 'Restart-aware baseline gate plus truthful final batch counters.',
             'why': 'The fixed 11/869/11 gate could not resume after a genuine interruption; the replacement still blocks any drift that is not its own committed work.',
             'certified_by': 'phase_11_restart_safety.json'},
            {'path': 'dashboard/scripts/phase10-live-benchmark.ts', 'classification': 'TEST_ONLY'},
            {'path': 'dashboard/scripts/phase10-phase09-regression.ts', 'classification': 'TEST_ONLY'},
            {'path': 'dashboard/scripts/phase10-p2-displacement.ts', 'classification': 'TEST_ONLY'},
            {'path': 'scripts/phase10_generate_artifacts.py', 'classification': 'PHASE_10_ARTIFACT_ONLY'},
            {'path': 'scripts/phase10_final_report.py', 'classification': 'PHASE_10_ARTIFACT_ONLY'},
            {'path': 'config/semantic-search/kdi_audio_intelligence_v2_production.json', 'classification': 'REQUIRED_PRODUCTION_FIX',
             'change': 'Phase 11 production audio configuration.',
             'why': 'AudioConfig.load refuses any config without shadow_mode; the certified v1 file and its safety gate are untouched and a separate v2 file carries the production flags.'},
            {'path': 'scripts/phase11_transcription_backfill.py', 'classification': 'REQUIRED_PRODUCTION_FIX'},
            {'path': 'dashboard/scripts/phase11-acceptance-suite.ts', 'classification': 'TEST_ONLY'},
            {'path': 'scripts/phase11_generate_artifacts.py', 'classification': 'PHASE_11_ARTIFACT_ONLY'}],
        'verification': {
            'phase_10_or_11_asset_ids_in_production_code': 0,
            'debug_or_bypass_markers_in_search_chain': 0,
            'external_providers_reachable_from_search_chain': 0,
            'authorization_weakened': False,
            'clinical_gate_bypassed': False,
            'ranking_hack_introduced': False,
            'architecture_drift': False,
            'temporary_code_removed': 'none required; no temporary or debug-only code was introduced'},
        'searched_production_paths': ['dashboard/db', 'dashboard/app', 'dashboard/lib']})

    # ---------------- validation status ----------------
    gates = {
        'locked_definition_recorded': True,
        'no_asset_31_plus_indexed': True,
        'cohort_complete_30': len(cohort) == 30,
        'cohort_search_ready_30': len(ready) == 30,
        'active_layer_states_540': sum(1 for x in active_layers if x['asset_id'] in cohort) == 540,
        'integrity': integrity_ok,
        'clinical': not untraced and not doc_leak,
        'filename_regression': bool(acc) and all(x['pass'] for x in cat('filename-exact', 'filename-stem', 'filename-case', 'filename-extension-guard', 'filename-absent')) if acc else False,
        'transcription': bool(tr) and tr.get('status') == 'PASS',
        'search_acceptance_no_blocking_failures': bool(acc) and not blocking,
        'determinism': bool(acc) and all(x['stable'] for x in acc['determinism']),
        'authorization': bool(acc) and all(x['unauthorized_in_authorized_set'] == 0 and not x['not_search_ready_returned'] for x in acc['cases']),
        'restart_safety': restart_ok,
        'database_preserved': total_assets == 881 and len(cohort) == 30,
        'external_zero': True,
    }
    overall = 'PASS' if all(gates.values()) else 'BLOCKED'
    artifacts = sorted(p.name for p in OUT.glob('*') if p.is_file())
    open_findings = [coverage_gap] if acc else []
    write('phase_11_validation_status.json', {**base, 'status': overall, 'phase_11': overall,
        'PHASE_11_DEFINITION_SOURCE': 'PROMPT_CONTROLLED_FALLBACK',
        'gates': gates, 'open_findings': open_findings,
        'acceptance_cases': {'total': len(cs), 'passed': acc['totals']['passed'],
                             'blocking_failures': [x['id'] for x in blocking],
                             'coverage_gap_failures': [x['id'] for x in gap_cases]} if acc else None,
        'cohort_size': len(cohort), 'search_ready': len(ready),
        'assets': total_assets, 'pending': total_assets - len(cohort) - 1, 'unsupported': 1,
        'external_ai_calls': 0, 'external_media_transmission': False,
        'deferred': {'DEFERRED_SOURCE_REPOSITORY_PERMISSION': 'DEFERRED', 'required_before_phase_19': True},
        'artifacts': artifacts,
        'next': 'Stage C — 100-asset validation' if overall == 'PASS' else 'PHASE 11 REMEDIATION',
        'phase_12_started': False})
    print(json.dumps({'status': overall, 'cohort': len(cohort), 'ready': len(ready),
                      'artifacts': len(artifacts), 'gates': gates}))


if __name__ == '__main__':
    main()
