"""Clean, rate-limited re-probe of ONLY the quarantined assets.

The bulk probe hit Google Drive rate limits (HttpError / RemoteProtocolError)
because it pulled ~1200 files with 4 workers and no backoff, so its quarantine
set is contaminated by transient download failures - not decode failures. This
pass re-checks just those assets SERIALLY with exponential backoff, so a failure
here is a real decode/render failure, letting us distinguish a decode gap from a
genuinely damaged original.

Tiers (images): native (pillow-heif primary) -> Drive rendered thumbnail; format
by magic bytes. Videos: frame extraction. Originals never modified.
"""
from __future__ import annotations

import os, subprocess, time
from pathlib import Path

import httpx
from dotenv import dotenv_values
from supabase import create_client
import imageio_ffmpeg
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))
from kdi_media.image_access import get_display_jpeg, detect_format  # noqa

WORK = ROOT / "tmp" / "probe"; WORK.mkdir(parents=True, exist_ok=True)
FF = imageio_ffmpeg.get_ffmpeg_exe()
FRACS = (0.05, 0.2, 0.4, 0.6, 0.8, 0.95)
TRANSIENT = (HttpError, httpx.RemoteProtocolError, httpx.TransportError, ConnectionError)


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
DRIVE = gbuild("drive", "v3", credentials=CREDS, cache_discovery=False)


def retry(fn, what, attempts=6):
    for i in range(attempts):
        try:
            return fn()
        except TRANSIENT as ex:
            if i == attempts - 1:
                raise
            time.sleep(min(30, 2 ** i) + 0.5)
    raise RuntimeError(f"unreachable:{what}")


def drive_file_id(asset_id):
    rows = DB.table("asset_sources").select("source_file_id,is_first_discovered_source").eq("asset_id", asset_id).execute().data or []
    rows.sort(key=lambda r: 0 if r.get("is_first_discovered_source") else 1)
    for r in rows:
        sf = DB.table("source_files").select("google_file_id,is_folder").eq("id", r["source_file_id"]).single().execute().data
        if sf and sf.get("google_file_id") and not sf.get("is_folder"):
            return sf["google_file_id"]
    return None


def download(file_id, dest):
    def _dl():
        req = DRIVE.files().get_media(fileId=file_id, supportsAllDrives=True)
        with open(dest, "wb") as fh:
            dl = MediaIoBaseDownload(fh, req, chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()
    retry(_dl, "download")


def video_frames(asset_id, path):
    p = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True)
    dur = 5.0
    for line in p.stderr.splitlines():
        if "Duration:" in line:
            try:
                h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
                dur = int(h) * 3600 + int(m) * 60 + float(s)
            except ValueError:
                pass
            break
    n = 0
    for i, fr in enumerate(FRACS):
        out = WORK / f"{asset_id}_f{i}.jpg"
        subprocess.run([FF, "-nostdin", "-ss", f"{max(0.0, dur*fr):.3f}", "-i", str(path),
                        "-frames:v", "1", "-q:v", "5", str(out), "-y"], capture_output=True)
        if out.exists() and out.stat().st_size > 0:
            n += 1; out.unlink()
    return n


def main():
    q = DB.table("asset_media_probe").select("asset_id,media,source_folder").eq("status", "QUARANTINE").execute().data or []
    print(f"re-probing {len(q)} quarantined assets (serial, backoff)", flush=True)
    for i, r in enumerate(q):
        aid, media = r["asset_id"], r["media"]
        row = {"asset_id": aid, "media": media, "source_folder": r.get("source_folder")}
        dest = WORK / f"{aid}.q"
        try:
            fid = retry(lambda: drive_file_id(aid), "fileid")
            if not fid:
                row.update(status="QUARANTINE", reason="no_drive_id", decode_source="failed", frames_extracted=0)
                DB.table("asset_media_probe").upsert(row, on_conflict="asset_id").execute(); continue
            download(fid, dest)
            raw = dest.read_bytes()
            if media == "image":
                res = retry(lambda: get_display_jpeg(raw, drive=DRIVE, creds=CREDS, file_id=fid), "decode")
                row["detected_format"] = res["detected_format"]; row["decode_source"] = res["decode_source"]
                if res["jpeg"] is not None:
                    row.update(status="DECODABLE", frames_extracted=1,
                               reason=None if res["decode_source"] == "native" else "recovered_drive_thumbnail")
                else:
                    row.update(status="QUARANTINE", frames_extracted=0, reason=res["reason"])
            else:
                row["detected_format"] = detect_format(raw[:32])
                n = video_frames(aid, dest)
                row.update(status="DECODABLE" if n else "QUARANTINE", frames_extracted=n,
                           decode_source="native" if n else "failed",
                           reason=None if n >= 6 else ("under_6_frames" if n else "zero_frames"))
            DB.table("asset_media_probe").upsert(row, on_conflict="asset_id").execute()
            print(f"[{i+1}/{len(q)}] {aid} {media} -> {row['status']} {row.get('decode_source')} {row.get('reason') or ''}", flush=True)
        except Exception as ex:  # noqa
            row.update(status="QUARANTINE", reason=f"persistent:{type(ex).__name__}", decode_source="failed", frames_extracted=0)
            DB.table("asset_media_probe").upsert(row, on_conflict="asset_id").execute()
            print(f"[{i+1}/{len(q)}] {aid} {media} -> PERSISTENT FAIL {type(ex).__name__}", flush=True)
        finally:
            try:
                if dest.exists(): dest.unlink()
            except OSError:
                pass
        time.sleep(0.3)  # gentle pacing
    print("quarantine re-probe complete", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
