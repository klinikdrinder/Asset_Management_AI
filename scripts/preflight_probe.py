"""Pre-flight media probe over all assets - costs no model calls.

For every asset: resolve its Drive file, download it, and
  * images: attempt a full decode (HEIC included, via pillow-heif)
  * videos: attempt to extract up to 6 evenly-spaced keyframes
Record DECODABLE / QUARANTINE + reason + frames_extracted into
public.asset_media_probe. Downloaded bytes are deleted immediately after
probing. Resumable (skips assets already probed). Progress is visible by
`select status,count(*) from asset_media_probe group by 1`.
"""
from __future__ import annotations

import os, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import dotenv_values
from PIL import Image
from pillow_heif import register_heif_opener
from supabase import create_client
import imageio_ffmpeg
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild
from googleapiclient.http import MediaIoBaseDownload

register_heif_opener()  # let PIL open HEIC/HEIF

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "tmp" / "probe"; WORK.mkdir(parents=True, exist_ok=True)
FF = imageio_ffmpeg.get_ffmpeg_exe()
FRACS = (0.05, 0.2, 0.4, 0.6, 0.8, 0.95)
_local = threading.local()
_db_lock = threading.Lock()


def env():
    e = {}
    for f in (ROOT / ".env", ROOT / ".env.local", ROOT / "dashboard/.env.local"):
        if f.exists():
            e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ)
    return e


E = env()
DB = create_client(E.get("SUPABASE_URL") or E["NEXT_PUBLIC_SUPABASE_URL"], E["SUPABASE_SERVICE_ROLE_KEY"])
CREDS = service_account.Credentials.from_service_account_file(
    E["GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH"],
    scopes=["https://www.googleapis.com/auth/drive.readonly"])


def drive():
    if not getattr(_local, "drive", None):
        _local.drive = gbuild("drive", "v3", credentials=CREDS, cache_discovery=False)
    return _local.drive


def folder_map():
    import json
    man = json.loads((ROOT / "reports/semantic-search/rollout/full/kdi_local_preparation_manifest_v1.json").read_text(encoding="utf-8"))
    out = {}
    def walk(o):
        if isinstance(o, dict):
            if o.get("source_folder") and o.get("asset_id"):
                out.setdefault(o["asset_id"], o["source_folder"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(man)
    return out


def drive_file_id(asset_id):
    rows = DB.table("asset_sources").select("source_file_id,is_first_discovered_source").eq("asset_id", asset_id).execute().data or []
    rows.sort(key=lambda r: 0 if r.get("is_first_discovered_source") else 1)
    for r in rows:
        sf = DB.table("source_files").select("google_file_id,is_folder").eq("id", r["source_file_id"]).single().execute().data
        if sf and sf.get("google_file_id") and not sf.get("is_folder"):
            return sf["google_file_id"]
    return None


def download(file_id, dest):
    req = drive().files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(dest, "wb") as fh:
        dl = MediaIoBaseDownload(fh, req, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = dl.next_chunk()


def video_duration(path):
    p = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True)
    for line in p.stderr.splitlines():
        if "Duration:" in line:
            hms = line.split("Duration:")[1].split(",")[0].strip()
            try:
                h, m, s = hms.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except ValueError:
                return 0.0
    return 0.0


def probe_video(asset_id, path):
    dur = video_duration(path) or 5.0
    n = 0
    for i, fr in enumerate(FRACS):
        out = WORK / f"{asset_id}_f{i}.jpg"
        subprocess.run([FF, "-nostdin", "-ss", f"{max(0.0, dur*fr):.3f}", "-i", str(path),
                        "-frames:v", "1", "-q:v", "5", str(out), "-y"], capture_output=True)
        if out.exists() and out.stat().st_size > 0:
            n += 1
            out.unlink()
    return n


def upsert(row):
    with _db_lock:
        DB.table("asset_media_probe").upsert(row, on_conflict="asset_id").execute()


def probe_asset(a, folders):
    aid = a["id"]
    media = "video" if str(a.get("mime_type", "")).startswith("video") else "image"
    row = {"asset_id": aid, "media": media, "source_folder": folders.get(aid),
           "file_size_bytes": a.get("file_size_bytes")}
    ext = ".mp4" if media == "video" else ".bin"
    dest = WORK / f"{aid}{ext}"
    try:
        fid = drive_file_id(aid)
        if not fid:
            row.update(status="QUARANTINE", reason="no_drive_id", frames_extracted=0)
            upsert(row); return
        download(fid, dest)
        if media == "image":
            try:
                with Image.open(dest) as im:
                    im.convert("RGB").load()
                row.update(status="DECODABLE", reason=None, frames_extracted=1)
            except Exception as ex:  # noqa
                row.update(status="QUARANTINE", reason=f"image_decode:{type(ex).__name__}", frames_extracted=0)
        else:
            n = probe_video(aid, dest)
            if n == 0:
                row.update(status="QUARANTINE", reason="zero_frames", frames_extracted=0)
            else:
                row.update(status="DECODABLE", reason=None if n >= 6 else "under_6_frames", frames_extracted=n)
        upsert(row)
    except Exception as ex:  # noqa
        row.update(status="QUARANTINE", reason=f"download_error:{type(ex).__name__}", frames_extracted=0)
        upsert(row)
    finally:
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass


def main():
    folders = folder_map()
    assets = []
    start = 0
    while True:
        rows = DB.table("assets").select("id,mime_type,file_extension,file_size_bytes").range(start, start + 999).execute().data or []
        assets += rows
        if len(rows) < 1000:
            break
        start += 1000
    done = {r["asset_id"] for r in (DB.table("asset_media_probe").select("asset_id").execute().data or [])}
    todo = [a for a in assets if a["id"] not in done]
    print(f"probe: {len(assets)} assets, {len(done)} already done, {len(todo)} to probe", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda a: probe_asset(a, folders), todo))
    print("probe complete", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
