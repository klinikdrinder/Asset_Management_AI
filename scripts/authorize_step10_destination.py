"""Authorize and metadata-verify the isolated Step 10 destination profile."""

from __future__ import annotations

import argparse
import json

from kdi_media.google_drive import (
    DRIVE_DESTINATION_WRITE_SCOPE,
    FOLDER_MIME_TYPE,
    DriveCredentialProfile,
    GoogleDriveAccessError,
    create_destination_write_drive_service,
    load_destination_oauth_config,
    require_expected_account,
    require_write_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--folder-id", required=True)
    parser.add_argument(
        "--expected-account",
        default="kdimediaautomation@gmail.com",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.authorize:
        raise SystemExit(
            "Explicit --authorize is required for destination_write"
        )

    require_write_profile(DriveCredentialProfile.DESTINATION_WRITE)
    config = load_destination_oauth_config()
    service = create_destination_write_drive_service(config)
    account = require_expected_account(service, args.expected_account)
    fields = (
        "id,name,mimeType,driveId,parents,trashed,"
        "capabilities(canAddChildren,canEdit,canCopy,canShare,canListChildren)"
    )
    try:
        item = (
            service.files()
            .get(
                fileId=args.folder_id,
                fields=fields,
                supportsAllDrives=True,
            )
            .execute()
        )
    except Exception as exc:
        raise GoogleDriveAccessError(
            "Destination folder metadata is not accessible"
        ) from exc
    if item.get("id") != args.folder_id:
        raise GoogleDriveAccessError(
            "Destination metadata returned an unexpected folder ID"
        )
    if item.get("mimeType") != FOLDER_MIME_TYPE:
        raise GoogleDriveAccessError(
            "Configured destination is not a Google Drive folder"
        )

    result = {
        "profile": DriveCredentialProfile.DESTINATION_WRITE.value,
        "scope": DRIVE_DESTINATION_WRITE_SCOPE,
        "authenticated_account": account,
        "folder_id_match": True,
        "folder_name": item.get("name"),
        "is_folder": True,
        "trashed": item.get("trashed") is True,
        "drive_context": (
            "SHARED_DRIVE_FOLDER" if item.get("driveId") else "MY_DRIVE_FOLDER"
        ),
        "shared_drive_id": item.get("driveId"),
        "capabilities": item.get("capabilities") or {},
        "metadata_verification": "DESTINATION_WRITE_METADATA_VERIFIED",
        "drive_write_requests": 0,
        "child_listing_requests": 0,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
