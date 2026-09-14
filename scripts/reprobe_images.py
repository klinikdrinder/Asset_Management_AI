"""Re-probe every image with the 3-tier decoder (image_access), recording the
magic-byte format and which tier decoded it. Updates asset_media_probe:
  decode_source in ('native','drive_thumbnail','failed'), detected_format, status.
Originals are never modified - decode is in-memory, temp copies deleted.
Videos are left as the base probe recorded them.
"""
from __future__ import annotations

import os, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import dotenv_values
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild
from googleapiclient.http import MediaIoBaseDownload

ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))
from kdi_media.image_access import get_display_jpeg  # noqa

WORK = ROOT / "tmp" / "probe"; WORK.mkdir(parents=True, exist_ok=True)
_local = threading.local(); _lock = threading.Lock()


def env():
    e = {}
    for f in (ROOT / ".env", ROOT / ".env.local", ROOT / "dashboard/.env.local"):
        if f.exists():
            e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ); return e


E = env()
DB = create_client(E.get("SUPABASE_URL") or E["NEXT_PUBLIC_SUPABASE_URL"], E["SUPABASE_SERVICE_ROLE_KEY"])
CREDS = service_account.Credentials.from_service_account_file(
    E["GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH"],
    scopes=["https://www.googleapis.com/auth/drive.readonly"])


def drive():
    if not getattr(_local, "d", None):
        _local.d = gbuild("drive", "v3", credentials=CREDS, cache_discovery=False)
    return _local.d


def folder_map():
    import json
    man = json.loads((ROOT / "reports/semantic-search/rollout/full/kdi_local_preparation_manifest_v1.json").read_text(encoding="utf-8"))
    out = {}
    def walk(o):
        if isinstance(o, dict):
            if o.get("source_folder") and o.get("asset_id"):
                out.setdefault(o["asset_id"], o["source_folder"])
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(man); return out


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


def upsert(row):
    with _lock:
        DB.table("asset_media_probe").upsert(row, on_conflict="asset_id").execute()


def handle(a, folders):
    aid = a["id"]
    row = {"asset_id": aid, "media": "image", "source_folder": folders.get(aid),
           "file_size_bytes": a.get("file_size_bytes")}
    dest = WORK / f"{aid}.img"
    try:
        fid = drive_file_id(aid)
        raw = None
        if fid:
            download(fid, dest)
            raw = dest.read_bytes()
        res = get_display_jpeg(raw, drive=drive(), creds=CREDS, file_id=fid)
        row["detected_format"] = res["detected_format"]
        row["decode_source"] = res["decode_source"]
        if res["jpeg"] is not None:
            row.update(status="DECODABLE", reason=None if res["decode_source"] == "native" else "recovered_drive_thumbnail",
                       frames_extracted=1)
        else:
            row.update(status="QUARANTINE", reason=res["reason"], frames_extracted=0)
        upsert(row)
    except Exception as ex:  # noqa
        row.update(status="QUARANTINE", reason=f"error:{type(ex).__name__}", decode_source="failed", frames_extracted=0)
        upsert(row)
    finally:
        try:
            if dest.exists(): dest.unlink()
        except OSError:
            pass


def main():
    folders = folder_map()
    imgs, start = [], 0
    while True:
        rows = DB.table("assets").select("id,mime_type,file_size_bytes").ilike("mime_type", "image/%").range(start, start + 999).execute().data or []
        imgs += rows
        if len(rows) < 1000: break
        start += 1000
    print(f"reprobe images: {len(imgs)}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda a: handle(a, folders), imgs))
    print("reprobe complete", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
