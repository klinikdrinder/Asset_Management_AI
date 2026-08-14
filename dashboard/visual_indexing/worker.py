from __future__ import annotations
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
import argparse, gc, json, os, shutil, subprocess, sys, tempfile, time, uuid
from dotenv import dotenv_values
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from supabase import create_client
from .openclip_encoder import OpenClipEncoder, MODEL_PROVIDER, MODEL_NAME, MODEL_VERSION, DIMENSIONS

ROOT=Path(__file__).resolve().parents[1]; PROJECT=ROOT.parent
TEMP_ROOT=Path(tempfile.gettempdir())/"kdi_semantic_visual"
STATES=("QUEUED","PROCESSING","INDEXED","RETRY","FAILED","NOT_APPLICABLE")
def env():
    result={}
    for path in (PROJECT/".env",PROJECT/".env.local",ROOT/".env.local"): result.update({k:v for k,v in dotenv_values(path).items() if v})
    result.update(os.environ); return result
def clients():
    e=env(); url=e.get("NEXT_PUBLIC_SUPABASE_URL") or e.get("SUPABASE_URL"); key=e.get("SUPABASE_SERVICE_ROLE_KEY")
    cred=e.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH") or e.get("GOOGLE_APPLICATION_CREDENTIALS") or e.get("GOOGLE_CREDENTIALS_PATH")
    if not url or not key or not cred: raise RuntimeError("DATABASE_OR_DRIVE_CREDENTIALS_UNAVAILABLE")
    creds=service_account.Credentials.from_service_account_file(cred,scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return create_client(url,key),build("drive","v3",credentials=creds,cache_discovery=False)
def cleanup_stale(hours=24):
    TEMP_ROOT.mkdir(parents=True,exist_ok=True); cutoff=time.time()-hours*3600
    for p in TEMP_ROOT.iterdir():
        if p.is_dir() and p.stat().st_mtime<cutoff: shutil.rmtree(p,ignore_errors=True)
def download(drive,file_id,path):
    request=drive.files().get_media(fileId=file_id,supportsAllDrives=True)
    with path.open("wb") as out:
        transfer=MediaIoBaseDownload(out,request,chunksize=8*1024*1024); done=False
        while not done: _,done=transfer.next_chunk(num_retries=3)
def vector_for_video(encoder,source,workspace):
    probe=str(PROJECT/".tools"/"ffmpeg"/"bin"/"ffprobe.exe"); ffmpeg=str(PROJECT/".tools"/"ffmpeg"/"bin"/"ffmpeg.exe")
    result=subprocess.run([probe,"-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(source)],capture_output=True,text=True,timeout=60,check=True)
    duration=float(result.stdout.strip()); vectors=[]
    for index,fraction in enumerate((.15,.5,.85)):
        frame=workspace/f"frame-{index}.jpg"
        run=subprocess.run([ffmpeg,"-ss",f"{duration*fraction:.3f}","-i",str(source),"-frames:v","1","-vf","scale=1024:1024:force_original_aspect_ratio=decrease","-q:v","3","-y",str(frame)],capture_output=True,timeout=90)
        if run.returncode==0 and frame.exists():
            with suppress(Exception): vectors.append(encoder.embed_image(frame))
            frame.unlink(missing_ok=True)
    if not vectors: raise RuntimeError("FRAME_EXTRACTION_ERROR")
    return encoder.aggregate(vectors),len(vectors)
def classify(exc):
    text=str(exc).upper()
    for code in ("FRAME_EXTRACTION_ERROR","INVALID_VECTOR","FFPROBE_ERROR","DRIVE_ACCESS_ERROR","DOWNLOAD_ERROR","MODEL_ERROR","DATABASE_ERROR"):
        if code in text:return code
    if isinstance(exc,subprocess.SubprocessError): return "FFPROBE_ERROR"
    return "EMBEDDING_ERROR"
def asset_input(db,asset_id):
    a=db.table("assets").select("id,mime_type,file_extension").eq("id",asset_id).single().execute().data
    rows=db.table("asset_destinations").select("destination_google_file_id,upload_status").eq("asset_id",asset_id).eq("upload_status","VERIFIED").limit(1).execute().data
    if not rows or not rows[0].get("destination_google_file_id"): raise RuntimeError("DRIVE_ACCESS_ERROR")
    return a,rows[0]["destination_google_file_id"]
def run_one(db,drive,encoder,owner):
    rows=db.rpc("claim_visual_index_job",{"p_owner":owner,"p_lease_seconds":1800}).execute().data or []
    if not rows:return False
    job=rows[0]
    try:
        with tempfile.TemporaryDirectory(prefix=f"{job['id']}-",dir=TEMP_ROOT) as tmp:
            work=Path(tmp); asset,file_id=asset_input(db,job["asset_id"]); source=work/"source.media"; download(drive,file_id,source)
            if str(asset.get("mime_type") or "").startswith("image/"):
                vector=encoder.embed_image(source); frames=1; method="DRIVE_IMAGE"
            elif str(asset.get("mime_type") or "").startswith("video/"):
                vector,frames=vector_for_video(encoder,source,work);method="VIDEO_FRAMES"
            else: raise RuntimeError("NOT_APPLICABLE")
            db.rpc("complete_visual_index_job",{"p_job_id":job["id"],"p_owner":owner,"p_embedding":{"embedding":vector,"source_method":method,"frame_count":frames}}).execute()
    except Exception as exc:
        code=classify(exc); retry=code in {"DRIVE_ACCESS_ERROR","DOWNLOAD_ERROR","DATABASE_ERROR"}
        with suppress(Exception): db.rpc("fail_visual_index_job",{"p_job_id":job["id"],"p_owner":owner,"p_code":code,"p_detail":str(exc)[:1000],"p_retryable":retry}).execute()
    finally: gc.collect()
    return True
def counts(db):
    out={}
    for state in STATES: out[state]=db.table("asset_visual_index_jobs").select("id",count="exact").eq("status",state).limit(0).execute().count or 0
    return out
def show(db,completed=0):
    c=counts(db);eligible=c["QUEUED"]+c["PROCESSING"]+c["INDEXED"]+c["RETRY"]+c["FAILED"]
    print(f"KDI Visual Semantic Index\nEligible visual assets: {eligible}\nIndexed: {c['INDEXED']}\nCompleted this run: {completed}\nProcessing: {c['PROCESSING']}\nFailed: {c['FAILED']}\nRemaining: {c['QUEUED']+c['RETRY']+c['PROCESSING']}")
def main():
    parser=argparse.ArgumentParser();parser.add_argument("command",choices=("queue","one","run","status","retry","reconcile"));args=parser.parse_args()
    cleanup_stale();db,drive=clients()
    if args.command=="queue": print(db.rpc("queue_visual_index_jobs",{"p_provider":MODEL_PROVIDER,"p_model":MODEL_NAME,"p_version":MODEL_VERSION}).execute().data);return
    if args.command=="retry": db.table("asset_visual_index_jobs").update({"status":"RETRY","next_attempt_at":datetime.now(timezone.utc).isoformat()}).eq("status","FAILED").execute();return
    if args.command in ("status","reconcile"): show(db);return
    encoder=OpenClipEncoder();owner=f"{os.getpid()}-{uuid.uuid4()}";completed=0
    while run_one(db,drive,encoder,owner):
        completed+=1
        if args.command=="one" or completed%10==0: show(db,completed)
        if args.command=="one": break
    show(db,completed)
if __name__=="__main__": main()
