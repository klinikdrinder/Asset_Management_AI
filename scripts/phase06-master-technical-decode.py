"""Read-only technical probe of verified Master copies."""
import os, json, hashlib, shutil, subprocess, tempfile
from pathlib import Path
from dotenv import dotenv_values
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image
from supabase import create_client

R=Path(__file__).resolve().parents[1]; O=R/'reports/semantic-search/rollout/phase-06'; M=json.loads((R/'reports/semantic-search/rollout/phase-05/phase_05_selected_20_manifest.json').read_text())
e={}; e.update({k:v for f in (R/'.env',R/'.env.local') for k,v in dotenv_values(f).items() if v}); e.update(os.environ)
db=create_client(e['SUPABASE_URL'],e['SUPABASE_SERVICE_ROLE_KEY']); cp=e.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(R/'.secrets/kdi-media-reader.json'); ds=build('drive','v3',credentials=service_account.Credentials.from_service_account_file(cp,scopes=['https://www.googleapis.com/auth/drive.readonly']),cache_discovery=False)
ff=R/'.tools/ffmpeg/bin/ffmpeg.exe'; fp=R/'.tools/ffmpeg/bin/ffprobe.exe'; rs=[]
for a in M['assets']:
    aid=a['asset_id']; row=db.table('assets').select('id,file_name,mime_type,content_hash').eq('id',aid).single().execute().data; d=db.table('asset_destinations').select('destination_google_file_id').eq('asset_id',aid).eq('upload_status','VERIFIED').limit(1).execute().data[0]; t=Path(tempfile.mkdtemp(prefix='kdi6-')); p=t/a['filename']; item={'asset_id':aid,'filename':a['filename']}
    try:
        with p.open('wb') as f:
            x=MediaIoBaseDownload(f,ds.files().get_media(fileId=d['destination_google_file_id'],supportsAllDrives=True),chunksize=8*1024*1024); done=False
            while not done: _,done=x.next_chunk(num_retries=3)
        item.update({'retrieval':'PASS','hash_match':hashlib.sha256(p.read_bytes()).hexdigest()==row.get('content_hash')})
        if str(row.get('mime_type','')).startswith('image/'):
            with Image.open(p) as im: im.verify(); item.update({'decode':'PASS','dimensions':list(im.size),'preprocess':'PASS'})
        else:
            q=subprocess.run([str(fp),'-v','error','-show_entries','format=duration:stream=codec_name,width,height,r_frame_rate,codec_type','-of','json',str(p)],capture_output=True,text=True,timeout=120,check=True); j=json.loads(q.stdout); v=next(s for s in j['streams'] if s.get('codec_type')=='video'); sm=t/'sample.jpg'; z=subprocess.run([str(ff),'-ss','0','-i',str(p),'-frames:v','1','-y',str(sm)],capture_output=True,timeout=120); item.update({'decode':'PASS' if z.returncode==0 and sm.exists() else 'FAIL','duration':j.get('format',{}).get('duration'),'codec':v.get('codec_name'),'resolution':[v.get('width'),v.get('height')],'frame_rate':v.get('r_frame_rate'),'audio_present':any(s.get('codec_type')=='audio' for s in j['streams']),'preprocess':'PASS' if z.returncode==0 else 'FAIL'})
    except Exception as ex: item.update({'retrieval':'FAIL','error_type':type(ex).__name__,'error':str(ex)[:160]})
    rs.append(item); shutil.rmtree(t,ignore_errors=True)
o={'selected':len(rs),'retrieved':sum(x.get('retrieval')=='PASS' for x in rs),'hash_match':sum(x.get('hash_match') is True for x in rs),'decoded':sum(x.get('decode')=='PASS' for x in rs),'semantic_analysis':0,'external_calls':0,'results':rs}; (O/'phase_06_selected_20_full_decode.json').write_text(json.dumps(o,indent=2)+'\n'); print(json.dumps({k:o[k] for k in ('selected','retrieved','hash_match','decoded','semantic_analysis')}))
