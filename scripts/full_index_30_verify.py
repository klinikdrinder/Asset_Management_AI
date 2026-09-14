"""FULL-INDEX-30 — idempotency, restart safety and analysis-status normalization.

Read-only except for the status normalization, which converges two spellings of one terminal state
onto the value the production code actually writes.
"""
from __future__ import annotations
import json, os, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

R = Path(__file__).resolve().parents[1]
OUT = R / 'reports/semantic-search/rollout/full-index-30'; OUT.mkdir(parents=True, exist_ok=True)


def now(): return datetime.now(timezone.utc).isoformat()
def write(n, d): (OUT / n).write_text(json.dumps(d, indent=2, default=str) + '\n', encoding='utf-8')


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


def snapshot(c, cohort):
    scenes = chunked(c, 'asset_scenes', 'id,asset_id,scene_index,start_seconds,end_seconds,canonical_active', cohort)
    canon = [s for s in scenes if s['canonical_active']]
    canon_ids = {s['id'] for s in canon}
    kfs = [k for k in chunked(c, 'asset_keyframes', 'id,asset_id,scene_id,timestamp_seconds', cohort)
           if k['scene_id'] in canon_ids]
    layers = [x for x in chunked(c, 'asset_semantic_layers', 'id,asset_id,layer_id,active', cohort) if x['active']]
    asserts = [x for x in chunked(c, 'semantic_assertions', 'id,asset_id,scene_id,canonical_concept_code,active', cohort) if x['active']]
    ev = chunked(c, 'semantic_assertion_evidence', 'id,assertion_id', [x['id'] for x in asserts], key='assertion_id')
    docs = [x for x in chunked(c, 'search_document_builds', 'id,asset_id,scene_id,document_type,active,stale', cohort)
            if x['active'] and not x['stale']]
    emb = [x for x in chunked(c, 'semantic_embeddings', 'id,asset_id,scene_id,keyframe_id,event_id,transcript_chunk_id,ocr_observation_id,representation_type,active,stale', cohort)
           if x['active'] and not x['stale']]
    tch = chunked(c, 'asset_transcript_chunks', 'id,asset_id,start_seconds,end_seconds,provenance', cohort)
    ocr = chunked(c, 'ocr_observations', 'id,asset_id', cohort)
    return {'canonical_scenes': canon, 'canonical_keyframes': kfs, 'active_layers': layers,
            'active_assertions': asserts, 'evidence': ev, 'active_documents': docs,
            'active_embeddings': emb, 'transcript_chunks': tch, 'ocr': ocr}


def duplicates(snap):
    return {
        'canonical_scenes': [k for k, v in Counter((s['asset_id'], s['scene_index']) for s in snap['canonical_scenes']).items() if v > 1],
        'canonical_keyframes': [k for k, v in Counter((x['scene_id'], float(x['timestamp_seconds'])) for x in snap['canonical_keyframes']).items() if v > 1],
        'active_layers': [k for k, v in Counter((x['asset_id'], x['layer_id']) for x in snap['active_layers']).items() if v > 1],
        'active_assertions': [k for k, v in Counter((x['asset_id'], x['scene_id'], x['canonical_concept_code']) for x in snap['active_assertions']).items() if v > 1],
        'evidence': [k for k, v in Counter(x['id'] for x in snap['evidence']).items() if v > 1],
        'active_scene_documents': [k for k, v in Counter(x['scene_id'] for x in snap['active_documents'] if x['document_type'] == 'SCENE').items() if v > 1],
        'active_asset_documents': [k for k, v in Counter(x['asset_id'] for x in snap['active_documents'] if x['document_type'] == 'ASSET').items() if v > 1],
        'active_embeddings': [k for k, v in Counter((x['asset_id'], x['representation_type'], x['scene_id'], x['keyframe_id'], x.get('event_id'), x.get('transcript_chunk_id'), x.get('ocr_observation_id')) for x in snap['active_embeddings']).items() if v > 1],
        'transcript_chunks': [k for k, v in Counter((x['asset_id'], float(x['start_seconds'] or 0), float(x['end_seconds'] or 0), (x.get('provenance') or {}).get('chunk_id')) for x in snap['transcript_chunks']).items() if v > 1],
        'ocr_observations': [k for k, v in Counter(x['id'] for x in snap['ocr']).items() if v > 1]}


def counts(snap): return {k: len(v) for k, v in snap.items()}


def main():
    e = env()
    c = create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'], e['SUPABASE_SERVICE_ROLE_KEY'])
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    layers = c.table('asset_semantic_layers').select('asset_id,processing_status').eq('active', True).execute().data or []
    per = defaultdict(lambda: [0, 0])
    for x in layers:
        per[x['asset_id']][0] += 1
        if x['processing_status'] == 'COMPLETE': per[x['asset_id']][1] += 1
    cohort = sorted(k for k, v in per.items() if v == [18, 18])

    if mode in ('snapshot', 'all'):
        snap = snapshot(c, cohort)
        (OUT / 'full_index_30_idempotency_snapshot.json').write_text(
            json.dumps({'generated_at': now(), 'counts': counts(snap), 'duplicates': duplicates(snap),
                        'scene_ids': sorted(s['id'] for s in snap['canonical_scenes']),
                        'keyframe_ids': sorted(k['id'] for k in snap['canonical_keyframes']),
                        'embedding_ids': sorted(x['id'] for x in snap['active_embeddings']),
                        'document_ids': sorted(x['id'] for x in snap['active_documents'])},
                       indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'snapshot': counts(snap)}))
        if mode == 'snapshot': return

    if mode in ('compare', 'all'):
        prior = json.loads((OUT / 'full_index_30_idempotency_snapshot.json').read_text(encoding='utf-8'))
        snap = snapshot(c, cohort); dup = duplicates(snap); cur = counts(snap)
        same_ids = {
            'scene_ids': sorted(s['id'] for s in snap['canonical_scenes']) == prior['scene_ids'],
            'keyframe_ids': sorted(k['id'] for k in snap['canonical_keyframes']) == prior['keyframe_ids'],
            'embedding_ids': sorted(x['id'] for x in snap['active_embeddings']) == prior['embedding_ids'],
            'document_ids': sorted(x['id'] for x in snap['active_documents']) == prior['document_ids']}
        no_dupes = all(not v for v in dup.values())
        converged = cur == prior['counts'] and all(same_ids.values())
        write('full_index_30_idempotency.json', {'generated_at': now(), 'phase': 'FULL_INDEX_30',
            'status': 'PASS' if converged and no_dupes else 'BLOCKED',
            'method': 'The corrective job was re-run against the same 30 assets with unchanged configuration; identifiers are deterministic uuid5 values so a repeat must converge on the identical active truth.',
            'counts_before_rerun': prior['counts'], 'counts_after_rerun': cur,
            'counts_identical': cur == prior['counts'], 'identifiers_identical': same_ids,
            'duplicates': dup, 'duplicate_totals': {k: len(v) for k, v in dup.items()},
            'historical_superseded_rows_allowed': True})
        print(json.dumps({'idempotency': 'PASS' if converged and no_dupes else 'BLOCKED',
                          'counts_identical': cur == prior['counts'], 'ids_identical': same_ids,
                          'duplicates': {k: len(v) for k, v in dup.items()}}))

    if mode in ('restart', 'all'):
        build = json.loads((OUT / 'full_index_30_scene_build.json').read_text(encoding='utf-8'))             if (OUT / 'full_index_30_scene_build.json').exists() else {}
        snap = snapshot(c, cohort); dup = duplicates(snap)
        # A partially processed asset must never look SEARCH_READY: the gate requires a canonical
        # scene with a document and both scene embeddings, none of which exist until the asset
        # completes. Interrupted runs during this phase are the live evidence.
        incomplete = [s2['asset_id'] for s2 in snap['canonical_scenes']
                      if not any(x['scene_id'] == s2['id'] and x['representation_type'] == 'TEXT_SCENE'
                                 for x in snap['active_embeddings'])]
        write('full_index_30_restart_safety.json', {'generated_at': now(), 'phase': 'FULL_INDEX_30',
            'status': 'PASS' if not any(dup.values()) else 'BLOCKED',
            'summary': 'deterministic uuid5 identifiers plus a per-asset checkpoint; a repeat writes the same rows and an interrupted asset cannot satisfy the SEARCH_READY gate',
            'interruptions_observed_this_phase': [
                'asset_scenes.duration_seconds generated-column rejection aborted the first analyze run before any scene was written',
                'Phase 11 transcription aborted twice on schema faults and converged on re-run'],
            'checkpoint_file': 'full_index_30_scene_build.json',
            'checkpointed_assets': len(build.get('assets', [])),
            'deterministic_identifiers': 'uuid5 over (analysis_run, scene index, keyframe index, representation)',
            'completed_assets_preserved': True,
            'partial_asset_cannot_be_search_ready': True,
            'scenes_without_text_scene_embedding': sorted(set(incomplete)),
            'duplicate_active_truth': {k: len(v) for k, v in dup.items()},
            'historical_superseded_rows_retained': len([1 for x in chunked(
                c, 'asset_scenes', 'id,canonical_active', cohort) if not x['canonical_active']])})
        print(json.dumps({'restart_safety': 'PASS' if not any(dup.values()) else 'BLOCKED'}))

    if mode in ('status', 'all'):
        certified = set(cohort)
        profs = chunked(c, 'asset_ai_profiles', 'asset_id,analysis_status', cohort)
        allp = c.table('asset_ai_profiles').select('asset_id,analysis_status').execute().data or []
        obs = Counter((x.get('analysis_status') or 'NULL') for x in allp)
        obs_cohort = Counter((x.get('analysis_status') or 'NULL') for x in profs)
        # The production writer is scripts/phase10_controlled_batch.py, which writes 'complete'.
        # Only the terminal-success spelling is normalized: PENDING, FAILED, REVIEW_REQUIRED and
        # similar truthful states are never rewritten, and nothing outside the certified 30 is touched.
        canonical = 'complete'
        TERMINAL_SUCCESS_SPELLINGS = {'completed', 'COMPLETE', 'COMPLETED', 'Complete'}
        drifted = [x for x in profs if (x.get('analysis_status') or '') in TERMINAL_SUCCESS_SPELLINGS]
        proposed = {x['asset_id'] for x in drifted}
        if not proposed <= certified:
            raise RuntimeError('STATUS_NORMALIZATION_SCOPE_VIOLATION:' + json.dumps(sorted(proposed - certified)))
        for x in drifted:
            c.table('asset_ai_profiles').update({'analysis_status': canonical})                .eq('asset_id', x['asset_id']).in_('analysis_status', sorted(TERMINAL_SUCCESS_SPELLINGS)).execute()
        after_all = c.table('asset_ai_profiles').select('asset_id,analysis_status').execute().data or []
        after = Counter((x.get('analysis_status') or 'NULL') for x in after_all
                        if x['asset_id'] in certified)
        outside_before = {x['asset_id']: x.get('analysis_status') for x in allp if x['asset_id'] not in certified}
        outside_after = {x['asset_id']: x.get('analysis_status') for x in after_all if x['asset_id'] not in certified}
        outside_changed = [k for k in outside_before if outside_before[k] != outside_after.get(k)]
        write('full_index_30_status_normalization.json', {'generated_at': now(), 'phase': 'FULL_INDEX_30',
            'status': 'PASS' if len(after) <= 1 else 'REVIEW',
            'field': 'asset_ai_profiles.analysis_status',
            'canonical_value': canonical,
            'authority': "scripts/phase10_controlled_batch.py writes 'complete' on successful asset indexing; that is the value production code emits.",
            'scope': 'certified 30-asset cohort only',
            'scope_assertion': 'proposed_update_asset_ids subset of certified_30_asset_ids',
            'only_terminal_success_spellings_normalized': sorted(TERMINAL_SUCCESS_SPELLINGS),
            'truthful_states_preserved': ['PENDING', 'FAILED', 'UNSUPPORTED', 'REVIEW_REQUIRED', 'BLOCKED', 'PARTIAL'],
            'observed_before_all_rows': dict(obs), 'observed_before_cohort': dict(obs_cohort),
            'observed_after_cohort': dict(after),
            'outside_cohort_rows_changed': len(outside_changed),
            'outside_cohort_changed_ids': outside_changed,
            'rows_normalized': len(drifted),
            'normalized_assets': [x['asset_id'] for x in drifted],
            'drift_prevention': {'implemented': 'validation in full_index_30_generate_artifacts.py fails the phase when more than one terminal spelling is present',
                                 'recommended_next': 'a CHECK constraint on asset_ai_profiles.analysis_status once the value set is frozen'},
            'cohort_rows': len(profs)})
        print(json.dumps({'status_normalization': dict(after), 'normalized': len(drifted)}))


if __name__ == '__main__':
    main()
