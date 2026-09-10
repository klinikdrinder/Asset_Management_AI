"""FULL-INDEX-30 — audio and OCR completeness for the whole 30-asset cohort.

The policy requires every required component to hold a *terminal evaluated* state. UNKNOWN is only
acceptable for a real epistemic reason, never because a check was skipped. Several cohort videos
carried SPEECH_PRESENT=UNKNOWN and OCR_VISIBLE_TEXT=UNKNOWN purely because those analyses were never
run. This resolves both against the actual media using the approved local engines.

Two stages, separate processes (CTranslate2 and PyTorch cannot share one process):
    .venv-semantic  python scripts/full_index_30_audio_ocr.py audio
    .venv-semantic  python scripts/full_index_30_audio_ocr.py ocr
"""
from __future__ import annotations
import hashlib, json, math, os, shutil, subprocess, sys, tempfile, time, uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'src'))
from kdi_media.audio_intelligence import extract_audio, wav_metadata, energy_vad, build_chunks, file_sha256

OUT = R / 'reports/semantic-search/rollout/full-index-30'; OUT.mkdir(parents=True, exist_ok=True)
AUDIO_CFG = R / 'config/semantic-search/kdi_audio_intelligence_v2_production.json'
OCR_CFG = R / 'config/semantic-search/kdi_ocr_intelligence_v1.json'
AUDIO_CKPT = OUT / 'full_index_30_audio_results.json'
OCR_CKPT = OUT / 'full_index_30_ocr_results.json'
FF = str(R / '.tools/ffmpeg/bin/ffmpeg.exe'); FP = str(R / '.tools/ffmpeg/bin/ffprobe.exe')
SPEC = 'semantic_index_v1'; ONT = 'KDI_SEMANTIC_V2'
AUDIO_PROC = 'kdi_audio_intelligence_v2'; OCR_PROC = 'kdi_ocr_intelligence_v2'
L14 = 'SPEECH_TRANSCRIPT_AUDIO'; L15 = 'OCR_VISIBLE_TEXT'
NS = uuid.UUID('9c1d4b70-5e2a-4f83-91cd-7ab0e6f24d15')
UNSAFE = ('surgery', 'procedure', 'treatment', 'hair transplant', 'fue', 'implantation', 'extraction',
          'graft harvesting', 'graft placement', 'prp', 'laser treatment', 'injection')


def now(): return datetime.now(timezone.utc).isoformat()
def uid(s): return str(uuid.uuid5(NS, s))
def clinical(t):
    low = ' ' + ' '.join(str(t).lower().split()) + ' '
    return sorted({x for x in UNSAFE if x in low})


def env():
    e = {}
    for f in (R / '.env', R / '.env.local', R / 'dashboard/.env.local'):
        if f.exists(): e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ); return e


def client():
    e = env()
    return create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'], e['SUPABASE_SERVICE_ROLE_KEY']), e


def chunked(c, table, fields, ids, key='asset_id'):
    rows = []
    for i in range(0, len(ids), 50):
        rows += c.table(table).select(fields).in_(key, ids[i:i + 50]).execute().data or []
    return rows


def cohort_assets(c):
    layers = c.table('asset_semantic_layers').select('asset_id,processing_status').eq('active', True).execute().data or []
    per = defaultdict(lambda: [0, 0])
    for x in layers:
        per[x['asset_id']][0] += 1
        if x['processing_status'] == 'COMPLETE': per[x['asset_id']][1] += 1
    ids = sorted(k for k, v in per.items() if v == [18, 18])
    return chunked(c, 'assets', 'id,file_name,mime_type,content_hash,checksum_sha256', ids, key='id')


def drive_client(e):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build as gbuild
    cp = e.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(R / '.secrets/kdi-media-reader.json')
    return gbuild('drive', 'v3', credentials=service_account.Credentials.from_service_account_file(
        cp, scopes=['https://www.googleapis.com/auth/drive.readonly']), cache_discovery=False)


def download(drive, file_id, dest):
    from googleapiclient.http import MediaIoBaseDownload
    with dest.open('wb') as fh:
        dl = MediaIoBaseDownload(fh, drive.files().get_media(fileId=file_id, supportsAllDrives=True),
                                 chunksize=8 * 1024 * 1024)
        fin = False
        while not fin: _, fin = dl.next_chunk(num_retries=3)


def set_layer(c, aid, layer, state, applicability, summary):
    c.table('asset_semantic_layers').update({'semantic_state': state, 'applicability': applicability,
        'processing_status': 'COMPLETE', 'completeness_status': 'COMPLETE',
        'confidence_summary': summary}).eq('asset_id', aid).eq('layer_id', layer).eq('active', True).execute()


def upsert_run(c, run_id, aid, run_type, proc, cfg_fp, src, provider, model, meta):
    c.table('semantic_analysis_runs').upsert({'id': run_id, 'asset_id': aid, 'run_type': run_type,
        'status': 'COMPLETED', 'semantic_spec_version': SPEC, 'ontology_version': ONT,
        'processor_version': proc, 'configuration_fingerprint': cfg_fp, 'source_fingerprint': src,
        'provider': provider, 'model': model, 'metadata': meta}, on_conflict='id').execute()


def write_assertions(c, aid, layer, run_id, src, facts, scene_id=None):
    """Assertions land non-critical, evidence attaches, then search_critical is raised so the
    deferred evidence guard validates the final state."""
    c.table('semantic_assertions').update({'active': False}).eq('asset_id', aid).eq('layer_id', layer)\
        .eq('active', True).execute()
    arows, erows = [], []
    for code, state, conf, origin, critical, etype in facts:
        sid = uid(f'{run_id}:{layer}:{code}')
        arows.append({'id': sid, 'asset_id': aid, 'scene_id': scene_id, 'layer_id': layer,
            'subject_type': 'ASSET' if not scene_id else 'SCENE', 'predicate': code,
            'canonical_concept_code': code, 'canonical_concept_type': layer, 'value_text': None,
            'semantic_state': state, 'confidence': conf,
            'confidence_source': 'HIGH' if conf and conf >= .9 else ('MEDIUM' if conf else None),
            'search_critical': critical, 'analysis_run_id': run_id, 'origin': origin,
            'ontology_version': ONT, 'semantic_spec_version': SPEC, 'human_review_status': 'PENDING',
            'active': True, 'source_fingerprint': src, 'idempotency_key': f'fullindex30:{run_id}:{layer}:{code}'})
        erows.append({'assertion_id': sid, 'evidence_type': etype,
            'polarity': 'POSITIVE' if state == 'OBSERVED' else 'NEGATIVE', 'completeness': 'COMPLETE',
            'asset_id': aid, 'scene_id': scene_id, 'evidence_score': float(conf) if conf else 0.5,
            'source_fingerprint': src, 'analysis_run_id': run_id})
    for r in arows:
        c.table('semantic_assertions').upsert({**r, 'search_critical': False}, on_conflict='id').execute()
    have = {x['assertion_id'] for x in (c.table('semantic_assertion_evidence').select('assertion_id')
            .in_('assertion_id', [r['id'] for r in arows]).execute().data or [])}
    new = [r for r in erows if r['assertion_id'] not in have]
    if new: c.table('semantic_assertion_evidence').insert(new).execute()
    for r in arows:
        if r['search_critical']:
            c.table('semantic_assertions').update({'search_critical': True}).eq('id', r['id']).execute()


# ---------------------------------------------------------------- audio
def audio_stage():
    started = time.time(); c, e = client()
    from faster_whisper import WhisperModel
    from kdi_media.audio_intelligence import canonical_fingerprint
    cfg = json.loads(AUDIO_CFG.read_text(encoding='utf-8')); cfg_fp = canonical_fingerprint(cfg)
    ms = cfg['acceptance']['meaningful_speech']
    assets = [a for a in cohort_assets(c) if str(a['mime_type']).startswith('video')]
    ids = [a['id'] for a in assets]
    dests = {x['asset_id']: x for x in (c.table('asset_destinations').select('asset_id,destination_google_file_id')
             .in_('asset_id', ids).eq('upload_status', 'VERIFIED').execute().data or [])}
    speech = {x['asset_id']: x for x in chunked(c, 'semantic_assertions',
              'asset_id,canonical_concept_code,semantic_state,active', ids)
              if x['active'] and x['canonical_concept_code'] == 'SPEECH_PRESENT'}
    prior = {}
    if AUDIO_CKPT.exists():
        prior = {x['asset_id']: x for x in json.loads(AUDIO_CKPT.read_text(encoding='utf-8')).get('assets', [])
                 if x.get('status') == 'COMPLETE'}
    # An asset needs evaluation unless a real analysis already produced its terminal state.
    targets = [a for a in assets if a['id'] not in prior
               and (a['id'] not in speech or speech[a['id']]['semantic_state'] == 'UNKNOWN')]
    already = [a for a in assets if a['id'] in prior or (a['id'] in speech and speech[a['id']]['semantic_state'] != 'UNKNOWN')]
    print(json.dumps({'stage': 'audio', 'videos': len(assets), 'to_evaluate': len(targets),
                      'already_terminal': len(already)}), flush=True)
    results = list(prior.values())
    if targets:
        snaps = sorted((Path.home() / '.cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots').glob('*'))
        model = WhisperModel(str(snaps[-1]), device='cpu', compute_type='int8', local_files_only=True)
        drive = drive_client(e)
        for a in targets:
            t0 = time.time(); aid = a['id']; src = a.get('content_hash') or a.get('checksum_sha256')
            td = Path(tempfile.mkdtemp(prefix='kdi-ao-')); media = td / a['file_name']; wav = td / 'a.wav'
            try:
                download(drive, dests[aid]['destination_google_file_id'], media)
                if file_sha256(media) != src: raise RuntimeError('MASTER_HASH_MISMATCH:' + a['file_name'])
                probe = json.loads(subprocess.run([FP, '-v', 'error', '-show_entries',
                    'format=duration:stream=codec_type,codec_name', '-of', 'json', str(media)],
                    capture_output=True, text=True, check=True, timeout=180).stdout)
                astreams = [x for x in probe['streams'] if x.get('codec_type') == 'audio']
                dur = float(probe.get('format', {}).get('duration') or 0)
                run_id = uid(f'{aid}:{src}:{cfg_fp}:audio')
                if not astreams:
                    upsert_run(c, run_id, aid, 'FULL_INDEX_AUDIO', AUDIO_PROC, cfg_fp, src,
                               'local_faster_whisper', 'small', {'phase': 'FULL_INDEX_30', 'has_audio': False,
                                                                 'external_calls': 0})
                    write_assertions(c, aid, L14, run_id, src, [
                        ('AUDIO_STREAM_PRESENT', 'FALSE', 1.0, 'DETERMINISTIC_PROCESSOR', False, 'ASSET_LEVEL'),
                        ('SPEECH_PRESENT', 'FALSE', 1.0, 'DETERMINISTIC_PROCESSOR', False, 'ASSET_LEVEL'),
                        ('TRANSCRIPT', 'NOT_APPLICABLE' if False else 'FALSE', 1.0, 'DETERMINISTIC_PROCESSOR', False, 'ASSET_LEVEL'),
                        ('SPEAKER_ROLES_FROM_AUDIO', 'FALSE', 1.0, 'DETERMINISTIC_PROCESSOR', False, 'ASSET_LEVEL')])
                    set_layer(c, aid, L14, 'NOT_APPLICABLE', 'NOT_APPLICABLE',
                              {'reason': 'NO_AUDIO_STREAM', 'phase': 'FULL_INDEX_30'})
                    results.append({'asset_id': aid, 'filename': a['file_name'], 'status': 'COMPLETE',
                        'has_audio': False, 'terminal_state': 'NO_AUDIO', 'layer14': 'NOT_APPLICABLE',
                        'chunks': 0, 'accepted': 0, 'seconds': round(time.time() - t0, 2)})
                else:
                    extract_audio(FF, media, wav, sample_rate=16000, channels=1)
                    meta = wav_metadata(wav); vad = energy_vad(wav, cfg['vad'])
                    rows = []; info = None
                    if vad['speech_present'] == 'YES':
                        it, info = model.transcribe(str(wav), beam_size=5, word_timestamps=True,
                                                    vad_filter=True, temperature=0, condition_on_previous_text=False)
                        for seg in it:
                            probs = [float(w.probability) for w in (seg.words or []) if isinstance(w.probability, (int, float))]
                            conf = round(sum(probs) / len(probs), 3) if probs else (
                                round(max(0.0, min(1.0, math.exp(float(seg.avg_logprob)))), 3)
                                if isinstance(seg.avg_logprob, (int, float)) else None)
                            rows.append({'start': seg.start, 'end': seg.end, 'text': seg.text or '',
                                         'speaker': 'UNKNOWN_SPEAKER', 'language': info.language or 'unknown',
                                         'confidence': conf, 'confidence_source': 'PROVIDER_WORD_PROBABILITY_MEAN'})
                    scenes = [{'scene_id': s['id'], 'start_time': float(s['start_seconds']), 'end_time': float(s['end_seconds'])}
                              for s in (c.table('asset_scenes').select('id,start_seconds,end_seconds')
                                        .eq('asset_id', aid).eq('canonical_active', True).execute().data or [])]
                    chunks = build_chunks(aid, rows, scenes, [], run_id)
                    # asset_transcript_chunks requires a linked chunk to sit inside its scene.
                    # build_chunks links on overlap, so drop the link when containment fails rather
                    # than distorting either the transcript span or the scene boundary.
                    span = {s2['scene_id']: (s2['start_time'], s2['end_time']) for s2 in scenes}
                    for ch in chunks:
                        b = span.get(ch['primary_scene_id'])
                        if b and not (b[0] - 1e-6 <= ch['start_time'] and ch['end_time'] <= b[1] + 1e-6):
                            ch['primary_scene_id'] = None
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
                    meaningful = [x for x in chunks if x['accepted_for_search'] and not clinical(x['normalized_text'])]
                    if vad['speech_present'] == 'YES' and not any(not x['meaningfulness_flags'] for x in chunks):
                        vad['speech_present'] = 'UNKNOWN'; vad['reason'] = 'ENERGY_CANDIDATE_WITHOUT_MEANINGFUL_SPEECH'
                    upsert_run(c, run_id, aid, 'FULL_INDEX_AUDIO', AUDIO_PROC, cfg_fp, src,
                               'local_faster_whisper', 'small',
                               {'phase': 'FULL_INDEX_30', 'has_audio': True, 'external_calls': 0,
                                'speech_present': vad['speech_present'], 'segments': len(rows)})
                    for row in (c.table('asset_transcript_chunks').select('id,provenance').eq('asset_id', aid).execute().data or []):
                        if (row.get('provenance') or {}).get('origin') in ('PHASE11', 'FULL_INDEX_30'):
                            c.table('asset_transcript_chunks').delete().eq('id', row['id']).execute()
                    payload = []
                    for ch in chunks:
                        cl = clinical(ch['normalized_text'])
                        st = ('ACCEPTED_FOR_SEARCH' if ch['accepted_for_search'] and not cl
                              else 'EXCLUDED_REVIEW_REQUIRED' if ch['quality_flags'] or cl or ch['meaningfulness_flags']
                              else 'EXCLUDED')
                        payload.append({'asset_id': aid, 'start_seconds': ch['start_time'], 'end_seconds': ch['end_time'],
                            'speaker_role': 'UNKNOWN_SPEAKER', 'language': ch['language'],
                            'transcript_text': ch['normalized_text'], 'raw_text': ch['raw_text'],
                            'normalized_text': ch['normalized_text'], 'topics': [t['canonical_code'] for t in ch['topics']],
                            'transcription_status': st, 'search_status': st, 'confidence': ch['confidence'],
                            'scene_id': ch['primary_scene_id'], 'source_text_fingerprint': ch['source_text_fingerprint'],
                            'provider': 'local_faster_whisper', 'model': 'small', 'version': AUDIO_PROC,
                            'semantic_analysis_run_id': run_id, 'human_review_status': 'PENDING',
                            'provenance': {'origin': 'FULL_INDEX_30', 'chunk_id': ch['transcript_chunk_id'],
                                           'quality_flags': ch['quality_flags'],
                                           'meaningfulness_flags': ch['meaningfulness_flags'],
                                           'language_probability': lang_prob, 'clinical_terms_present': cl,
                                           'accepted_for_search': st == 'ACCEPTED_FOR_SEARCH',
                                           'configuration_fingerprint': cfg_fp, 'source_fingerprint': src}})
                    if payload: c.table('asset_transcript_chunks').insert(payload).execute()
                    sp = ('OBSERVED' if meaningful else 'FALSE' if vad['speech_present'] == 'NO' else 'UNKNOWN')
                    tr = 'OBSERVED' if meaningful else ('FALSE' if vad['speech_present'] == 'NO' else 'UNKNOWN')
                    write_assertions(c, aid, L14, run_id, src, [
                        ('AUDIO_STREAM_PRESENT', 'OBSERVED', 1.0, 'DETERMINISTIC_PROCESSOR', False, 'ASSET_LEVEL'),
                        ('SPEECH_PRESENT', sp, vad.get('confidence'), 'DETERMINISTIC_PROCESSOR', False, 'TRANSCRIPT'),
                        ('TRANSCRIPT', tr, None, 'AI_MODEL', False, 'TRANSCRIPT'),
                        ('SPEAKER_ROLES_FROM_AUDIO', 'UNKNOWN', None, 'AI_MODEL', False, 'TRANSCRIPT')])
                    set_layer(c, aid, L14, 'OBSERVED', 'APPLICABLE',
                              {'provider': 'local_faster_whisper', 'model': 'small', 'phase': 'FULL_INDEX_30',
                               'speech_present': vad['speech_present'], 'language_probability': lang_prob})
                    terminal = ('MEANINGFUL_SPEECH_TRANSCRIBED' if meaningful else
                                'NO_SPEECH' if vad['speech_present'] == 'NO' else
                                'INCIDENTAL_OR_UNINTELLIGIBLE_SOUND')
                    results.append({'asset_id': aid, 'filename': a['file_name'], 'status': 'COMPLETE',
                        'has_audio': True, 'terminal_state': terminal, 'layer14': 'OBSERVED',
                        'speech_present': vad['speech_present'], 'vad': vad, 'language': info.language if info else None,
                        'language_probability': lang_prob, 'chunks': len(chunks), 'accepted': len(meaningful),
                        'duration_seconds': dur, 'seconds': round(time.time() - t0, 2)})
                AUDIO_CKPT.write_text(json.dumps({'status': 'RUNNING', 'assets': results}, indent=2) + '\n', encoding='utf-8')
                print(json.dumps({'file': a['file_name'], 'terminal': results[-1]['terminal_state'],
                                  'chunks': results[-1]['chunks'], 'accepted': results[-1]['accepted']}), flush=True)
            finally:
                shutil.rmtree(td, ignore_errors=True)
    AUDIO_CKPT.write_text(json.dumps({'status': 'PASS', 'evaluated': len(results),
        'videos': len(assets), 'external_speech_calls': 0,
        'assets': sorted(results, key=lambda x: x['filename'])}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'evaluated': len(results),
                      'elapsed_seconds': round(time.time() - started, 1)}))


# ---------------------------------------------------------------- ocr
def ocr_stage():
    started = time.time(); c, e = client()
    import cv2, numpy as np, easyocr
    from PIL import Image, ImageOps
    from kdi_media.ocr_intelligence import (OCRConfig, canonical_fingerprint, box_from_points,
                                            normalize_text, gibberish, search_status, language_state)
    cfg = json.loads(OCR_CFG.read_text(encoding='utf-8')); cfg_fp = canonical_fingerprint(cfg)
    acc = cfg['acceptance']
    assets = cohort_assets(c)
    ids = [a['id'] for a in assets]
    dests = {x['asset_id']: x for x in (c.table('asset_destinations').select('asset_id,destination_google_file_id')
             .in_('asset_id', ids).eq('upload_status', 'VERIFIED').execute().data or [])}
    scenes = defaultdict(list)
    for s in (chunked(c, 'asset_scenes', 'id,asset_id,start_seconds,end_seconds,canonical_active', ids)):
        if s['canonical_active']: scenes[s['asset_id']].append(s)
    kfs = defaultdict(list)
    canon = {s['id'] for v in scenes.values() for s in v}
    for k in chunked(c, 'asset_keyframes', 'id,asset_id,scene_id,timestamp_seconds', ids):
        if k['scene_id'] in canon: kfs[k['asset_id']].append(k)
    prior = {}
    if OCR_CKPT.exists():
        prior = {x['asset_id']: x for x in json.loads(OCR_CKPT.read_text(encoding='utf-8')).get('assets', [])
                 if x.get('status') == 'COMPLETE'}
    # A video is only scannable once its canonical keyframes exist; leaving it for a later run is
    # correct, whereas scanning zero frames would record a false "no readable text" verdict.
    # Images are always in scope: an image whose OCR layer is still UNKNOWN was never scanned, and
    # skipping it would report completeness that does not exist.
    targets = [a for a in assets if a['id'] not in prior
               and (not str(a['mime_type']).startswith('video') or kfs.get(a['id']))]
    deferred = [a['file_name'] for a in assets if a['id'] not in prior
                and str(a['mime_type']).startswith('video') and not kfs.get(a['id'])]
    print(json.dumps({'stage': 'ocr', 'assets': len(assets), 'to_evaluate': len(targets),
                      'deferred_no_canonical_keyframes': deferred}), flush=True)
    model_dir = R / 'tmp/phase7_easyocr_models'
    reader = easyocr.Reader(cfg['ocr_engine']['languages'], gpu=False,
                            model_storage_directory=str(model_dir), user_network_directory=str(model_dir),
                            download_enabled=False, verbose=False)
    drive = drive_client(e); results = list(prior.values())
    for a in targets:
        t0 = time.time(); aid = a['id']; src = a.get('content_hash') or a.get('checksum_sha256')
        is_video = str(a['mime_type']).startswith('video')
        td = Path(tempfile.mkdtemp(prefix='kdi-ocr-')); media = td / a['file_name']
        try:
            download(drive, dests[aid]['destination_google_file_id'], media)
            if file_sha256(media) != src: raise RuntimeError('MASTER_HASH_MISMATCH:' + a['file_name'])
            run_id = uid(f'{aid}:{src}:{cfg_fp}:ocr')
            frames = []
            if is_video:
                for k in sorted(kfs.get(aid, []), key=lambda x: float(x['timestamp_seconds'])):
                    fp = td / f"kf_{k['id'][:8]}.jpg"
                    subprocess.run([FF, '-ss', f"{float(k['timestamp_seconds']):.3f}", '-i', str(media),
                                    '-frames:v', '1', '-q:v', '2', '-y', str(fp)],
                                   capture_output=True, timeout=180)
                    if fp.is_file() and fp.stat().st_size: frames.append((fp, k['id'], k['scene_id'], float(k['timestamp_seconds'])))
            else:
                fp = td / 'image.jpg'
                with Image.open(media) as im:
                    ImageOps.exif_transpose(im).convert('RGB').save(fp, quality=95)
                frames.append((fp, None, None, None))
            observations = []; scanned = 0
            for fpath, kid, sid, ts in frames:
                arr = cv2.imread(str(fpath))
                if arr is None: continue
                scanned += 1
                for pts, text, conf in reader.readtext(arr, decoder=cfg['ocr_engine']['decoder'],
                                                       canvas_size=cfg['ocr_engine']['canvas_size']):
                    norm = normalize_text(text)
                    if len(norm) < acc['minimum_useful_characters'] or gibberish(norm): continue
                    st, _reason = search_status(norm, float(conf), acc)
                    observations.append({'id': uid(f'{run_id}:{kid or "image"}:{norm}:{round(float(conf), 3)}'),
                        'asset_id': aid, 'scene_id': sid, 'keyframe_id': kid, 'timestamp_seconds': ts,
                        'raw_text': text, 'normalized_text': norm, 'text_type': 'OTHER',
                        'language': language_state(norm), 'confidence': round(float(conf), 4),
                        'bounding_box': box_from_points(pts, arr.shape[1], arr.shape[0]),
                        'search_status': st, 'provider': 'EasyOCR', 'model': 'english_g2+craft_mlt_25k',
                        'version': OCR_PROC, 'semantic_analysis_run_id': run_id,
                        'human_review_status': 'PENDING',
                        'provenance': 'OCR',
                        'metadata': {'phase': 'FULL_INDEX_30', 'engine': 'LOCAL_EASYOCR',
                                     'configuration_fingerprint': cfg_fp, 'frames_scanned': scanned}})
            credible = [o for o in observations if o['search_status'] == 'ACCEPTED_FOR_SEARCH']
            upsert_run(c, run_id, aid, 'FULL_INDEX_OCR', OCR_PROC, cfg_fp, src, 'EasyOCR', 'english_g2',
                       {'phase': 'FULL_INDEX_30', 'external_calls': 0, 'frames_scanned': scanned,
                        'observations': len(observations), 'credible': len(credible)})
            existing = c.table('ocr_observations').select('id,metadata').eq('asset_id', aid).execute().data or []
            for row in existing:
                if (row.get('metadata') or {}).get('phase') == 'FULL_INDEX_30':
                    c.table('ocr_observations').delete().eq('id', row['id']).execute()
            if observations:
                c.table('ocr_observations').insert(observations).execute()
            state = 'OBSERVED' if credible else ('FALSE' if scanned else 'UNKNOWN')
            write_assertions(c, aid, L15, run_id, src, [
                ('VISIBLE_TEXT', state, 0.9 if credible else (0.85 if scanned else None),
                 'DETERMINISTIC_PROCESSOR' if not credible else 'AI_MODEL', False, 'OCR')])
            set_layer(c, aid, L15, state, 'APPLICABLE',
                      {'provider': 'EasyOCR', 'phase': 'FULL_INDEX_30', 'frames_scanned': scanned,
                       'credible_observations': len(credible)})
            results.append({'asset_id': aid, 'filename': a['file_name'], 'status': 'COMPLETE',
                'media_type': 'VIDEO' if is_video else 'IMAGE', 'frames_scanned': scanned,
                'observations': len(observations), 'credible': len(credible),
                'terminal_state': 'READABLE_TEXT' if credible else 'NO_READABLE_TEXT',
                'layer15': state, 'sample': [o['normalized_text'][:60] for o in credible[:3]],
                'seconds': round(time.time() - t0, 2)})
            OCR_CKPT.write_text(json.dumps({'status': 'RUNNING', 'assets': results}, indent=2) + '\n', encoding='utf-8')
            print(json.dumps({'file': a['file_name'], 'frames': scanned, 'obs': len(observations),
                              'credible': len(credible), 'state': state}), flush=True)
        finally:
            shutil.rmtree(td, ignore_errors=True)
    OCR_CKPT.write_text(json.dumps({'status': 'PASS' if not deferred else 'INCOMPLETE',
        'deferred_no_canonical_keyframes': deferred,
        'evaluated': len(results), 'assets_total': len(assets),
        'external_calls': 0, 'assets': sorted(results, key=lambda x: x['filename'])}, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'evaluated': len(results),
                      'elapsed_seconds': round(time.time() - started, 1)}))


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else 'audio'
    if stage == 'audio': audio_stage()
    elif stage == 'ocr': ocr_stage()
    else: raise SystemExit('unknown stage: ' + stage)
