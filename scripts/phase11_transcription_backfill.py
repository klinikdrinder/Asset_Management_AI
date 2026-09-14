"""Phase 11 targeted local transcription backfill.

Scope is exactly the Phase 10 audio-bearing videos whose Layer 14 is still UNKNOWN. Reuses the
certified local audio chain (kdi_media.audio_intelligence) with a production configuration; the
certified v1 shadow config and its safety gate are untouched. No external speech service is used
and no media leaves the machine. Restart-safe: every write is keyed deterministically.

Two stages, deliberately separate processes. CTranslate2 (faster-whisper) and PyTorch
(sentence-transformers) both link libiomp5md.dll and abort when loaded together, and the documented
KMP_DUPLICATE_LIB_OK override is explicitly unsafe for numerical correctness, so it is not used.

    python scripts/phase11_transcription_backfill.py transcribe
    python scripts/phase11_transcription_backfill.py rebuild
"""
from __future__ import annotations
import hashlib, json, math, os, re, shutil, struct, subprocess, sys, tempfile, time, unicodedata, uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'src'))
from kdi_media.audio_intelligence import (canonical_fingerprint, extract_audio, wav_metadata, energy_vad,
                                          build_chunks, file_sha256)

OUT = R / 'reports/semantic-search/rollout/phase-11'; OUT.mkdir(parents=True, exist_ok=True)
P10 = R / 'reports/semantic-search/rollout/phase-10'
CONFIG = R / 'config/semantic-search/kdi_audio_intelligence_v2_production.json'
CKPT = OUT / 'phase_11_transcription_results.json'

SPEC = 'kdi_semantic_18_layer_v1'; SPEC_FP = '6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7'
ONT = 'KDI_SEMANTIC_V2'; PROC = 'kdi_audio_intelligence_v2'
EMBV = 'kdi_text_embedding_v1_spec_locked'
E5 = 'intfloat/multilingual-e5-small'; E5VER = 'hf-main-pinned-runtime-v1'
BUNDLE = 'kdi_embedding_bundle_v1_spec_locked'; TNORM = 'unicode_nfkc_whitespace_v1'
LAYER = 'SPEECH_TRANSCRIPT_AUDIO'
UNSAFE = ('surgery', 'procedure', 'treatment', 'hair transplant', 'fue', 'implantation', 'extraction',
          'graft harvesting', 'graft placement', 'prp', 'laser treatment', 'injection', 'graft', 'grafts')
NS = uuid.UUID('7b2f1c34-9d18-4a55-8f0e-2c6b41d7ae90')


def now(): return datetime.now(timezone.utc).isoformat()
def uid(seed): return str(uuid.uuid5(NS, seed))
def sha(*xs): return hashlib.sha256('\x1f'.join(str(x) for x in xs).encode()).hexdigest()


def env():
    e = {}
    for f in (R / '.env', R / '.env.local', R / 'dashboard/.env.local'):
        if f.exists():
            e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ)
    return e


def client():
    e = env()
    return create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'], e['SUPABASE_SERVICE_ROLE_KEY']), e


def load_config():
    v = json.loads(CONFIG.read_text(encoding='utf-8'))
    if v.get('processor_version') != PROC: raise RuntimeError('AUDIO_PROCESSOR_VERSION_MISMATCH')
    if v.get('shadow_mode') or not v.get('production_database_writes'): raise RuntimeError('PRODUCTION_CONFIG_EXPECTED')
    if v.get('external_media_transmission') or v.get('external_speech_services'): raise RuntimeError('EXTERNAL_SPEECH_PROHIBITED')
    if v['speech_to_text']['provider'] != 'local_faster_whisper': raise RuntimeError('NON_LOCAL_STT_PROHIBITED')
    return v, canonical_fingerprint(v)


def confidence_from_logprob(value):
    if not isinstance(value, (int, float)): return None, None
    return round(max(0.0, min(1.0, math.exp(float(value)))), 3), 'PROVIDER_LOGPROB_DERIVED'


def clinical_terms(text):
    low = ' ' + ' '.join(str(text).lower().split()) + ' '
    return sorted({t for t in UNSAFE if t in low})


def candidates(c, force=False):
    """Scope is fixed: the Phase 10 videos carrying an audio stream. Normally only those whose
    Layer 14 is still UNKNOWN are selected. `force` re-runs the same bounded set when the acceptance
    policy itself changed, so an earlier verdict is re-decided rather than left standing."""
    p10 = json.loads((P10 / 'phase_10_asset_results.json').read_text(encoding='utf-8'))['assets']
    audio = [x for x in p10 if x.get('media_type') == 'VIDEO'
             and (x.get('technical_metadata') or {}).get('audio_present') is True]
    ids = [x['asset_id'] for x in audio]
    rows = c.table('asset_semantic_layers').select('asset_id,semantic_state').in_('asset_id', ids)\
        .eq('layer_id', LAYER).eq('active', True).execute().data or []
    state = {x['asset_id']: x['semantic_state'] for x in rows}
    return audio, state, (audio if force else [x for x in audio if state.get(x['asset_id']) == 'UNKNOWN'])


# ---------------------------------------------------------------- stage 1
def transcribe_stage(force=False):
    started = time.time(); cfg, cfg_fp = load_config(); c, e = client()
    from faster_whisper import WhisperModel
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

    audio, state, cands = candidates(c, force)
    ids = [x['asset_id'] for x in audio]
    assets = {x['id']: x for x in (c.table('assets').select('id,file_name,content_hash,checksum_sha256,mime_type')
                                   .in_('id', ids).execute().data or [])}
    dests = {x['asset_id']: x for x in (c.table('asset_destinations').select('asset_id,destination_google_file_id')
             .in_('asset_id', ids).eq('upload_status', 'VERIFIED').execute().data or [])}
    (OUT / 'phase_11_transcription_candidate_manifest.json').write_text(json.dumps({
        'status': 'PASS', 'generated_at': now(), 'phase': 11,
        'scope_rule': 'Phase 10 videos with an audio stream whose active Layer 14 state is UNKNOWN.',
        'phase_10_videos': 9, 'audio_bearing': len(audio), 'selected': len(cands),
        'processor_version': PROC, 'configuration_fingerprint': cfg_fp,
        'stt': {'provider': 'local_faster_whisper', 'model': 'small', 'device': cfg['speech_to_text']['device'],
                'compute_type': cfg['speech_to_text']['compute_type'], 'offline': True},
        'assets': [{'rollout_position': x['rollout_position'], 'asset_id': x['asset_id'], 'filename': x['filename'],
                    'audio_present': True, 'layer14_state_before': state.get(x['asset_id']),
                    'duration_seconds': (x.get('technical_metadata') or {}).get('duration_seconds'),
                    'sha256': (assets.get(x['asset_id']) or {}).get('content_hash'),
                    'master_media_reference': (dests.get(x['asset_id']) or {}).get('destination_google_file_id'),
                    'selected': state.get(x['asset_id']) == 'UNKNOWN'} for x in audio]}, indent=2) + '\n',
        encoding='utf-8')
    if not cands:
        print(json.dumps({'status': 'PASS', 'selected': 0})); return

    results = []
    if CKPT.exists():
        results = [x for x in json.loads(CKPT.read_text(encoding='utf-8')).get('assets', []) if x.get('status') == 'COMPLETE']
    done = {x['asset_id'] for x in results}

    snaps = sorted((Path.home() / '.cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots').glob('*'))
    if not snaps: raise RuntimeError('LOCAL_WHISPER_MODEL_MISSING')
    model = WhisperModel(str(snaps[-1]), device=cfg['speech_to_text']['device'],
                         compute_type=cfg['speech_to_text']['compute_type'], local_files_only=True)
    cp = e.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(R / '.secrets/kdi-media-reader.json')
    drive = build('drive', 'v3', credentials=service_account.Credentials.from_service_account_file(
        cp, scopes=['https://www.googleapis.com/auth/drive.readonly']), cache_discovery=False)
    ff = str(R / '.tools/ffmpeg/bin/ffmpeg.exe'); fp = str(R / '.tools/ffmpeg/bin/ffprobe.exe')

    for m in cands:
        aid = m['asset_id']
        if aid in done: continue
        t0 = time.time(); a = assets[aid]; d = dests.get(aid)
        source_fp = a.get('content_hash') or a.get('checksum_sha256')
        if not d: raise RuntimeError('MASTER_UNAVAILABLE:' + aid)
        td = Path(tempfile.mkdtemp(prefix=f'kdi-p11-{m["rollout_position"]}-'))
        media = td / m['filename']; wav = td / 'audio.wav'
        try:
            with media.open('wb') as fh:
                dl = MediaIoBaseDownload(fh, drive.files().get_media(fileId=d['destination_google_file_id'],
                                         supportsAllDrives=True), chunksize=8 * 1024 * 1024)
                fin = False
                while not fin: _, fin = dl.next_chunk(num_retries=3)
            if file_sha256(media) != source_fp: raise RuntimeError('MASTER_HASH_MISMATCH:' + aid)
            probe = json.loads(subprocess.run([fp, '-v', 'error', '-show_entries',
                'format=duration:stream=codec_type,codec_name,sample_rate,channels', '-of', 'json', str(media)],
                capture_output=True, text=True, check=True, timeout=120).stdout)
            astreams = [x for x in probe['streams'] if x.get('codec_type') == 'audio']
            media_duration = float(probe.get('format', {}).get('duration') or 0)
            if not astreams: raise RuntimeError('AUDIO_STREAM_EXPECTED_BUT_ABSENT:' + aid)

            extract_audio(ff, media, wav, sample_rate=cfg['audio_extractor']['sample_rate'],
                          channels=cfg['audio_extractor']['channels'])
            meta = wav_metadata(wav); vad = energy_vad(wav, cfg['vad'])
            rows = []; info = None; tsec = 0.0
            if vad['speech_present'] == 'YES':
                ts = time.time()
                it, info = model.transcribe(str(wav), beam_size=cfg['speech_to_text']['beam_size'],
                                            word_timestamps=True, vad_filter=True, temperature=0,
                                            condition_on_previous_text=False)
                for seg in it:
                    probs = [float(w.probability) for w in (seg.words or []) if isinstance(w.probability, (int, float))]
                    if probs: conf, src = round(sum(probs) / len(probs), 3), 'PROVIDER_WORD_PROBABILITY_MEAN'
                    else: conf, src = confidence_from_logprob(seg.avg_logprob)
                    rows.append({'start': seg.start, 'end': seg.end, 'text': seg.text or '',
                                 'speaker': 'UNKNOWN_SPEAKER', 'language': (info.language or 'unknown'),
                                 'confidence': conf, 'confidence_source': src,
                                 'no_speech_prob': seg.no_speech_prob, 'avg_logprob': seg.avg_logprob})
                tsec = time.time() - ts
            # An energy candidate that yields no real text is downgraded, never asserted as speech.
            if vad['speech_present'] == 'YES' and not any(str(x['text']).strip() for x in rows):
                vad['speech_present'] = 'UNKNOWN'; vad['reason'] = 'ENERGY_CANDIDATE_WITHOUT_TRANSCRIPT'

            db_scenes = c.table('asset_scenes').select('id,start_seconds,end_seconds').eq('asset_id', aid)\
                .order('scene_index').execute().data or []
            scenes = [{'scene_id': s['id'], 'start_time': float(s['start_seconds'] or 0),
                       'end_time': float(s['end_seconds'] or 0)} for s in db_scenes]
            run_id = uid(f'{aid}:{source_fp}:{cfg_fp}:audio')
            chunks = build_chunks(aid, rows, scenes, [], run_id)
            for ch in chunks:
                if not (0 <= ch['start_time'] < ch['end_time']): raise RuntimeError('TRANSCRIPT_TIME_ORDER_INVALID:' + aid)
                if media_duration and ch['end_time'] > media_duration + 0.5:
                    raise RuntimeError('TRANSCRIPT_TIMESTAMP_BEYOND_MEDIA:' + aid)

            # Meaningfulness gate. A ~1s clip can decode a chime into a plausible word; that must not
            # become searchable speech. Failing chunks are kept truthfully but withheld from search.
            ms = cfg['acceptance']['meaningful_speech']
            lang_prob = float(info.language_probability) if info else None
            for ch in chunks:
                flags = []
                if lang_prob is not None and lang_prob < ms['minimum_language_probability']:
                    flags.append('LANGUAGE_CONFIDENCE_BELOW_THRESHOLD')
                if len(str(ch['normalized_text']).split()) < ms['minimum_word_count']:
                    flags.append('TOO_FEW_WORDS_FOR_MEANINGFUL_SPEECH')
                if (ch['end_time'] - ch['start_time']) < ms['minimum_speech_span_seconds']:
                    flags.append('SPEECH_SPAN_TOO_SHORT')
                ch['meaningfulness_flags'] = flags
                if flags: ch['accepted_for_search'] = False
            if vad['speech_present'] == 'YES' and not any(not x['meaningfulness_flags'] for x in chunks):
                vad['speech_present'] = 'UNKNOWN'
                vad['reason'] = 'ENERGY_CANDIDATE_WITHOUT_MEANINGFUL_SPEECH'

            accepted = [x for x in chunks if x['accepted_for_search']]
            gated = [x for x in accepted if clinical_terms(x['normalized_text'])]
            searchable = [x for x in accepted if not clinical_terms(x['normalized_text'])]

            c.table('semantic_analysis_runs').upsert({'id': run_id, 'asset_id': aid,
                'run_type': 'PHASE11_AUDIO_TRANSCRIPTION', 'status': 'COMPLETED',
                'semantic_spec_version': SPEC, 'ontology_version': ONT, 'processor_version': PROC,
                'configuration_fingerprint': cfg_fp, 'source_fingerprint': source_fp,
                'provider': 'local_faster_whisper', 'model': 'small',
                'metadata': {'phase': 11, 'rollout_position': m['rollout_position'],
                             'speech_present': vad['speech_present'], 'external_calls': 0}},
                on_conflict='id').execute()

            for row in (c.table('asset_transcript_chunks').select('id,provenance').eq('asset_id', aid).execute().data or []):
                if (row.get('provenance') or {}).get('origin') == 'PHASE11':
                    c.table('asset_transcript_chunks').delete().eq('id', row['id']).execute()
            payload = []
            for ch in chunks:
                cl = clinical_terms(ch['normalized_text'])
                status = ('ACCEPTED_FOR_SEARCH' if ch['accepted_for_search'] and not cl
                          else 'EXCLUDED_REVIEW_REQUIRED' if ch['quality_flags'] or cl or ch['meaningfulness_flags']
                          else 'EXCLUDED')
                payload.append({'asset_id': aid, 'start_seconds': ch['start_time'], 'end_seconds': ch['end_time'],
                    'speaker_role': 'UNKNOWN_SPEAKER', 'language': ch['language'],
                    'transcript_text': ch['normalized_text'], 'raw_text': ch['raw_text'],
                    'normalized_text': ch['normalized_text'], 'summary': None,
                    'topics': [t['canonical_code'] for t in ch['topics']],
                    'transcription_status': status, 'search_status': status,
                    'confidence': ch['confidence'], 'scene_id': ch['primary_scene_id'],
                    'source_text_fingerprint': ch['source_text_fingerprint'],
                    'provider': 'local_faster_whisper', 'model': 'small', 'version': PROC,
                    'semantic_analysis_run_id': run_id,
                    'human_review_status': 'PENDING',
                    'provenance': {'origin': 'PHASE11', 'chunk_id': ch['transcript_chunk_id'],
                                   'analysis_run_id': run_id, 'quality_flags': ch['quality_flags'],
                                   'meaningfulness_flags': ch['meaningfulness_flags'],
                                   'language_probability': lang_prob,
                                   'clinical_terms_present': cl, 'confidence_source': ch['confidence_source'],
                                   'accepted_for_search': status == 'ACCEPTED_FOR_SEARCH',
                                   'configuration_fingerprint': cfg_fp, 'source_fingerprint': source_fp}})
            if payload: c.table('asset_transcript_chunks').insert(payload).execute()

            speech_state = ('OBSERVED' if vad['speech_present'] == 'YES' and chunks
                            else 'FALSE' if vad['speech_present'] == 'NO' else 'UNKNOWN')
            transcript_state = 'OBSERVED' if searchable else ('FALSE' if vad['speech_present'] == 'NO' else 'UNKNOWN')
            facts = [('AUDIO_STREAM_PRESENT', 'OBSERVED', 1.0, 'DETERMINISTIC_PROCESSOR'),
                     ('SPEECH_PRESENT', speech_state, vad.get('confidence'), 'DETERMINISTIC_PROCESSOR'),
                     ('TRANSCRIPT', transcript_state, None, 'AI_MODEL'),
                     ('SPEAKER_ROLES_FROM_AUDIO', 'UNKNOWN', None, 'AI_MODEL')]
            c.table('semantic_assertions').update({'active': False}).eq('asset_id', aid)\
                .eq('layer_id', LAYER).eq('active', True).execute()
            arows = []; erows = []
            for code, st, conf, origin in facts:
                sid = uid(f'{run_id}:assertion:{code}')
                arows.append({'id': sid, 'asset_id': aid, 'layer_id': LAYER, 'subject_type': 'ASSET',
                    'predicate': code, 'canonical_concept_code': code, 'canonical_concept_type': LAYER,
                    'value_text': None, 'semantic_state': st, 'confidence': conf,
                    'confidence_source': 'HIGH' if conf and conf >= .9 else ('MEDIUM' if conf else None),
                    'search_critical': False, 'origin': origin, 'ontology_version': ONT,
                    'analysis_run_id': run_id,
                    'semantic_spec_version': SPEC, 'human_review_status': 'PENDING', 'active': True,
                    'source_fingerprint': source_fp, 'idempotency_key': f'phase11:{run_id}:{LAYER}:{code}'})
                temporal = code in ('TRANSCRIPT', 'SPEECH_PRESENT')
                erows.append({'assertion_id': sid, 'evidence_type': 'TRANSCRIPT' if temporal else 'ASSET_LEVEL',
                    'polarity': 'POSITIVE' if st == 'OBSERVED' else 'NEGATIVE', 'completeness': 'COMPLETE',
                    'asset_id': aid, 'start_time': 0.0 if temporal else None,
                    'end_time': round(media_duration, 3) if temporal else None,
                    'evidence_score': float(conf) if conf else 0.5, 'source_fingerprint': source_fp,
                    'analysis_run_id': run_id})
            for row in arows: c.table('semantic_assertions').upsert(row, on_conflict='id').execute()
            have = {x['assertion_id'] for x in (c.table('semantic_assertion_evidence').select('assertion_id')
                    .in_('assertion_id', [r['id'] for r in arows]).execute().data or [])}
            new_ev = [r for r in erows if r['assertion_id'] not in have]
            if new_ev: c.table('semantic_assertion_evidence').insert(new_ev).execute()
            c.table('asset_semantic_layers').update({'semantic_state': 'OBSERVED', 'applicability': 'APPLICABLE',
                'processing_status': 'COMPLETE', 'completeness_status': 'COMPLETE',
                'confidence_summary': {'provider': 'local_faster_whisper', 'model': 'small',
                                       'speech_present': vad['speech_present'], 'phase': 11}})\
                .eq('asset_id', aid).eq('layer_id', LAYER).eq('active', True).execute()

            results.append({'asset_id': aid, 'rollout_position': m['rollout_position'], 'filename': m['filename'],
                'status': 'COMPLETE', 'audio_stream': True,
                'audio': {'codec': astreams[0].get('codec_name'), 'sample_rate': astreams[0].get('sample_rate'),
                          'channels': astreams[0].get('channels'), 'media_duration_seconds': round(media_duration, 3),
                          'wav_duration_seconds': round(meta['duration_seconds'], 3)},
                'vad': vad, 'speech_present': vad['speech_present'],
                'language': (info.language if info else None),
                'language_probability': (round(float(info.language_probability), 3) if info else None),
                'raw_segments': len(rows), 'chunks': len(chunks), 'accepted_chunks': len(accepted),
                'searchable_chunks': len(searchable), 'clinical_gated_chunks': len(gated),
                'hallucination_flagged': sum(1 for x in chunks if x['quality_flags']),
                'non_meaningful_rejected': sum(1 for x in chunks if x['meaningfulness_flags']),
                'layer14_state_after': 'OBSERVED', 'speech_state': speech_state,
                'transcript_state': transcript_state,
                'searchable_text': ' '.join(x['normalized_text'] for x in searchable),
                'run_id': run_id, 'source_fingerprint': source_fp,
                'search_document_rebuilt': False, 'e5': 'EXISTING_E5_REUSED',
                'openclip': 'EXISTING_VECTOR_REUSED',
                'chunk_detail': [{'start': x['start_time'], 'end': x['end_time'], 'text': x['normalized_text'],
                                  'confidence': x['confidence'], 'language': x['language'],
                                  'quality_flags': x['quality_flags'],
                                  'meaningfulness_flags': x['meaningfulness_flags'],
                                  'clinical_terms': clinical_terms(x['normalized_text']),
                                  'accepted_for_search': x['accepted_for_search'],
                                  'scene_id': x['primary_scene_id']} for x in chunks],
                'seconds': round(time.time() - t0, 3), 'transcribe_seconds': round(tsec, 3)})
            CKPT.write_text(json.dumps({'status': 'RUNNING', 'planned': len(cands), 'assets': results},
                                       indent=2) + '\n', encoding='utf-8')
            print(json.dumps({'position': m['rollout_position'], 'filename': m['filename'],
                              'speech': vad['speech_present'], 'chunks': len(chunks),
                              'searchable': len(searchable), 'seconds': round(time.time() - t0, 3)}), flush=True)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    CKPT.write_text(json.dumps({'status': 'TRANSCRIBED', 'planned': len(cands), 'completed': len(results),
        'processor_version': PROC, 'configuration_fingerprint': cfg_fp,
        'external_speech_calls': 0, 'external_media_transmission': False,
        'assets': sorted(results, key=lambda x: x['rollout_position'])}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'TRANSCRIBED', 'completed': len(results),
                      'elapsed_seconds': round(time.time() - started, 3)}))


# ---------------------------------------------------------------- stage 2
def rebuild_stage():
    """Rebuild search document and E5 only where accepted transcript changed searchable truth."""
    started = time.time(); cfg, cfg_fp = load_config(); c, _ = client()
    import numpy as np
    from sentence_transformers import SentenceTransformer
    data = json.loads(CKPT.read_text(encoding='utf-8'))
    targets = [x for x in data['assets'] if x.get('searchable_chunks', 0) > 0 and not x.get('search_document_rebuilt')]
    if not targets:
        data['status'] = 'PASS'
        data['rebuild'] = {'documents_rebuilt': sum(1 for x in data['assets'] if x.get('search_document_rebuilt')),
                           'e5_rebuilt': sum(1 for x in data['assets'] if x.get('e5') == 'E5_REBUILT_DUE_TO_TRANSCRIPT'),
                           'reason': 'no asset produced accepted, clinically-clean transcript text'}
        CKPT.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'status': 'PASS', 'rebuilt': 0, 'reason': 'no searchable transcript'})); return
    snaps = sorted((Path.home() / '.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots').glob('*'))
    e5model = SentenceTransformer(str(snaps[-1]), local_files_only=True)
    for t in targets:
        aid = t['asset_id']
        doc = (c.table('search_document_builds').select('*').eq('asset_id', aid).eq('active', True)
               .eq('stale', False).limit(1).execute().data or [None])[0]
        legacy = (c.table('asset_search_documents').select('*').eq('asset_id', aid).limit(1).execute().data or [None])[0]
        if not doc or not legacy: raise RuntimeError('SEARCH_DOCUMENT_MISSING:' + aid)
        new_text = re.sub(r'\s+', ' ', unicodedata.normalize(
            'NFKC', f"{legacy['searchable_text']} Spoken content: {t['searchable_text']}")).strip()
        if clinical_terms(new_text): raise RuntimeError('SEARCH_DOCUMENT_CLINICAL_LEAKAGE:' + aid)
        docfp = hashlib.sha256(new_text.encode()).hexdigest()
        newdoc = uid(f"{t['run_id']}:document:{docfp}")
        normalized = dict(doc.get('normalized_document') or {})
        normalized['spoken_content'] = t['searchable_text']; normalized['transcript_chunks'] = t['searchable_chunks']
        c.table('search_document_builds').update({'active': False, 'stale': True}).eq('asset_id', aid)\
            .eq('active', True).execute()
        c.table('search_document_builds').upsert({**{k: v for k, v in doc.items()
            if k not in ('id', 'created_at', 'updated_at')}, 'id': newdoc, 'search_text': new_text,
            'normalized_document': normalized, 'document_fingerprint': docfp, 'status': 'READY',
            'active': True, 'stale': False, 'builder_version': 'kdi_phase11_transcript_builder_v1',
            'configuration_version': 'kdi_phase11_transcription_backfill_v1', 'generated_at': now()},
            on_conflict='id').execute()
        c.table('asset_search_documents').update({'searchable_text': new_text, 'structured_document': normalized,
            'build_status': 'READY', 'built_at': now()}).eq('asset_id', aid).execute()
        vec = np.asarray(e5model.encode('passage: ' + new_text, normalize_embeddings=True), dtype=np.float32)
        tfp = sha(new_text, TNORM, docfp)
        vfp = hashlib.sha256((E5 + '\x1f' + E5VER + '\x1f384\x1f' + tfp + '\x1f').encode()
                             + struct.pack('<' + 'f' * 384, *vec.tolist())).hexdigest()
        embid = uid(f"{t['run_id']}:e5")
        old = (c.table('semantic_embeddings').select('*').eq('asset_id', aid)
               .eq('representation_type', 'TEXT_ASSET').eq('active', True).limit(1).execute().data or [None])[0]
        c.table('semantic_embeddings').update({'active': False, 'stale': True}).eq('asset_id', aid)\
            .eq('representation_type', 'TEXT_ASSET').eq('active', True).execute()
        c.table('semantic_embeddings').upsert({**{k: v for k, v in (old or {}).items()
            if k not in ('id', 'created_at', 'updated_at')}, 'id': embid, 'asset_id': aid,
            'embedding_scope': 'TEXT_ASSET', 'representation_type': 'TEXT_ASSET',
            'provider': 'sentence_transformers', 'model': E5, 'version': EMBV, 'model_version': E5VER,
            'dimensions': 384, 'embedding': vec.tolist(), 'source_fingerprint': tfp,
            'source_text_fingerprint': tfp, 'source_document_fingerprint': docfp, 'vector_fingerprint': vfp,
            'text_normalization_version': TNORM, 'embedding_version': EMBV, 'embedding_bundle_version': BUNDLE,
            'semantic_spec_version': SPEC, 'semantic_spec_fingerprint': SPEC_FP, 'ontology_version': ONT,
            'active': True, 'stale': False, 'review_status': 'AI_UNREVIEWED', 'generated_at': now(),
            'metadata': {'source_unit_id': newdoc, 'phase11_transcript_rebuild': True}}, on_conflict='id').execute()
        t['search_document_rebuilt'] = True; t['e5'] = 'E5_REBUILT_DUE_TO_TRANSCRIPT'
        print(json.dumps({'asset': t['filename'], 'rebuilt': True}), flush=True)
    data['status'] = 'PASS'
    data['rebuild'] = {'documents_rebuilt': sum(1 for x in data['assets'] if x.get('search_document_rebuilt')),
                       'e5_rebuilt': sum(1 for x in data['assets'] if x.get('e5') == 'E5_REBUILT_DUE_TO_TRANSCRIPT'),
                       'openclip_rebuilt': 0}
    CKPT.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'rebuilt': data['rebuild']['documents_rebuilt'],
                      'elapsed_seconds': round(time.time() - started, 3)}))


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else 'transcribe'
    if stage == 'transcribe': transcribe_stage(force='--reprocess' in sys.argv)
    elif stage == 'rebuild': rebuild_stage()
    else: raise SystemExit('unknown stage: ' + stage)
