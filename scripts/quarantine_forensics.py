"""Forensic re-probe of the quarantined set - serial, with exponential backoff
so Drive throttling can't masquerade as damage.

Per asset: download the SOURCE original (source_files.google_file_id) with retry;
record actual bytes, magic-byte format, native (pillow-heif primary) decode, and
Drive-thumbnail fallback. If the source cannot be decoded, try the MASTER copy
(asset_destinations.destination_google_file_id). Bucket each file:
  recoverable_locally      - source decodes (native or thumbnail)
  recoverable_by_recopy    - source broken but master copy decodes
  permanently_unprocessable- no copy decodes (reason recorded)

Originals are never modified. Writes buckets/flags to asset_media_probe and a
full per-asset record to reports/ai-search-v3/quarantine_forensics.json.
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


def retry(fn, attempts=6):
    for i in range(attempts):
        try:
            return fn()
        except TRANSIENT:
            if i == attempts - 1:
                raise
            time.sleep(min(30, 2 ** i) + 0.5)


def download_bytes(file_id):
    def _dl():
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, DRIVE.files().get_media(fileId=file_id, supportsAllDrives=True), chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue()
    return retry(_dl)


def source_and_master(asset_id):
    src = None
    rows = DB.table("asset_sources").select("source_file_id,is_first_discovered_source").eq("asset_id", asset_id).execute().data or []
    rows.sort(key=lambda r: 0 if r.get("is_first_discovered_source") else 1)
    for r in rows:
        sf = DB.table("source_files").select("google_file_id,is_folder").eq("id", r["source_file_id"]).single().execute().data
        if sf and sf.get("google_file_id") and not sf.get("is_folder"):
            src = sf["google_file_id"]; break
    d = DB.table("asset_destinations").select("destination_google_file_id").eq("asset_id", asset_id).limit(1).execute().data
    master = d[0]["destination_google_file_id"] if d else None
    return src, master


def video_frames(asset_id, raw):
    dest = WORK / f"{asset_id}.q.mp4"; dest.write_bytes(raw)
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
            o = WORK / f"{asset_id}_qf{i}.jpg"
            subprocess.run([FF, "-nostdin", "-ss", f"{max(0.0, dur*fr):.3f}", "-i", str(dest),
                            "-frames:v", "1", "-q:v", "5", str(o), "-y"], capture_output=True)
            if o.exists() and o.stat().st_size > 0:
                n += 1; o.unlink()
        return n
    finally:
        dest.unlink(missing_ok=True)


def decodes(raw):
    try:
        decode_primary_rgb(raw).convert("RGB").load()
        return True
    except Exception:
        return False


def main():
    q = DB.table("asset_media_probe").select("asset_id,media,source_folder,file_size_bytes").eq("status", "QUARANTINE").execute().data or []
    print(f"forensics on {len(q)} quarantined assets (serial, backoff)", flush=True)
    records = []
    for i, r in enumerate(q):
        aid, media = r["asset_id"], r["media"]
        db_size = r.get("file_size_bytes")
        rec = {"asset_id": aid, "media": media, "source_folder": r.get("source_folder"), "db_size": db_size,
               "actual_bytes": None, "detected_format": None, "native_ok": False, "thumbnail_ok": False,
               "source_ok": False, "master_ok": False, "bucket": None, "reason": None}
        try:
            src, master = source_and_master(aid)
            rec["has_master"] = bool(master)
            if not src:
                rec.update(bucket="permanently_unprocessable", reason="no_source_drive_id")
            else:
                raw = download_bytes(src)
                rec["actual_bytes"] = len(raw)
                rec["detected_format"] = detect_format(raw[:32]) if raw else "empty"
                if media == "video":
                    n = video_frames(aid, raw)
                    rec["source_ok"] = n > 0; rec["frames"] = n
                    rec["native_ok"] = n > 0
                else:
                    res = get_display_jpeg(raw, drive=DRIVE, creds=CREDS, file_id=src)
                    rec["native_ok"] = res["decode_source"] == "native" and res["jpeg"] is not None
                    rec["thumbnail_ok"] = res["decode_source"] == "drive_thumbnail" and res["jpeg"] is not None
                    rec["source_ok"] = res["jpeg"] is not None
                    if not rec["source_ok"]:
                        rec["reason"] = res["reason"]
                if rec["source_ok"]:
                    rec["bucket"] = "recoverable_locally"
                else:
                    # source unreadable/undecodable -> try the migrated master copy
                    if master:
                        try:
                            mraw = download_bytes(master)
                            rec["master_ok"] = decodes(mraw) if media == "image" else (video_frames(aid, mraw) > 0)
                        except Exception as mex:  # noqa
                            rec["reason"] = (rec["reason"] or "") + f"; master:{type(mex).__name__}"
                    if rec["master_ok"]:
                        rec["bucket"] = "recoverable_by_recopy"
                    else:
                        if rec["actual_bytes"] == 0:
                            rec["reason"] = "zero_length_source"
                        elif db_size and rec["actual_bytes"] and rec["actual_bytes"] < db_size:
                            rec["reason"] = f"truncated_source:{rec['actual_bytes']}/{db_size}"
                        rec["bucket"] = "permanently_unprocessable"
            # write back to probe
            upd = {"asset_id": aid, "actual_bytes": rec["actual_bytes"], "detected_format": rec["detected_format"],
                   "source_ok": rec["source_ok"], "master_ok": rec["master_ok"], "bucket": rec["bucket"]}
            if rec["source_ok"]:
                upd.update(status="DECODABLE", decode_source=("drive_thumbnail" if rec["thumbnail_ok"] else "native"),
                           reason=("recovered_drive_thumbnail" if rec["thumbnail_ok"] else None),
                           frames_extracted=rec.get("frames", 1))
            else:
                upd.update(status="QUARANTINE", decode_source="failed", reason=rec["reason"], frames_extracted=0)
            DB.table("asset_media_probe").upsert(upd, on_conflict="asset_id").execute()
            print(f"[{i+1}/{len(q)}] {aid} {media} {rec['detected_format']} -> {rec['bucket']} "
                  f"(src={rec['source_ok']} thumb={rec['thumbnail_ok']} master={rec['master_ok']})", flush=True)
        except Exception as ex:  # noqa
            rec.update(bucket="permanently_unprocessable", reason=f"persistent:{type(ex).__name__}")
            DB.table("asset_media_probe").upsert(
                {"asset_id": aid, "status": "QUARANTINE", "decode_source": "failed",
                 "reason": rec["reason"], "bucket": rec["bucket"], "actual_bytes": rec["actual_bytes"]},
                on_conflict="asset_id").execute()
            print(f"[{i+1}/{len(q)}] {aid} PERSISTENT {rec['reason']}", flush=True)
        records.append(rec)
        time.sleep(0.3)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "quarantine_forensics.json").write_text(json.dumps(records, indent=2, default=str) + "\n", encoding="utf-8")
    from collections import Counter
    print("BUCKETS:", dict(Counter(r["bucket"] for r in records)), flush=True)
    print("forensics complete", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
