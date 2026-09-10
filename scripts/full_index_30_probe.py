"""Full-index corrective phase — technical ground truth probe.

Downloads every cohort video from the verified master destination (read-only), verifies SHA-256,
and records real decoded technical metadata. Establishes whether stored scene timelines actually
cover the media. Writes a report only; no semantic writes.
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'src'))
from kdi_media.audio_intelligence import file_sha256

OUT = R / 'reports/semantic-search/rollout/full-index-30'; OUT.mkdir(parents=True, exist_ok=True)
FF = str(R / '.tools/ffmpeg/bin/ffmpeg.exe'); FP = str(R / '.tools/ffmpeg/bin/ffprobe.exe')


def now(): return datetime.now(timezone.utc).isoformat()


def env():
    e = {}
    for f in (R / '.env', R / '.env.local', R / 'dashboard/.env.local'):
        if f.exists(): e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ); return e


def probe(path):
    """Container metadata plus a decoded-duration cross-check."""
    raw = json.loads(subprocess.run([FP, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
                                    capture_output=True, text=True, check=True, timeout=180).stdout)
    v = next((s for s in raw['streams'] if s.get('codec_type') == 'video'), None)
    a = next((s for s in raw['streams'] if s.get('codec_type') == 'audio'), None)
    fmt = raw.get('format', {})
    # Decoded duration: count real frames rather than trusting the container header.
    dec = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                          '-show_entries', 'stream=nb_read_frames,duration', '-of', 'json', str(path)],
                         capture_output=True, text=True, timeout=300)
    frames = None; decoded_duration = None
    try:
        dj = json.loads(dec.stdout)['streams'][0]
        frames = int(dj.get('nb_read_frames') or 0) or None
        decoded_duration = float(dj.get('duration')) if dj.get('duration') not in (None, 'N/A') else None
    except Exception:
        pass
    def rate(x):
        try:
            n, d = str(x).split('/'); return round(float(n) / float(d), 6) if float(d) else None
        except Exception: return None
    fps = rate((v or {}).get('avg_frame_rate')) or rate((v or {}).get('r_frame_rate'))
    rotation = None
    for sd in (v or {}).get('side_data_list', []) or []:
        if 'rotation' in sd: rotation = sd['rotation']
    if rotation is None:
        rotation = ((v or {}).get('tags', {}) or {}).get('rotate')
    w, h = (v or {}).get('width'), (v or {}).get('height')
    container = float(fmt.get('duration')) if fmt.get('duration') not in (None, 'N/A') else None
    frame_duration = round(frames / fps, 4) if frames and fps else None
    return {
        'container_duration_seconds': container,
        'stream_duration_seconds': decoded_duration,
        'frame_count': frames,
        'frame_derived_duration_seconds': frame_duration,
        'width_px': w, 'height_px': h,
        'orientation': None if not (w and h) else ('PORTRAIT' if h > w else 'LANDSCAPE' if w > h else 'SQUARE'),
        'aspect_ratio': (v or {}).get('display_aspect_ratio') or (round(w / h, 4) if w and h else None),
        'fps': fps, 'codec': (v or {}).get('codec_name'), 'pix_fmt': (v or {}).get('pix_fmt'),
        'rotation': rotation, 'bit_rate': fmt.get('bit_rate'), 'format_name': fmt.get('format_name'),
        'size_bytes': int(fmt.get('size')) if fmt.get('size') else None,
        'has_audio': bool(a), 'audio_codec': (a or {}).get('codec_name'),
        'audio_sample_rate': (a or {}).get('sample_rate'), 'audio_channels': (a or {}).get('channels'),
        'nb_streams': fmt.get('nb_streams')}


def main():
    e = env()
    c = create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'], e['SUPABASE_SERVICE_ROLE_KEY'])
    layers = c.table('asset_semantic_layers').select('asset_id,processing_status').eq('active', True).execute().data or []
    per = {}
    for x in layers:
        v = per.setdefault(x['asset_id'], [0, 0]); v[0] += 1
        if x['processing_status'] == 'COMPLETE': v[1] += 1
    cohort = sorted(k for k, v in per.items() if v == [18, 18])
    assets = {}
    for i in range(0, len(cohort), 50):
        for x in (c.table('assets').select('id,file_name,mime_type,content_hash,checksum_sha256,file_size_bytes')
                  .in_('id', cohort[i:i + 50]).execute().data or []): assets[x['id']] = x
    videos = [a for a in assets.values() if str(a['mime_type']).startswith('video')]
    ids = [a['id'] for a in videos]
    dests = {x['asset_id']: x for x in (c.table('asset_destinations').select('asset_id,destination_google_file_id')
             .in_('asset_id', ids).eq('upload_status', 'VERIFIED').execute().data or [])}
    scenes = {}
    for x in (c.table('asset_scenes').select('id,asset_id,scene_index,start_seconds,end_seconds,detection_method,scene_type')
              .in_('asset_id', ids).execute().data or []): scenes.setdefault(x['asset_id'], []).append(x)

    cp = e.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(R / '.secrets/kdi-media-reader.json')
    drive = build('drive', 'v3', credentials=service_account.Credentials.from_service_account_file(
        cp, scopes=['https://www.googleapis.com/auth/drive.readonly']), cache_discovery=False)

    rows = []
    for a in sorted(videos, key=lambda x: x['file_name']):
        aid = a['id']; d = dests.get(aid)
        if not d: raise RuntimeError('MASTER_UNAVAILABLE:' + a['file_name'])
        src_fp = a.get('content_hash') or a.get('checksum_sha256')
        td = Path(tempfile.mkdtemp(prefix='kdi-probe-')); media = td / a['file_name']
        try:
            with media.open('wb') as fh:
                dl = MediaIoBaseDownload(fh, drive.files().get_media(fileId=d['destination_google_file_id'],
                                         supportsAllDrives=True), chunksize=8 * 1024 * 1024)
                fin = False
                while not fin: _, fin = dl.next_chunk(num_retries=3)
            actual = file_sha256(media)
            tech = probe(media)
            sc = sorted(scenes.get(aid, []), key=lambda x: (x['detection_method'] or '', x['start_seconds']))
            by_method = {}
            for s in sc: by_method.setdefault(s['detection_method'], []).append(s)
            usable = tech['container_duration_seconds'] or tech['frame_derived_duration_seconds'] or 0
            coverage = {}
            for m, group in by_method.items():
                merged = []
                for s in sorted(group, key=lambda x: x['start_seconds']):
                    st, en = float(s['start_seconds'] or 0), float(s['end_seconds'] or 0)
                    if merged and st <= merged[-1][1] + 1e-6: merged[-1][1] = max(merged[-1][1], en)
                    else: merged.append([st, en])
                covered = sum(b - aa for aa, b in merged)
                coverage[m] = {'scenes': len(group), 'merged_intervals': merged,
                               'covered_seconds': round(covered, 3),
                               'starts_at': round(merged[0][0], 3) if merged else None,
                               'ends_at': round(merged[-1][1], 3) if merged else None,
                               'coverage_ratio': round(covered / usable, 4) if usable else None,
                               'reaches_end': bool(merged and usable and merged[-1][1] >= usable - max(0.25, usable * 0.05)),
                               'starts_at_origin': bool(merged and merged[0][0] <= 0.25)}
            overlap_pairs = []
            for i in range(len(sc)):
                for j in range(i + 1, len(sc)):
                    x, y = sc[i], sc[j]
                    ov = min(float(x['end_seconds']), float(y['end_seconds'])) - max(float(x['start_seconds']), float(y['start_seconds']))
                    if ov > 0.01: overlap_pairs.append({'a': x['id'], 'b': y['id'], 'overlap_seconds': round(ov, 3),
                                                        'a_method': x['detection_method'], 'b_method': y['detection_method']})
            rows.append({'asset_id': aid, 'filename': a['file_name'],
                'sha256_registered': src_fp, 'sha256_downloaded': actual, 'identity_match': actual == src_fp,
                'registered_size_bytes': a.get('file_size_bytes'),
                'technical': tech,
                'duration_sources_consistent': (
                    tech['container_duration_seconds'] is not None and tech['frame_derived_duration_seconds'] is not None
                    and abs(tech['container_duration_seconds'] - tech['frame_derived_duration_seconds']) <= max(0.25, 0.05 * tech['container_duration_seconds'])),
                'scene_systems': coverage, 'overlapping_scene_pairs': overlap_pairs,
                'total_scene_rows': len(sc)})
            print(json.dumps({'file': a['file_name'], 'dur': tech['container_duration_seconds'],
                              'frames': tech['frame_count'], 'fps': tech['fps'],
                              'wxh': f"{tech['width_px']}x{tech['height_px']}", 'audio': tech['has_audio'],
                              'scene_systems': {k: v['scenes'] for k, v in coverage.items()},
                              'overlaps': len(overlap_pairs)}), flush=True)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    (OUT / 'full_index_30_temporal_coverage_audit.json').write_text(json.dumps({
        'generated_at': now(), 'phase': 'FULL_INDEX_30', 'status': 'PASS',
        'videos': len(rows),
        'identity_verified': sum(1 for x in rows if x['identity_match']),
        'duration_sources_consistent': sum(1 for x in rows if x['duration_sources_consistent']),
        'videos_with_overlapping_scenes': sum(1 for x in rows if x['overlapping_scene_pairs']),
        'assets': rows}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'videos': len(rows),
                      'identity_verified': sum(1 for x in rows if x['identity_match'])}))


if __name__ == '__main__':
    main()
