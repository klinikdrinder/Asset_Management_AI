import os, json, hashlib, tempfile, subprocess
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
A='a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd'; R=Path(__file__).resolve().parents[1]
e={}
for f in (R/'.env',R/'.env.local'):
    if f.exists(): e.update({k:v for k,v in dotenv_values(f).items() if v})
e.update(os.environ)
c=create_client(e['SUPABASE_URL'],e['SUPABASE_SERVICE_ROLE_KEY'])
asset=c.table('assets').select('id,file_name,content_hash,checksum_sha256').eq('id',A).single().execute().data
d=c.table('asset_destinations').select('*').eq('asset_id',A).eq('upload_status','VERIFIED').limit(1).execute().data[0]
td=Path(tempfile.mkdtemp(prefix='kdi-phase8-review-')); media=td/'canary.mp4'; frame=td/'keyframe.jpg'
cp=e.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH') or str(R/'.secrets/kdi-media-reader.json')
svc=build('drive','v3',credentials=service_account.Credentials.from_service_account_file(cp,scopes=['https://www.googleapis.com/auth/drive.readonly']),cache_discovery=False)
with media.open('wb') as f:
    dl=MediaIoBaseDownload(f,svc.files().get_media(fileId=d['destination_google_file_id'],supportsAllDrives=True),chunksize=8*1024*1024); done=False
    while not done: _,done=dl.next_chunk(num_retries=3)
digest=hashlib.sha256(media.read_bytes()).hexdigest(); ff=R/'.tools/ffmpeg/bin/ffmpeg.exe'; fp=R/'.tools/ffmpeg/bin/ffprobe.exe'
probe=json.loads(subprocess.run([str(fp),'-v','error','-show_entries','format=duration:stream=codec_name,width,height,r_frame_rate,codec_type','-of','json',str(media)],capture_output=True,text=True,check=True).stdout)
subprocess.run([str(ff),'-ss','0','-i',str(media),'-frames:v','1','-q:v','2','-y',str(frame)],capture_output=True,check=True)
print(json.dumps({'temp_dir':str(td),'frame':str(frame),'asset':asset,'sha256':digest,'probe':probe,'destination_id':d.get('destination_google_file_id')},indent=2))
