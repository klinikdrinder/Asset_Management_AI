"""Prepare controlled, temporary Job 6 visual QA derivatives.

This script is intentionally boundary-locked to the human-approved manifest.
It verifies the external-AI gate immediately before each Drive download, never
modifies originals, and emits only low-resolution JPEG contact sheets plus a
machine-readable probe report under tmp/job6.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from dotenv import dotenv_values
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp" / "job6"
MANIFEST = ROOT / "reports" / "ai-search-v3" / "job5_3-final-pilot-manifest.json"
PURPOSE = "KDI AI Search V3 pilot indexing only"


def environment() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / ".env.local"):
        values.update({k: v for k, v in dotenv_values(path).items() if v})
    values.update(os.environ)
    return values


def main() -> int:
    env = environment()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("purpose") != PURPOSE or manifest.get("pilot_size") != 10:
        raise RuntimeError("PILOT_MANIFEST_MISMATCH")
    assets = manifest.get("assets") or []
    if len(assets) != 10 or len({row["asset_id"] for row in assets}) != 10:
        raise RuntimeError("PILOT_BOUNDARY_MISMATCH")

    db = create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])
    cred_path = env.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH") or env.get("GOOGLE_APPLICATION_CREDENTIALS")
    if (not cred_path or not Path(cred_path).is_file()) and (ROOT / ".secrets" / "kdi-media-reader.json").is_file():
        cred_path = str(ROOT / ".secrets" / "kdi-media-reader.json")
    token_path = env.get("GOOGLE_DRIVE_TOKEN_FILE") or env.get("GOOGLE_TOKEN_PATH")
    if cred_path and Path(cred_path).is_file():
        credentials = service_account.Credentials.from_service_account_file(
            cred_path, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
    elif token_path and Path(token_path).is_file():
        credentials = Credentials.from_authorized_user_file(
            token_path, ["https://www.googleapis.com/auth/drive"]
        )
    else:
        raise RuntimeError("DRIVE_CREDENTIALS_UNAVAILABLE")
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    ffmpeg = ROOT / ".tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    ffprobe = ROOT / ".tools" / "ffmpeg" / "bin" / "ffprobe.exe"

    OUT.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, object]] = []
    for item in assets:
        asset_id, expected_name = item["asset_id"], item["file_name"]
        row = db.table("assets").select("id,file_name,mime_type,size_bytes,content_hash").eq("id", asset_id).single().execute().data
        if row.get("file_name") != expected_name:
            raise RuntimeError(f"UUID_FILENAME_MISMATCH:{asset_id}")
        allowed = db.rpc("can_asset_use_external_ai", {"p_asset_id": asset_id}).execute().data
        access = db.table("asset_access_control").select("external_ai_status,metadata").eq("asset_id", asset_id).single().execute().data
        authorization = (access.get("metadata") or {}).get("external_ai_authorization") or {}
        if allowed is not True or access.get("external_ai_status") != "ALLOWED" or authorization.get("purpose") != PURPOSE:
            raise RuntimeError(f"EXTERNAL_AI_GATE_DENIED:{asset_id}")
        destinations = db.table("asset_destinations").select("destination_google_file_id,upload_status,verification_level").eq("asset_id", asset_id).eq("upload_status", "VERIFIED").limit(1).execute().data
        if not destinations or not destinations[0].get("destination_google_file_id"):
            raise RuntimeError(f"VERIFIED_MASTER_UNAVAILABLE:{asset_id}")

        work = OUT / asset_id
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        source = work / ("source." + str(expected_name).rsplit(".", 1)[-1].lower())
        request = drive.files().get_media(fileId=destinations[0]["destination_google_file_id"], supportsAllDrives=True)
        with source.open("wb") as stream:
            transfer = MediaIoBaseDownload(stream, request, chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                _, done = transfer.next_chunk(num_retries=3)

        mime = str(row.get("mime_type") or "")
        duration: float | None = None
        frames: list[str] = []
        if mime.startswith("video/"):
            probe = subprocess.run([str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(source)], capture_output=True, text=True, check=True, timeout=60)
            duration = float(probe.stdout.strip())
            for index, fraction in enumerate((0.05, 0.2, 0.4, 0.6, 0.8, 0.95)):
                target = work / f"frame-{index + 1}.jpg"
                timestamp = max(0.0, min(duration - 0.01, duration * fraction))
                result = subprocess.run([str(ffmpeg), "-ss", f"{timestamp:.3f}", "-i", str(source), "-frames:v", "1", "-vf", "scale=640:640:force_original_aspect_ratio=decrease,pad=640:640:(ow-iw)/2:(oh-ih)/2", "-q:v", "3", "-y", str(target)], capture_output=True, timeout=90)
                if result.returncode == 0 and target.exists():
                    frames.append(str(target.relative_to(ROOT)))
            contact = work / "contact-sheet.jpg"
            result = subprocess.run([str(ffmpeg), "-i", str(work / "frame-%d.jpg"), "-vf", "tile=3x2", "-frames:v", "1", "-q:v", "3", "-y", str(contact)], capture_output=True, timeout=90)
            if result.returncode != 0 or not contact.exists():
                raise RuntimeError(f"CONTACT_SHEET_FAILED:{asset_id}")
        elif mime.startswith("image/"):
            contact = work / "contact-sheet.jpg"
            result = subprocess.run([str(ffmpeg), "-i", str(source), "-vf", "scale=1280:1280:force_original_aspect_ratio=decrease", "-frames:v", "1", "-q:v", "3", "-y", str(contact)], capture_output=True, timeout=90)
            if result.returncode != 0 or not contact.exists():
                raise RuntimeError(f"IMAGE_DERIVATIVE_FAILED:{asset_id}")
            frames.append(str(contact.relative_to(ROOT)))
        else:
            raise RuntimeError(f"UNSUPPORTED_MEDIA:{asset_id}")
        report.append({"asset_id": asset_id, "file_name": expected_name, "mime_type": mime, "size_bytes": row.get("size_bytes"), "duration_seconds": duration, "frames": frames, "contact_sheet": str(contact.relative_to(ROOT)), "authorization": "PASS"})

    (OUT / "prepared-media.json").write_text(json.dumps({"purpose": PURPOSE, "assets": report}, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "assets": len(report), "output": str(OUT / "prepared-media.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
