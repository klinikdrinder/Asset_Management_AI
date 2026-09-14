"""Read-only revalidation of the already-canonical video segmentation (§27).

Downloads each of the 8 videos that already carry PHASE3_TIMELINE canonical scenes, runs the same
shot-change detector used for the corrective pass, and compares detected cuts against the stored
scene boundaries. Reports agreement; changes nothing.
"""
from __future__ import annotations
import json, os, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild
from googleapiclient.http import MediaIoBaseDownload

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'src'))
sys.path.insert(0, str(R / 'scripts'))
from kdi_media.audio_intelligence import file_sha256
from full_index_30_scene_index import probe_media, detect_cuts

OUT = R / 'reports/semantic-search/rollout/full-index-30'; OUT.mkdir(parents=True, exist_ok=True)
TOL = 0.75  # seconds; a stored boundary matches a detected cut within this tolerance


def env():
    e = {}
    for f in (R / '.env', R / '.env.local', R / 'dashboard/.env.local'):
        if f.exists(): e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ); return e


def main():
    e = env()
    c = create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'], e['SUPABASE_SERVICE_ROLE_KEY'])
    scenes = c.table('asset_scenes').select('id,asset_id,scene_index,start_seconds,end_seconds,detection_method')\
        .eq('canonical_active', True).execute().data or []
    by_asset = {}
    for s in scenes: by_asset.setdefault(s['asset_id'], []).append(s)
    ids = sorted(by_asset)
    assets = {}
    for i in range(0, len(ids), 50):
        for x in (c.table('assets').select('id,file_name,mime_type,content_hash,checksum_sha256')
                  .in_('id', ids[i:i + 50]).execute().data or []): assets[x['id']] = x
    vids = {k: v for k, v in assets.items() if str(v['mime_type']).startswith('video')}
    dests = {x['asset_id']: x for x in (c.table('asset_destinations').select('asset_id,destination_google_file_id')
             .in_('asset_id', list(vids)).eq('upload_status', 'VERIFIED').execute().data or [])}
    cp = e.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(R / '.secrets/kdi-media-reader.json')
    drive = gbuild('drive', 'v3', credentials=service_account.Credentials.from_service_account_file(
        cp, scopes=['https://www.googleapis.com/auth/drive.readonly']), cache_discovery=False)

    rows = []
    for aid, a in sorted(vids.items(), key=lambda kv: kv[1]['file_name']):
        sc = sorted(by_asset[aid], key=lambda x: float(x['start_seconds']))
        if all(s['detection_method'] == 'LOCAL_SHOT_CHANGE_AND_QUALITY_V1' for s in sc):
            continue  # produced by this phase; validated at build time
        td = Path(tempfile.mkdtemp(prefix='kdi-reval-')); media = td / a['file_name']
        try:
            with media.open('wb') as fh:
                dl = MediaIoBaseDownload(fh, drive.files().get_media(
                    fileId=dests[aid]['destination_google_file_id'], supportsAllDrives=True), chunksize=8 * 1024 * 1024)
                fin = False
                while not fin: _, fin = dl.next_chunk(num_retries=3)
            src = a.get('content_hash') or a.get('checksum_sha256')
            identity = file_sha256(media) == src
            tech = probe_media(media)
            dur = tech['duration_seconds'] or 0.0
            detected = detect_cuts(media, dur)
            stored = [round(float(s['start_seconds']), 3) for s in sc if float(s['start_seconds']) > 0.01]
            matched = [d for d in detected if any(abs(d - b) <= TOL for b in stored)]
            unmatched_detected = [d for d in detected if d not in matched]
            unmatched_stored = [b for b in stored if not any(abs(d - b) <= TOL for d in detected)]
            covered = round(max(float(s['end_seconds']) for s in sc) - min(float(s['start_seconds']) for s in sc), 3)
            rows.append({'asset_id': aid, 'filename': a['file_name'], 'identity_match': identity,
                'duration_seconds': dur, 'canonical_scenes': len(sc),
                'stored_boundaries': stored, 'detected_cuts': detected,
                'boundaries_confirmed': matched, 'detected_not_segmented': unmatched_detected,
                'stored_without_detected_cut': unmatched_stored,
                'coverage_seconds': covered,
                'coverage_ratio': round(covered / dur, 4) if dur else None,
                'starts_at_origin': float(sc[0]['start_seconds']) <= 0.25,
                'reaches_end': max(float(s['end_seconds']) for s in sc) >= dur - max(0.25, dur * 0.05),
                'segmentation_agrees': not unmatched_detected,
                'verdict': 'AGREES_WITH_MEDIA' if not unmatched_detected else 'UNDER_SEGMENTED'})
            print(json.dumps({'file': a['file_name'], 'dur': dur, 'scenes': len(sc),
                              'detected_cuts': len(detected), 'unmatched': len(unmatched_detected),
                              'verdict': rows[-1]['verdict']}), flush=True)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    under = [x for x in rows if x['verdict'] != 'AGREES_WITH_MEDIA']
    (OUT / 'full_index_30_segmentation_revalidation.json').write_text(json.dumps({
        'generated_at': datetime.now(timezone.utc).isoformat(), 'phase': 'FULL_INDEX_30',
        'status': 'PASS' if not under else 'REVIEW',
        'method': "ffmpeg select='gt(scene,0.35)' shot-change detection compared against stored canonical boundaries",
        'tolerance_seconds': TOL, 'videos_revalidated': len(rows),
        'segmentation_agrees': len(rows) - len(under), 'under_segmented': [x['filename'] for x in under],
        'rebuilt': 0, 'note': 'Read-only revalidation. Existing canonical segmentation was not rebuilt.',
        'assets': rows}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS' if not under else 'REVIEW', 'videos': len(rows),
                      'under_segmented': [x['filename'] for x in under]}))


if __name__ == '__main__':
    main()
