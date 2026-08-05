"""Create and manage the non-sensitive Step 14 live-test Drive fixture."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.http import MediaIoBaseUpload
from supabase import create_client

from kdi_media.google_drive import (
    create_destination_write_drive_service,
    create_readonly_drive_service,
    verify_folder_access,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tmp" / "step14-live-fixture.json"
FOLDER_NAME = "KDI Step 14 Controlled Sync Test"
FOLDER_ROLE = "step14_controlled_source"
UNIQUE_NAME = "step14-unique.png"
DUPLICATE_NAME = "step14-byte-identical-copy.png"
SKIP_NAME = "step14-unsupported.txt"
V1 = b"\x89PNG\r\n\x1a\nKDI_STEP14_NON_SENSITIVE_UNIQUE_V1\n"
V2 = b"\x89PNG\r\n\x1a\nKDI_STEP14_NON_SENSITIVE_CHANGED_V2\n"
SKIP = b"KDI Step 14 non-sensitive unsupported fixture.\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("setup", "add-unique", "add-duplicate", "change-unique", "add-skip", "add-retry", "disable"))
    parser.add_argument("--execute", action="store_true", required=True)
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    write_service = create_destination_write_drive_service()
    manifest = _read_manifest()
    if args.action == "setup":
        folder_id = _ensure_folder(write_service)
        verify_folder_access(create_readonly_drive_service(), folder_id)
        rows = client.table("source_folders").upsert({
            "source_name": FOLDER_NAME,
            "account_name": "kdimediaautomation@gmail.com",
            "folder_url": f"https://drive.google.com/drive/folders/{folder_id}",
            "google_folder_id": folder_id,
            "active": True,
            "access_status": "ACCESSIBLE",
            "permission_role": "OWNER",
            "notes": "Approved non-sensitive Step 14 controlled live-test source; disable after A-J.",
        }, on_conflict="google_folder_id").execute().data or []
        if len(rows) != 1:
            raise RuntimeError("Controlled source registration did not reconcile")
        manifest.update({"folder_id": folder_id, "source_folder_id": rows[0]["id"]})
    elif args.action == "disable":
        client.table("source_folders").update({"active": False}).eq("id", manifest["source_folder_id"]).execute()
        manifest["active"] = False
    else:
        folder_id = manifest["folder_id"]
        if args.action == "add-unique":
            manifest["unique"] = _ensure_file(write_service, folder_id, UNIQUE_NAME, "image/png", V1, "unique")
        elif args.action == "add-duplicate":
            manifest["duplicate"] = _ensure_file(write_service, folder_id, DUPLICATE_NAME, "image/png", V1, "duplicate")
        elif args.action == "change-unique":
            file_id = manifest["unique"]["file_id"]
            metadata = write_service.files().update(
                fileId=file_id,
                media_body=MediaIoBaseUpload(io.BytesIO(V2), mimetype="image/png", resumable=True),
                fields="id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink",
                supportsAllDrives=True,
            ).execute()
            manifest["unique"] = _safe_file(metadata, V2)
        elif args.action == "add-skip":
            manifest["skip"] = _ensure_file(write_service, folder_id, SKIP_NAME, "text/plain", SKIP, "skip")
        elif args.action == "add-retry":
            content = b"\x89PNG\r\n\x1a\nKDI_STEP14_NON_SENSITIVE_RETRY_FIXTURE\n"
            manifest["retry"] = _ensure_file(write_service, folder_id, "step14-retry.png", "image/png", content, "retry")
    manifest["active"] = args.action != "disable"
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _ensure_folder(service):
    response = service.files().list(
        q="trashed=false and mimeType='application/vnd.google-apps.folder' and appProperties has { key='kdi_fixture_role' and value='step14_controlled_source' }",
        spaces="drive", fields="files(id,name)", pageSize=2,
    ).execute()
    matches = response.get("files") or []
    if len(matches) > 1:
        raise RuntimeError("Duplicate controlled Step 14 folders exist")
    if matches:
        return matches[0]["id"]
    created = service.files().create(
        body={"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder", "appProperties": {"kdi_fixture_role": FOLDER_ROLE}},
        fields="id", supportsAllDrives=True,
    ).execute()
    return created["id"]


def _ensure_file(service, folder_id: str, name: str, mime: str, content: bytes, role: str):
    response = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false and appProperties has {{ key='kdi_fixture_item' and value='{role}' }}",
        spaces="drive", fields="files(id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink)", pageSize=2,
    ).execute()
    matches = response.get("files") or []
    if len(matches) > 1:
        raise RuntimeError("Duplicate controlled fixture identities exist")
    if matches:
        return _safe_file(matches[0], content)
    created = service.files().create(
        body={"name": name, "parents": [folder_id], "appProperties": {"kdi_fixture_item": role}},
        media_body=MediaIoBaseUpload(io.BytesIO(content), mimetype=mime, resumable=True),
        fields="id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink",
        supportsAllDrives=True,
    ).execute()
    return _safe_file(created, content)


def _safe_file(metadata, content: bytes):
    return {
        "file_id": metadata["id"], "file_name": metadata["name"],
        "mime_type": metadata["mimeType"], "size": int(metadata["size"]),
        "modified_time": metadata.get("modifiedTime"),
        "provider_md5": metadata.get("md5Checksum"),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _read_manifest():
    if not MANIFEST.exists():
        return {}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
