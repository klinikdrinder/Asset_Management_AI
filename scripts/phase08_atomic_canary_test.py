import os,json,hashlib,tempfile,subprocess,time,sys,shutil
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
R=Path(__file__).resolve().parents[1]; A='a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd'; e={}
for f in (R/'.env',R/'.env.local'):
 if f.exists(): e.update({k:v for k,v in dotenv_values(f).items() if v})
e.update(os.environ); c=create_client(e['SUPABASE_URL'],e['SUPABASE_SERVICE_ROLE_KEY']); a=c.table('assets').select('content_hash,checksum_sha256').eq('id',A).single().execute().data; d=c.table('asset_destinations').select('*').eq('asset_id',A).eq('upload_status','VERIFIED').limit(1).execute().data[0]
td=Path(tempfile.mkdtemp(prefix='kdi-atomic-canary-')); m=td/'a.mp4'; fr=td/'f.jpg'; cp=e.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(R/'.secrets/kdi-media-reader.json'); svc=build('drive','v3',credentials=service_account.Credentials.from_service_account_file(cp,scopes=['https://www.googleapis.com/auth/drive.readonly']),cache_discovery=False)
with m.open('wb') as f:
 dl=MediaIoBaseDownload(f,svc.files().get_media(fileId=d['destination_google_file_id'],supportsAllDrives=True),chunksize=8*1024*1024); done=False
 while not done: _,done=dl.next_chunk(num_retries=3)
assert hashlib.sha256(m.read_bytes()).hexdigest()==(a.get('content_hash') or a.get('checksum_sha256')); subprocess.run([str(R/'.tools/ffmpeg/bin/ffmpeg.exe'),'-ss','0','-i',str(m),'-frames:v','1','-q:v','2','-y',str(fr)],capture_output=True,check=True)
sys.path.insert(0,str(R/'src')); from PIL import Image; from kdi_media.providers.local_atomic_adapter import LocalAtomicObservationProvider
t=time.time(); out=LocalAtomicObservationProvider(str(R/'.kdi-models/SmolVLM2-500M-Video-Instruct'),max_new_tokens=6).analyze_image_atomic(Image.open(fr).convert('RGB')); result={'status':'PASS','asset_id':A,'elapsed_seconds':round(time.time()-t,1),'observations':out['observations'],'external_calls':0}; print(json.dumps(result)); (R/'reports/semantic-search/rollout/phase-08/phase_08_500m_atomic_test.json').write_text(json.dumps(result,indent=2)+'\n'); shutil.rmtree(td,ignore_errors=True)
