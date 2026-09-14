"""Forensics v2 for the quarantined set - fixes v1's two bugs:
  * 404/403 are PERMANENT (dead/inaccessible Drive id) - not retried as transient
  * a failed SOURCE download now falls through to the MASTER copy
    (asset_destinations.destination_google_file_id) before giving up

Buckets each quarantined asset:
  recoverable_locally       - SOURCE decodes (native / thumbnail / frames)
  recoverable_by_recopy     - source dead/undecodable but MASTER copy decodes
  permanently_unprocessable - no copy usable (reason: source+master status)

Serial + backoff on transient only. Originals never modified.
"""
from __future__ import annotations

import io, json, os, subprocess, time
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
from kdi_media.image_access import get_display_jpeg, detect_format, decode_primary_rgb  # noqa

WORK = ROOT / "tmp" / "probe"; WORK.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "reports" / "ai-search-v3"
FF = imageio_ffmpeg.get_ffmpeg_exe()
FRACS = (0.05, 0.2, 0.4, 0.6, 0.8, 0.95)
TRANSIENT = (httpx.RemoteProtocolError, httpx.TransportError, ConnectionError)


class PermanentDL(Exception):
    pass


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


def download_bytes(file_id):
    for i in range(6):
        try:
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, DRIVE.files().get_media(fileId=file_id, supportsAllDrives=True), chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()
            return buf.getvalue()
        except HttpError as ex:
            st = getattr(ex.resp, "status", None)
            if st in (403, 404, 410):
                raise PermanentDL(f"http_{st}")
            if i == 5:
                raise PermanentDL(f"http_{st}_exhausted")
            time.sleep(min(30, 2 ** i) + 0.5)
        except TRANSIENT:
            if i == 5:
                raise PermanentDL("transient_exhausted")
            time.sleep(min(30, 2 ** i) + 0.5)


def ids(asset_id):
    src = None
    rows = DB.table("asset_sources").select("source_file_id,is_first_discovered_source").eq("asset_id", asset_id).execute().data or []
    rows.sort(key=lambda r: 0 if r.get("is_first_discovered_source") else 1)
    for r in rows:
        sf = DB.table("source_files").select("google_file_id,is_folder").eq("id", r["source_file_id"]).single().execute().data
        if sf and sf.get("google_file_id") and not sf.get("is_folder"):
            src = sf["google_file_id"]; break
    d = DB.table("asset_destinations").select("destination_google_file_id").eq("asset_id", asset_id).limit(1).execute().data
    return src, (d[0]["destination_google_file_id"] if d else None)


def video_frames(asset_id, raw):
    dest = WORK / f"{asset_id}.q2.mp4"; dest.write_bytes(raw)
    try:
        p = subprocess.run([FF, "-i", str(dest)], capture_output=True, text=True)
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
            o = WORK / f"{asset_id}_q2f{i}.jpg"
            subprocess.run([FF, "-nostdin", "-ss", f"{max(0.0, dur*fr):.3f}", "-i", str(dest),
                            "-frames:v", "1", "-q:v", "5", str(o), "-y"], capture_output=True)
            if o.exists() and o.stat().st_size > 0:
                n += 1; o.unlink()
        return n
    finally:
        dest.unlink(missing_ok=True)


def decode_ok(media, asset_id, raw, src_gid=None):
    """Returns (ok, thumbnail_used, detected_format)."""
    fmt = detect_format(raw[:32]) if raw else "empty"
    if media == "video":
        return (video_frames(asset_id, raw) > 0, False, fmt)
    res = get_display_jpeg(raw, drive=DRIVE, creds=CREDS, file_id=src_gid)
    return (res["jpeg"] is not None, res["decode_source"] == "drive_thumbnail", res["detected_format"])


def main():
    q = DB.table("asset_media_probe").select("asset_id,media,source_folder,file_size_bytes").eq("status", "QUARANTINE").execute().data or []
    print(f"forensics v2 on {len(q)} quarantined (serial, permanent-aware, master fallback)", flush=True)
    records = []
    for i, r in enumerate(q):
        aid, media = r["asset_id"], r["media"]
        rec = {"asset_id": aid, "media": media, "source_folder": r.get("source_folder"), "db_size": r.get("file_size_bytes"),
               "source_status": None, "master_status": None, "actual_bytes": None, "detected_format": None,
               "source_ok": False, "master_ok": False, "thumbnail_used": False, "bucket": None, "reason": None}
        try:
            src, master = ids(aid)
            rec["has_master"] = bool(master)
            # SOURCE
            if not src:
                rec["source_status"] = "no_source_id"
            else:
                try:
                    raw = download_bytes(src)
                    rec["actual_bytes"] = len(raw)
                    ok, thumb, fmt = decode_ok(media, aid, raw, src_gid=src)
                    rec["detected_format"] = fmt; rec["source_ok"] = ok; rec["thumbnail_used"] = thumb
                    rec["source_status"] = "ok" if ok else "downloaded_undecodable"
                except PermanentDL as ex:
                    rec["source_status"] = str(ex)
            # MASTER (only if source unusable)
            if not rec["source_ok"]:
                if master:
                    try:
                        mraw = download_bytes(master)
                        mok, _, mfmt = decode_ok(media, aid, mraw, src_gid=master)
                        rec["master_ok"] = mok
                        rec["master_status"] = "ok" if mok else "downloaded_undecodable"
                        if not rec["detected_format"]:
                            rec["detected_format"] = mfmt
                    except PermanentDL as ex:
                        rec["master_status"] = str(ex)
                else:
                    rec["master_status"] = "no_master_id"
            # BUCKET
            if rec["source_ok"]:
                rec["bucket"] = "recoverable_locally"
            elif rec["master_ok"]:
                rec["bucket"] = "recoverable_by_recopy"
            else:
                rec["bucket"] = "permanently_unprocessable"
                rec["reason"] = f"source:{rec['source_status']};master:{rec['master_status']}"
            # write back
            upd = {"asset_id": aid, "actual_bytes": rec["actual_bytes"], "detected_format": rec["detected_format"],
                   "source_ok": rec["source_ok"], "master_ok": rec["master_ok"], "bucket": rec["bucket"]}
            if rec["source_ok"]:
                upd.update(status="DECODABLE", decode_source=("drive_thumbnail" if rec["thumbnail_used"] else "native"),
                           reason=("recovered_drive_thumbnail" if rec["thumbnail_used"] else None), frames_extracted=1)
            else:
                upd.update(status="QUARANTINE", decode_source="failed", reason=rec["reason"], frames_extracted=0)
            DB.table("asset_media_probe").upsert(upd, on_conflict="asset_id").execute()
            print(f"[{i+1}/{len(q)}] {aid} {media} {rec['detected_format']} -> {rec['bucket']} "
                  f"(src={rec['source_status']} master={rec['master_status']})", flush=True)
        except Exception as ex:  # noqa
            rec.update(bucket="permanently_unprocessable", reason=f"unexpected:{type(ex).__name__}")
            DB.table("asset_media_probe").upsert({"asset_id": aid, "status": "QUARANTINE", "bucket": rec["bucket"],
                "reason": rec["reason"], "decode_source": "failed"}, on_conflict="asset_id").execute()
            print(f"[{i+1}/{len(q)}] {aid} UNEXPECTED {type(ex).__name__}", flush=True)
        records.append(rec)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "quarantine_forensics.json").write_text(json.dumps(records, indent=2, default=str) + "\n", encoding="utf-8")
    from collections import Counter
    print("BUCKETS:", dict(Counter(r["bucket"] for r in records)), flush=True)
    print("forensics v2 complete", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
