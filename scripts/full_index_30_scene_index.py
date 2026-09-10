"""Full-index corrective phase — canonical scene indexing for the partially indexed cohort videos.

Scope is fixed to the existing 30-asset cohort. Nothing outside it is read or written.

The 10 target videos hold only non-canonical placeholder scenes (canonical_active=false) with no
scene search document and no scene-level embedding. This builds real canonical scene truth:
technical metadata, evidence-driven segmentation, quality-scored keyframes, local VLM observations,
scene assertions with evidence, scene search documents, and the retrieval embeddings.

Two stages, separate processes and interpreters:
    .venv-semantic  python scripts/full_index_30_scene_index.py analyze
    .venv           python scripts/full_index_30_scene_index.py embed
"""
from __future__ import annotations
import hashlib, json, math, os, re, shutil, struct, subprocess, sys, tempfile, time, unicodedata, uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'src'))
OUT = R / 'reports/semantic-search/rollout/full-index-30'; OUT.mkdir(parents=True, exist_ok=True)
WORK = R / 'tmp/full-index-30'; WORK.mkdir(parents=True, exist_ok=True)
CKPT = OUT / 'full_index_30_scene_build.json'
FF = str(R / '.tools/ffmpeg/bin/ffmpeg.exe'); FP = str(R / '.tools/ffmpeg/bin/ffprobe.exe')

TARGETS = ['3631150497-preview.mp4', 'IMG_0534.MP4', 'IMG_1461.MP4', 'IMG_2933.MP4', 'IMG_2951.MP4',
           'IMG_3564.MP4', 'IMG_3568.MP4', 'IMG_3575.MP4', 'IMG_3587.MP4', 'IMG_3592.MP4']

MODEL = 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct'
PROC = 'kdi_full_index_scene_v1'
SPEC = 'semantic_index_v1'; ONT = 'KDI_SEMANTIC_V2'
E5 = 'intfloat/multilingual-e5-small'; E5VER = 'hf-main-pinned-runtime-v1'
CLIP_MODEL = 'ViT-B-32'; CLIP_VER = 'laion2b_s34b_b79k'
TNORM = 'unicode_nfkc_whitespace_v1'
NS = uuid.UUID('2f5c8a71-6b3d-4e19-9f52-8c04a7d1be36')
# The certified atomic vocabulary. No second ontology is introduced.
CONCEPTS = {
    'people': ('PEOPLE_ROLES', 'PERSON_OR_BODY_PART_VISIBLE', 'person or body part visible', 'ROLE', True),
    'objects': ('CLINICAL_VISUAL_OBSERVATIONS', 'HANDHELD_INSTRUMENT_AND_PROTECTIVE_GLOVES_VISIBLE',
                'handheld object or instrument and protective gloves visible', 'SEMANTIC_CONCEPT', True),
    'anatomy': ('ANATOMY', 'EXPOSED_BODY_REGION_VISIBLE', 'exposed body region visible', 'ANATOMY', True),
    'action': ('ACTIONS_EVENTS', 'PHYSICAL_CONTACT_HOLDING_OR_MANIPULATION_VISIBLE',
               'physical contact, holding, or manipulation visible', 'ACTION', True),
    'environment': ('ENVIRONMENT', 'BROAD_ENVIRONMENT_VISIBLE', 'broad indoor or outdoor environment visible',
                    'SEMANTIC_CONCEPT', False)}
UNSAFE = ('surgery', 'procedure', 'treatment', 'hair transplant', 'fue', 'implantation', 'extraction',
          'graft harvesting', 'graft placement', 'prp', 'laser treatment', 'injection')


def now(): return datetime.now(timezone.utc).isoformat()
def uid(seed): return str(uuid.uuid5(NS, seed))
def sha(*xs): return hashlib.sha256('\x1f'.join(str(x) for x in xs).encode()).hexdigest()
def norm(t): return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', t)).strip()


def env():
    e = {}
    for f in (R / '.env', R / '.env.local', R / 'dashboard/.env.local'):
        if f.exists(): e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ); return e


def client():
    e = env()
    return create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'], e['SUPABASE_SERVICE_ROLE_KEY']), e


def cohort_videos(c):
    layers = c.table('asset_semantic_layers').select('asset_id,processing_status').eq('active', True).execute().data or []
    per = {}
    for x in layers:
        v = per.setdefault(x['asset_id'], [0, 0]); v[0] += 1
        if x['processing_status'] == 'COMPLETE': v[1] += 1
    ids = sorted(k for k, v in per.items() if v == [18, 18])
    rows = []
    for i in range(0, len(ids), 50):
        rows += c.table('assets').select('id,file_name,mime_type,content_hash,checksum_sha256')\
            .in_('id', ids[i:i + 50]).execute().data or []
    return [x for x in rows if str(x['mime_type']).startswith('video')]


def probe_media(path):
    raw = json.loads(subprocess.run([FP, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
                                    capture_output=True, text=True, check=True, timeout=180).stdout)
    v = next((s for s in raw['streams'] if s.get('codec_type') == 'video'), None)
    a = next((s for s in raw['streams'] if s.get('codec_type') == 'audio'), None)
    fmt = raw.get('format', {})
    def rate(x):
        try:
            n, d = str(x).split('/'); return round(float(n) / float(d), 6) if float(d) else None
        except Exception: return None
    fps = rate((v or {}).get('avg_frame_rate')) or rate((v or {}).get('r_frame_rate'))
    w, h = (v or {}).get('width'), (v or {}).get('height')
    rot = None
    for sd in (v or {}).get('side_data_list', []) or []:
        if 'rotation' in sd: rot = sd['rotation']
    return {'duration_seconds': float(fmt['duration']) if fmt.get('duration') not in (None, 'N/A') else None,
            'width_px': w, 'height_px': h, 'fps': fps, 'codec': (v or {}).get('codec_name'),
            'orientation': None if not (w and h) else ('PORTRAIT' if h > w else 'LANDSCAPE' if w > h else 'SQUARE'),
            'aspect_ratio': (v or {}).get('display_aspect_ratio') or (round(w / h, 4) if w and h else None),
            'rotation': rot, 'pix_fmt': (v or {}).get('pix_fmt'),
            'bit_rate': fmt.get('bit_rate'), 'format_name': fmt.get('format_name'),
            'size_bytes': int(fmt['size']) if fmt.get('size') else None,
            'has_audio': bool(a), 'audio_codec': (a or {}).get('codec_name'),
            'audio_sample_rate': (a or {}).get('sample_rate'), 'audio_channels': (a or {}).get('channels')}


def detect_cuts(path, duration):
    """Real shot-change detection. Short media legitimately yields no cut."""
    if not duration or duration < 2.0: return []
    p = subprocess.run([FF, '-v', 'info', '-i', str(path), '-filter:v', "select='gt(scene,0.35)',showinfo",
                        '-f', 'null', '-'], capture_output=True, text=True, timeout=600)
    times = sorted({round(float(m), 3) for m in re.findall(r'pts_time:([0-9.]+)', p.stderr or '')})
    # A cut is only meaningful if it leaves usable material on both sides.
    return [t for t in times if 0.4 < t < duration - 0.4]


def segment(duration, cuts):
    bounds = [0.0] + list(cuts) + [round(duration, 3)]
    return [{'index': i, 'start': round(bounds[i], 3), 'end': round(bounds[i + 1], 3)}
            for i in range(len(bounds) - 1) if bounds[i + 1] - bounds[i] > 0.01]


def frame_at(path, ts, dest):
    subprocess.run([FF, '-ss', f'{max(ts, 0):.3f}', '-i', str(path), '-frames:v', '1', '-q:v', '2', '-y', str(dest)],
                   capture_output=True, check=True, timeout=180)
    return dest.is_file() and dest.stat().st_size > 0


def frame_quality(img):
    """Reject black/blurred/transition frames. Sharpness via a Laplacian-style gradient measure."""
    import numpy as np
    g = np.asarray(img.convert('L'), dtype=np.float32)
    if g.size == 0: return {'usable': False, 'reason': 'EMPTY'}
    mean = float(g.mean()); std = float(g.std())
    lap = (g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4.0 * g[1:-1, 1:-1]) if g.shape[0] > 2 and g.shape[1] > 2 else None
    sharp = float(lap.var()) if lap is not None else 0.0
    usable = mean >= 12.0 and std >= 8.0 and sharp >= 12.0
    reason = None if usable else ('NEAR_BLACK' if mean < 12 else 'LOW_CONTRAST' if std < 8 else 'MOTION_BLURRED')
    return {'usable': usable, 'reason': reason, 'brightness': round(mean, 2),
            'contrast': round(std, 2), 'sharpness': round(sharp, 2),
            'score': round(sharp * min(std, 60.0), 2)}


# ------------------------------------------------------------------ stage: analyze
def analyze_stage():
    started = time.time(); c, e = client()
    from google.oauth2 import service_account
    from googleapiclient.discovery import build as gbuild
    from googleapiclient.http import MediaIoBaseDownload
    from PIL import Image
    sys.path.insert(0, str(R / 'src'))
    from kdi_media.audio_intelligence import file_sha256
    from kdi_media.providers.local_atomic_adapter import LocalAtomicObservationProvider

    videos = {x['file_name']: x for x in cohort_videos(c)}
    missing = [f for f in TARGETS if f not in videos]
    if missing: raise RuntimeError('TARGET_OUTSIDE_COHORT:' + json.dumps(missing))
    ids = [videos[f]['id'] for f in TARGETS]
    dests = {x['asset_id']: x for x in (c.table('asset_destinations').select('asset_id,destination_google_file_id')
             .in_('asset_id', ids).eq('upload_status', 'VERIFIED').execute().data or [])}

    results = []
    if CKPT.exists():
        results = [x for x in json.loads(CKPT.read_text(encoding='utf-8')).get('assets', []) if x.get('status') == 'ANALYZED']
    done = {x['asset_id'] for x in results}

    provider = LocalAtomicObservationProvider(str(R / '.kdi-models/SmolVLM2-500M-Video-Instruct'), max_new_tokens=6)
    cp = e.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(R / '.secrets/kdi-media-reader.json')
    drive = gbuild('drive', 'v3', credentials=service_account.Credentials.from_service_account_file(
        cp, scopes=['https://www.googleapis.com/auth/drive.readonly']), cache_discovery=False)

    for name in TARGETS:
        a = videos[name]; aid = a['id']
        if aid in done: continue
        t0 = time.time(); src_fp = a.get('content_hash') or a.get('checksum_sha256')
        d = dests.get(aid)
        if not d: raise RuntimeError('MASTER_UNAVAILABLE:' + name)
        work = WORK / aid; shutil.rmtree(work, ignore_errors=True); work.mkdir(parents=True)
        td = Path(tempfile.mkdtemp(prefix='kdi-fi30-')); media = td / name
        try:
            with media.open('wb') as fh:
                dl = MediaIoBaseDownload(fh, drive.files().get_media(fileId=d['destination_google_file_id'],
                                         supportsAllDrives=True), chunksize=8 * 1024 * 1024)
                fin = False
                while not fin: _, fin = dl.next_chunk(num_retries=3)
            if file_sha256(media) != src_fp: raise RuntimeError('MASTER_HASH_MISMATCH:' + name)
            tech = probe_media(media)
            duration = tech['duration_seconds'] or 0.0
            cuts = detect_cuts(media, duration)
            scenes = segment(duration, cuts)
            run_id = uid(f'{aid}:{src_fp}:{PROC}')
            c.table('semantic_analysis_runs').upsert({'id': run_id, 'asset_id': aid,
                'run_type': 'FULL_INDEX_SCENE_SEMANTICS', 'status': 'RUNNING',
                'semantic_spec_version': SPEC, 'ontology_version': ONT, 'processor_version': PROC,
                'configuration_fingerprint': sha(PROC, MODEL, 'scene_v1'), 'source_fingerprint': src_fp,
                'provider': 'LOCAL_TRANSFORMERS', 'model': MODEL,
                'metadata': {'phase': 'FULL_INDEX_30', 'external_calls': 0,
                             'detected_cuts': cuts, 'scene_count': len(scenes)}}, on_conflict='id').execute()

            scene_rows = []
            for sc in scenes:
                span = sc['end'] - sc['start']
                # Candidate sampling: enough coverage to choose a representative frame, more for longer scenes.
                n = 1 if span < 1.0 else 3 if span < 4.0 else 6
                cands = [sc['start'] + span * (i + 1) / (n + 1) for i in range(n)]
                picked = []
                for ci, ts in enumerate(cands):
                    fpath = work / f"s{sc['index']}_c{ci}.jpg"
                    if not frame_at(media, ts, fpath): continue
                    with Image.open(fpath) as im:
                        q = frame_quality(im)
                    picked.append({'ts': round(ts, 3), 'path': str(fpath), **q})
                usable = [x for x in picked if x['usable']] or picked
                if not usable: raise RuntimeError('NO_DECODABLE_FRAME:' + name)
                usable.sort(key=lambda x: -x['score'])
                keep = usable[:1] if span < 4.0 else usable[:2]
                kfs = []
                for ki, cand in enumerate(sorted(keep, key=lambda x: x['ts'])):
                    with Image.open(cand['path']) as im:
                        rgb = im.convert('RGB'); rgb.load()
                        obs = provider.analyze_image_atomic(rgb)['observations']
                    if any(any(t in str(o.get('raw_response', '')).lower() for t in UNSAFE)
                           and o.get('state') == 'OBSERVED' for o in obs):
                        raise RuntimeError('CLINICAL_GATE_FAILED:' + name)
                    acc = [CONCEPTS[o['category']][2] for o in obs if o['state'] == 'OBSERVED']
                    desc = ('Representative frame showing ' + ', '.join(acc) + '.') if acc else \
                        'Representative frame with no determinate visual observation.'
                    kfs.append({'keyframe_id': uid(f"{run_id}:kf:{sc['index']}:{ki}"), 'timestamp': cand['ts'],
                                'frame_index': int(cand['ts'] * (tech['fps'] or 30)),
                                'path': cand['path'], 'quality': {k: cand[k] for k in ('brightness', 'contrast', 'sharpness', 'score')},
                                'selection_reason': 'QUALITY_SCORED_REPRESENTATIVE',
                                'visual_description': desc, 'observations': obs, 'accepted': acc})
                merged = {}
                for kf in kfs:
                    for o in kf['observations']:
                        cur = merged.get(o['category'])
                        if cur is None or (o['state'] == 'OBSERVED' and cur != 'OBSERVED'): merged[o['category']] = o['state']
                scene_rows.append({'index': sc['index'], 'start': sc['start'], 'end': sc['end'],
                                   'keyframes': kfs, 'merged_states': merged})

            # ---- persist canonical scene truth ----
            c.table('asset_scenes').update({'canonical_active': False}).eq('asset_id', aid)\
                .eq('canonical_active', True).execute()
            scene_out = []
            for sc in scene_rows:
                sid = uid(f"{run_id}:scene:{sc['index']}")
                acc = sorted({CONCEPTS[k][2] for k, v in sc['merged_states'].items() if v == 'OBSERVED'})
                lit = (f"Scene {sc['index'] + 1} of {name}: " + (', '.join(acc) if acc else
                       'no determinate visual observation') + '.')
                c.table('asset_scenes').upsert({'id': sid, 'asset_id': aid, 'scene_index': sc['index'],
                    'start_seconds': sc['start'], 'end_seconds': sc['end'],
                    'scene_type': 'CANONICAL_SEMANTIC_SCENE', 'literal_description': lit,
                    'short_description': lit, 'detection_method': 'LOCAL_SHOT_CHANGE_AND_QUALITY_V1',
                    'confidence': 0.8, 'review_status': 'NOT_REVIEWED', 'source': 'FULL_INDEX_30',
                    'processor_version': PROC, 'configuration_version': PROC,
                    'semantic_label': 'CANONICAL_SEMANTIC_SCENE',
                    'semantic_state': 'OBSERVED' if acc else 'UNKNOWN',
                    'semantic_version': SPEC, 'canonical_active': True,
                    'semantic_analysis_run_id': run_id, 'analysis_run_id': None,
                    'metadata': {'phase': 'FULL_INDEX_30', 'detected_cuts': cuts,
                                 'keyframe_count': len(sc['keyframes'])}}, on_conflict='id').execute()
                for kf in sc['keyframes']:
                    c.table('asset_keyframes').upsert({'id': kf['keyframe_id'], 'asset_id': aid, 'scene_id': sid,
                        'timestamp_seconds': kf['timestamp'], 'frame_index': kf['frame_index'],
                        'selection_reason': kf['selection_reason'], 'visual_description': kf['visual_description'],
                        'technical_quality_score': min(1.0, kf['quality']['score'] / 5000.0),
                        'semantic_importance_score': 0.8 if kf['accepted'] else 0.4,
                        'is_representative': True, 'review_status': 'NOT_REVIEWED',
                        'source_fingerprint': src_fp, 'processor_version': PROC,
                        'semantic_analysis_run_id': run_id, 'semantic_version': SPEC,
                        'metadata': {'phase': 'FULL_INDEX_30', 'quality': kf['quality']}},
                        on_conflict='id').execute()
                # scene assertions + evidence
                arows = []; erows = []; positives = []
                for cat, state in sorted(sc['merged_states'].items()):
                    lid, code, label, ctype, critical = CONCEPTS[cat]
                    asid = uid(f"{run_id}:assert:{sc['index']}:{code}")
                    kf0 = sc['keyframes'][0]
                    arows.append({'id': asid, 'asset_id': aid, 'scene_id': sid, 'keyframe_id': kf0['keyframe_id'],
                        'layer_id': lid, 'subject_type': 'SCENE', 'predicate': code,
                        'canonical_concept_code': code, 'canonical_concept_type': lid, 'value_text': label,
                        'semantic_state': state, 'confidence': 0.7, 'confidence_source': 'MEDIUM',
                        'search_critical': critical, 'analysis_run_id': run_id, 'origin': 'AI_MODEL',
                        'ontology_version': ONT, 'semantic_spec_version': SPEC,
                        'human_review_status': 'PENDING', 'active': True, 'source_fingerprint': src_fp,
                        'idempotency_key': f"fullindex30:{run_id}:{sc['index']}:{code}"})
                    erows.append({'assertion_id': asid, 'evidence_type': 'KEYFRAME_LEVEL',
                        'polarity': 'POSITIVE' if state == 'OBSERVED' else 'NEGATIVE', 'completeness': 'COMPLETE',
                        'asset_id': aid, 'scene_id': sid, 'keyframe_id': kf0['keyframe_id'],
                        'start_time': kf0['timestamp'], 'end_time': kf0['timestamp'], 'evidence_score': 0.7,
                        'source_fingerprint': src_fp, 'analysis_run_id': run_id})
                    if state == 'OBSERVED':
                        positives.append({'assertion_id': asid, 'canonical_code': code, 'display_text': label,
                                          'concept_type': ctype, 'semantic_state': 'OBSERVED', 'confidence': 0.7,
                                          'origin': 'AI_MODEL', 'search_critical': critical,
                                          'resolution_source': 'UNVERIFIED_AI'})
                c.table('semantic_assertions').update({'active': False}).eq('scene_id', sid)\
                    .eq('active', True).execute()
                # semantic_assertion_evidence_guard is a deferred constraint trigger, and PostgREST
                # commits each request on its own, so a search-critical row cannot be written before
                # its evidence exists. Land the assertion as non-critical, attach the evidence, then
                # raise search_critical to its true value so the guard validates the final state.
                for row in arows:
                    c.table('semantic_assertions').upsert({**row, 'search_critical': False}, on_conflict='id').execute()
                have = {x['assertion_id'] for x in (c.table('semantic_assertion_evidence').select('assertion_id')
                        .in_('assertion_id', [r['id'] for r in arows]).execute().data or [])}
                new_ev = [r for r in erows if r['assertion_id'] not in have]
                if new_ev: c.table('semantic_assertion_evidence').insert(new_ev).execute()
                for row in arows:
                    if row['search_critical']:
                        c.table('semantic_assertions').update({'search_critical': True}).eq('id', row['id']).execute()
                search_text = norm(f"{name} scene {sc['index'] + 1} {lit} " + ' '.join(acc))
                if any(t in search_text.lower() for t in UNSAFE):
                    raise RuntimeError('SCENE_DOCUMENT_CLINICAL_LEAKAGE:' + name)
                scene_out.append({'scene_id': sid, 'index': sc['index'], 'start': sc['start'], 'end': sc['end'],
                                  'literal': lit, 'accepted_concepts': acc, 'positives': positives,
                                  'search_text': search_text,
                                  'keyframes': [{'keyframe_id': k['keyframe_id'], 'path': k['path'],
                                                 'timestamp': k['timestamp'], 'frame_index': k['frame_index'],
                                                 'selection_reason': k['selection_reason'],
                                                 'visual_description': k['visual_description'],
                                                 'quality': k['quality']} for k in sc['keyframes']]})
            # Persist real decoded technical metadata rather than leaving core fields NULL.
            try: rot = int(float(tech.get('rotation'))) if tech.get('rotation') is not None else None
            except Exception: rot = None
            ar = tech['aspect_ratio'] if isinstance(tech.get('aspect_ratio'), (int, float)) else (
                round(tech['width_px'] / tech['height_px'], 6) if tech.get('width_px') and tech.get('height_px') else None)
            # service_role currently lacks write privilege on asset_technical_metadata. The probe
            # values are still persisted on the analysis run and in the temporal coverage artifact,
            # so the blocker is recorded rather than worked around by changing database grants.
            tech_persisted = None
            try:
                c.table('asset_technical_metadata').upsert({'asset_id': aid,
                    'width_px': tech['width_px'], 'height_px': tech['height_px'], 'aspect_ratio': ar,
                    'orientation': tech['orientation'], 'duration_seconds': tech['duration_seconds'],
                    'fps': tech['fps'], 'codec': tech['codec'], 'rotation_degrees': rot,
                    'has_audio': tech['has_audio'], 'audio_codec': tech['audio_codec'],
                    'sample_rate_hz': int(tech['audio_sample_rate']) if tech.get('audio_sample_rate') else None,
                    'provenance': 'FULL_INDEX_30_FFPROBE', 'analysis_run_id': run_id,
                    'metadata': {'pix_fmt': tech['pix_fmt'], 'bit_rate': tech['bit_rate'],
                                 'format_name': tech['format_name'], 'size_bytes': tech['size_bytes'],
                                 'audio_channels': tech['audio_channels'], 'source_fingerprint': src_fp}},
                    on_conflict='asset_id').execute()
                tech_persisted = 'asset_technical_metadata'
            except Exception as exc:
                tech_persisted = f'BLOCKED:{type(exc).__name__}'
            c.table('semantic_analysis_runs').update({'status': 'COMPLETED',
                'metadata': {'phase': 'FULL_INDEX_30', 'external_calls': 0, 'detected_cuts': cuts,
                             'scene_count': len(scene_out),
                             'keyframe_count': sum(len(s['keyframes']) for s in scene_out),
                             'technical': tech}}).eq('id', run_id).execute()
            results.append({'asset_id': aid, 'filename': name, 'status': 'ANALYZED', 'run_id': run_id,
                            'source_fingerprint': src_fp, 'technical': tech, 'detected_cuts': cuts,
                            'technical_metadata_persisted_to': tech_persisted,
                            'scenes': scene_out, 'seconds': round(time.time() - t0, 3)})
            CKPT.write_text(json.dumps({'status': 'RUNNING', 'planned': len(TARGETS), 'assets': results},
                                       indent=2) + '\n', encoding='utf-8')
            print(json.dumps({'file': name, 'duration': tech['duration_seconds'], 'cuts': len(cuts),
                              'scenes': len(scene_out),
                              'keyframes': sum(len(s['keyframes']) for s in scene_out),
                              'seconds': round(time.time() - t0, 1)}), flush=True)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    CKPT.write_text(json.dumps({'status': 'ANALYZED', 'planned': len(TARGETS), 'completed': len(results),
                                'assets': results}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'ANALYZED', 'completed': len(results),
                      'elapsed_seconds': round(time.time() - started, 1)}))


# ------------------------------------------------------------------ stage: embed
def embed_stage():
    started = time.time(); c, _ = client()
    import numpy as np
    from PIL import Image
    from sentence_transformers import SentenceTransformer
    sys.path.insert(0, str(R / 'dashboard'))
    from visual_indexing.openclip_encoder import OpenClipEncoder

    data = json.loads(CKPT.read_text(encoding='utf-8'))
    snaps = sorted((Path.home() / '.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots').glob('*'))
    e5 = SentenceTransformer(str(snaps[-1]), local_files_only=True)
    clip = OpenClipEncoder()
    built = {'scene_documents': 0, 'text_scene': 0, 'visual_scene': 0, 'visual_keyframe': 0}

    for a in data['assets']:
        aid = a['asset_id']; run_id = a['run_id']; src = a['source_fingerprint']
        build_run = uid(f'{run_id}:scenebuild')
        c.table('search_document_build_runs').upsert({'id': build_run, 'status': 'COMPLETE',
            'search_document_version': 'kdi_search_document_v1', 'builder_version': PROC,
            'configuration_version': PROC, 'configuration_fingerprint': sha(PROC, 'scene_docs'),
            'semantic_spec_version': SPEC, 'ontology_version': ONT, 'source_semantic_version': SPEC,
            'asset_count': 1, 'asset_document_count': 0, 'scene_document_count': len(a['scenes']),
            'event_document_count': 0, 'errors': [], 'started_at': now(), 'completed_at': now()},
            on_conflict='id').execute()
        for sc in a['scenes']:
            sid = sc['scene_id']; text = sc['search_text']
            docfp = hashlib.sha256(text.encode()).hexdigest()
            docid = uid(f'{run_id}:scenedoc:{sid}')
            c.table('search_document_builds').update({'active': False, 'stale': True})\
                .eq('scene_id', sid).eq('document_type', 'SCENE').eq('active', True).execute()
            c.table('search_document_builds').upsert({'id': docid, 'build_run_id': build_run, 'asset_id': aid,
                'scene_id': sid, 'document_type': 'SCENE', 'filename': a['filename'], 'media_type': 'VIDEO',
                'start_time': sc['start'], 'end_time': sc['end'],
                'normalized_document': {'scene_index': sc['index'], 'literal_description': sc['literal'],
                                        'accepted_concepts': sc['accepted_concepts'],
                                        'keyframes': len(sc['keyframes']), 'grounding': 'scene_keyframe_evidence'},
                'search_text': text, 'positive_concepts': sc['positives'], 'negative_concepts': [],
                'search_document_version': 'kdi_search_document_v1', 'builder_version': PROC,
                'configuration_version': PROC, 'configuration_fingerprint': sha(PROC, 'scene_docs'),
                'semantic_spec_version': SPEC, 'ontology_version': ONT, 'source_semantic_version': SPEC,
                'source_fingerprint': src, 'source_semantic_fingerprint': src, 'document_fingerprint': docfp,
                'status': 'READY', 'review_status': 'AI_UNREVIEWED', 'human_approved': False,
                'review_required': False, 'active': True, 'stale': False, 'generated_at': now()},
                on_conflict='id').execute()
            c.table('scene_search_documents').upsert({'scene_id': sid, 'asset_id': aid, 'searchable_text': text,
                'short_description': sc['literal'], 'search_concepts': sc['accepted_concepts'],
                'structured_document': {'scene_index': sc['index'], 'keyframes': len(sc['keyframes'])},
                'source_hash': src, 'document_version': 'kdi_search_document_v1', 'build_status': 'READY',
                'built_at': now(), 'last_error': None}, on_conflict='scene_id').execute()
            built['scene_documents'] += 1

            vec = np.asarray(e5.encode('passage: ' + text, normalize_embeddings=True), dtype=np.float32)
            tfp = sha(text, TNORM, docfp)
            vfp = hashlib.sha256((E5 + '\x1f' + E5VER + '\x1f384\x1f' + tfp).encode()
                                 + struct.pack('<' + 'f' * 384, *vec.tolist())).hexdigest()
            tid = uid(f'{run_id}:textscene:{sid}')
            c.table('semantic_embeddings').update({'active': False, 'stale': True}).eq('scene_id', sid)\
                .eq('representation_type', 'TEXT_SCENE').eq('active', True).execute()
            c.table('semantic_embeddings').upsert({'id': tid, 'asset_id': aid, 'scene_id': sid,
                'embedding_scope': 'TEXT_SCENE', 'representation_type': 'TEXT_SCENE',
                'provider': 'sentence_transformers', 'model': E5, 'model_version': E5VER,
                'version': 'kdi_text_embedding_v1', 'embedding_version': 'kdi_text_embedding_v1',
                'embedding_bundle_version': 'kdi_embedding_bundle_v1', 'dimensions': 384,
                'embedding': vec.tolist(), 'source_fingerprint': tfp, 'source_text_fingerprint': tfp,
                'source_document_fingerprint': docfp, 'vector_fingerprint': vfp,
                'text_normalization_version': TNORM, 'semantic_spec_version': SPEC,
                'source_semantic_version': SPEC, 'ontology_version': ONT, 'analysis_run_id': run_id,
                'active': True, 'stale': False, 'review_status': 'AI_UNREVIEWED', 'generated_at': now(),
                'metadata': {'source_kind': 'SCENE', 'source_unit_id': docid,
                             'construction': 'passage_prefix_canonical_search_text_v1'}},
                on_conflict='id').execute()
            built['text_scene'] += 1

            kvecs = []
            for kf in sc['keyframes']:
                p = Path(kf['path'])
                if not p.is_file(): raise RuntimeError('KEYFRAME_IMAGE_MISSING:' + kf['keyframe_id'])
                with Image.open(p) as im:
                    kv = clip.embed_image(im)
                kvecs.append(kv)
                kvfp = hashlib.sha256((CLIP_MODEL + '\x1f' + CLIP_VER + '\x1f512\x1f' + kf['keyframe_id']).encode()
                                      + struct.pack('<' + 'f' * 512, *kv)).hexdigest()
                kid = uid(f"{run_id}:vkf:{kf['keyframe_id']}")
                c.table('semantic_embeddings').update({'active': False, 'stale': True})\
                    .eq('keyframe_id', kf['keyframe_id']).eq('representation_type', 'VISUAL_KEYFRAME')\
                    .eq('active', True).execute()
                c.table('semantic_embeddings').upsert({'id': kid, 'asset_id': aid, 'scene_id': sid,
                    'keyframe_id': kf['keyframe_id'], 'embedding_scope': 'VISUAL_KEYFRAME',
                    'representation_type': 'VISUAL_KEYFRAME', 'provider': 'open_clip', 'model': CLIP_MODEL,
                    'model_version': CLIP_VER, 'version': 'kdi_visual_embedding_v1',
                    'embedding_version': 'kdi_visual_embedding_v1',
                    'embedding_bundle_version': 'kdi_embedding_bundle_v1', 'dimensions': 512,
                    'embedding': kv, 'source_fingerprint': src, 'vector_fingerprint': kvfp,
                    'preprocessing_version': 'openclip_exif_rgb_bicubic_v1', 'semantic_spec_version': SPEC,
                    'source_semantic_version': SPEC, 'ontology_version': ONT, 'analysis_run_id': run_id,
                    'active': True, 'stale': False, 'review_status': 'AI_UNREVIEWED', 'generated_at': now(),
                    'metadata': {'timestamp_seconds': kf['timestamp'], 'frame_index': kf['frame_index'],
                                 'selection_reason': kf['selection_reason'], 'quality': kf['quality']}},
                    on_conflict='id').execute()
                built['visual_keyframe'] += 1

            arr = np.asarray(kvecs, dtype=np.float32)
            pooled = arr.mean(axis=0)
            pooled = pooled / max(float(np.linalg.norm(pooled)), 1e-12)
            svfp = hashlib.sha256((CLIP_MODEL + '\x1f' + CLIP_VER + '\x1f512\x1f' + sid).encode()
                                  + struct.pack('<' + 'f' * 512, *pooled.tolist())).hexdigest()
            svid = uid(f'{run_id}:vscene:{sid}')
            c.table('semantic_embeddings').update({'active': False, 'stale': True}).eq('scene_id', sid)\
                .eq('representation_type', 'VISUAL_SCENE').eq('active', True).execute()
            c.table('semantic_embeddings').upsert({'id': svid, 'asset_id': aid, 'scene_id': sid,
                'embedding_scope': 'VISUAL_SCENE', 'representation_type': 'VISUAL_SCENE',
                'provider': 'open_clip', 'model': CLIP_MODEL, 'model_version': CLIP_VER,
                'version': 'kdi_visual_embedding_v1', 'embedding_version': 'kdi_visual_embedding_v1',
                'embedding_bundle_version': 'kdi_embedding_bundle_v1', 'dimensions': 512,
                'embedding': pooled.tolist(), 'source_fingerprint': src, 'vector_fingerprint': svfp,
                'preprocessing_version': 'l2_mean_pool_l2_v1', 'semantic_spec_version': SPEC,
                'source_semantic_version': SPEC, 'ontology_version': ONT, 'analysis_run_id': run_id,
                'active': True, 'stale': False, 'review_status': 'AI_UNREVIEWED', 'generated_at': now(),
                'metadata': {'aggregation': 'l2_mean_pool_l2_v1', 'start_seconds': sc['start'],
                             'end_seconds': sc['end'],
                             'member_keyframe_ids': [k['keyframe_id'] for k in sc['keyframes']]}},
                on_conflict='id').execute()
            built['visual_scene'] += 1
        print(json.dumps({'file': a['filename'], 'scenes': len(a['scenes']), 'built': built}), flush=True)

    data['status'] = 'PASS'; data['built'] = built
    CKPT.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', **built, 'elapsed_seconds': round(time.time() - started, 1)}))


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else 'analyze'
    if stage == 'analyze': analyze_stage()
    elif stage == 'embed': embed_stage()
    else: raise SystemExit('unknown stage: ' + stage)
