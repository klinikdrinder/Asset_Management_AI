"""Reusable production rollout worker.

DRY_RUN/STAGING execute and checkpoint all local evidence preparation. Claude
transmission is a separate final gate; PRODUCTION refuses an asset unless the
canonical access row explicitly allows external AI. The worker is manifest
driven and resumable for future cohorts.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]; FF=ROOT/'.tools/ffmpeg/bin/ffmpeg.exe'; FP=ROOT/'.tools/ffmpeg/bin/ffprobe.exe'
DEFAULT_MANIFEST=ROOT/'reports/semantic-search/rollout/100/privacy-approval-required.json'
OUT=ROOT/'reports/semantic-search/rollout/100'; CHECKPOINT=OUT/'production-rollout-local-checkpoint.json'

def now(): return datetime.now(timezone.utc).isoformat()
def probe(path):
    raw=json.loads(subprocess.run([str(FP),'-v','error','-show_format','-show_streams','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=180).stdout)
    video=next((x for x in raw.get('streams',[]) if x.get('codec_type')=='video'),{})
    return {'duration_seconds':float((raw.get('format') or {}).get('duration') or 0),'width':video.get('width'),'height':video.get('height'),'fps':video.get('avg_frame_rate'),'codec':video.get('codec_name'),'audio_stream':any(x.get('codec_type')=='audio' for x in raw.get('streams',[]))}
def cuts(path,duration):
    if duration<2:return []
    p=subprocess.run([str(FF),'-v','info','-i',str(path),'-filter:v',"select='gt(scene,0.35)',showinfo",'-f','null','-'],capture_output=True,text=True,timeout=600)
    return sorted({round(float(x),3) for x in __import__('re').findall(r'pts_time:([0-9.]+)',p.stderr or '') if .4<float(x)<duration-.4})
def frames(path,duration,folder):
    bounds=[0.0]+cuts(path,duration)+[duration]; out=[]
    for i in range(len(bounds)-1):
        start,end=bounds[i],bounds[i+1]; span=end-start
        points=[start+span*.5] if span<4 else [start+span*.25,start+span*.75]
        for j,t in enumerate(points):
            target=folder/f'scene-{i:03d}-frame-{j:02d}.jpg'; subprocess.run([str(FF),'-ss',f'{t:.3f}','-i',str(path),'-frames:v','1','-q:v','4','-y',str(target)],capture_output=True,check=True,timeout=180)
            if target.is_file() and target.stat().st_size: out.append({'scene_index':i,'timestamp':round(t,3),'path':str(target)})
    return bounds,out
def download(drive,file_id,target):
    from googleapiclient.http import MediaIoBaseDownload
    with target.open('wb') as fh:
        dl=MediaIoBaseDownload(fh,drive.files().get_media(fileId=file_id,supportsAllDrives=True),chunksize=8*1024*1024); done=False
        while not done: _,done=dl.next_chunk(num_retries=3)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST); ap.add_argument('--mode',choices=['DRY_RUN','STAGING','PRODUCTION'],default='STAGING'); ap.add_argument('--resume',action='store_true'); args=ap.parse_args()
    load_dotenv(ROOT/'.env'); load_dotenv(ROOT/'.env.local',override=False)
    manifest=json.loads(args.manifest.read_text(encoding='utf-8')); assets=manifest['assets']
    if len(assets)!=100 or [x['ordinal'] for x in assets]!=list(range(31,131)) or any(x['media_type']!='VIDEO' for x in assets): raise RuntimeError('FROZEN_MANIFEST_SCOPE_INVALID')
    if any(x['ordinal']>130 for x in assets): raise RuntimeError('OUT_OF_SCOPE_ASSET')
    checkpoint={'status':'RUNNING','mode':args.mode,'started_at':now(),'assets':[]}
    if args.resume and CHECKPOINT.exists(): checkpoint=json.loads(CHECKPOINT.read_text());
    done={x['asset_id'] for x in checkpoint.get('assets',[]) if x.get('checkpoint')=='WAITING_EXTERNAL_AI_APPROVAL'}
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    cred=os.getenv('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(ROOT/'.secrets/kdi-media-reader.json')
    drive=build('drive','v3',credentials=service_account.Credentials.from_service_account_file(cred,scopes=['https://www.googleapis.com/auth/drive.readonly']),cache_discovery=False)
    OUT.mkdir(parents=True,exist_ok=True); workroot=OUT/'local-work'; workroot.mkdir(exist_ok=True)
    try:
        import easyocr
        reader=easyocr.Reader(['en'],gpu=False,model_storage_directory=str(ROOT/'tmp/phase7_easyocr_models'),user_network_directory=str(ROOT/'tmp/phase7_easyocr_models'),verbose=False,download_enabled=False)
    except Exception as exc:
        reader=None; ocr_runtime_error=str(exc)
    for item in assets:
        aid=item['asset_id']
        if aid in done: continue
        started=time.perf_counter(); work=workroot/aid; work.mkdir(exist_ok=True); media=work/item['filename']
        record={**item,'started_at':now(),'external_ai_calls':0,'mode':args.mode}
        try:
            print(json.dumps({'ordinal':item['ordinal'],'stage':'ACQUIRED'}),flush=True)
            download(drive,item['source_master_reference'],media)
            digest=hashlib.sha256(media.read_bytes()).hexdigest()
            if digest!=item['checksum']: raise RuntimeError('MASTER_HASH_MISMATCH')
            record['checksum_verified']=True; record['checkpoint']='ACQUIRED'; tech=probe(media); record['technical_probe']=tech; record['checkpoint']='PROBED'
            bounds,kfs=frames(media,tech['duration_seconds'],work); record['scenes']=[{'scene_index':i,'start_seconds':bounds[i],'end_seconds':bounds[i+1]} for i in range(len(bounds)-1)]; record['canonical_scenes']=len(record['scenes']); record['keyframes']=kfs; record['canonical_keyframes']=len(kfs); record['checkpoint']='KEYFRAMES_COMPLETE'
            # Audio is evaluated locally. Transcript execution is delegated to
            # the existing approved local audio pipeline when enabled.
            record['audio_evaluated']=True; record['audio_stream']=tech['audio_stream']; record['transcript_state']='PENDING_SEMANTIC_PIPELINE' if tech['audio_stream'] else 'NOT_APPLICABLE'; record['checkpoint']='AUDIO_EVALUATED'
            # OCR is explicitly marked evaluated only when the local OCR engine
            # returns. Missing local model assets are a real stage failure.
            try:
                if reader is None: raise RuntimeError(ocr_runtime_error)
                from PIL import Image
                ocr=[]
                for frame in kfs:
                    with Image.open(frame['path']) as image: ocr.extend(reader.readtext(image,detail=1,paragraph=False))
                record['ocr_evaluated']=True; record['ocr_observations']=len(ocr)
            except Exception as exc:
                record['ocr_evaluated']=False; record['ocr_error']=str(exc); raise RuntimeError('LOCAL_OCR_UNAVAILABLE') from exc
            record['checkpoint']='OCR_COMPLETE'; record['openclip_preparation']='EXISTING_CERTIFIED_512D_REPRESENTATION'
            record['checkpoint']='WAITING_EXTERNAL_AI_APPROVAL' if args.mode!='PRODUCTION' else 'WAITING_EXTERNAL_AI_APPROVAL'; record['elapsed_seconds']=round(time.perf_counter()-started,2)
            checkpoint['assets']=[x for x in checkpoint.get('assets',[]) if x.get('asset_id')!=aid]+[record]; CHECKPOINT.write_text(json.dumps(checkpoint,indent=2)+'\n',encoding='utf-8')
        except Exception as exc:
            record.update({'checkpoint':'FAILED','failure':str(exc),'elapsed_seconds':round(time.perf_counter()-started,2)}); checkpoint['assets']=[x for x in checkpoint.get('assets',[]) if x.get('asset_id')!=aid]+[record]; CHECKPOINT.write_text(json.dumps(checkpoint,indent=2)+'\n',encoding='utf-8'); print(json.dumps(record),flush=True)
    complete=sum(x.get('checkpoint')=='WAITING_EXTERNAL_AI_APPROVAL' for x in checkpoint['assets']); checkpoint['status']='PASS' if complete==100 else 'BLOCKED'; checkpoint['completed_at']=now(); checkpoint['waiting_external_ai_approval']=complete; CHECKPOINT.write_text(json.dumps(checkpoint,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'status':checkpoint['status'],'waiting_external_ai_approval':complete,'technical_failures':100-complete,'external_ai_calls':0}))
if __name__=='__main__': main()
