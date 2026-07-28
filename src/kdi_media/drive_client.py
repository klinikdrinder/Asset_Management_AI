"""Google Drive API v3 access, recursive scanning, and copying."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."
FILE_FIELDS = (
    "nextPageToken,files("
    "id,name,mimeType,fileExtension,size,md5Checksum,"
    "createdTime,modifiedTime,webViewLink,thumbnailLink,"
    "parents,trashed,driveId,capabilities(canCopy,canEdit,canComment)"
    ")"
)


class DriveClient:
    def __init__(self, credentials: Credentials) -> None:
        self.service: Resource = build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

    def get_folder(self, folder_id: str) -> dict[str, Any]:
        folder = (
            self.service.files()
            .get(
                fileId=folder_id,
                fields=(
                    "id,name,mimeType,driveId,"
                    "capabilities(canCopy,canEdit,canComment)"
                ),
                supportsAllDrives=True,
            )
            .execute()
        )
        if folder.get("mimeType") != FOLDER_MIME_TYPE:
            raise ValueError(f"Drive item {folder_id!r} is not a folder")
        return folder

    def iter_files_recursive(
        self,
        root_folder_id: str,
    ) -> Iterator[tuple[dict[str, Any], str]]:
        pending = deque([(root_folder_id, "")])
        visited = {root_folder_id}

        while pending:
            folder_id, relative_parent = pending.popleft()
            page_token = None

            while True:
                response = (
                    self.service.files()
                    .list(
                        q=(
                            f"'{folder_id}' in parents "
                            "and trashed = false"
                        ),
                        spaces="drive",
                        fields=FILE_FIELDS,
                        pageSize=1000,
                        pageToken=page_token,
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                    )
                    .execute()
                )

                for item in response.get("files", []):
                    name = item.get("name", "")
                    relative_path = (
                        f"{relative_parent}/{name}"
                        if relative_parent
                        else name
                    )
                    if item.get("mimeType") == FOLDER_MIME_TYPE:
                        if item["id"] not in visited:
                            visited.add(item["id"])
                            pending.append((item["id"], relative_path))
                        continue
                    yield item, relative_path

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

    def copy_file(
        self,
        file_id: str,
        destination_folder_id: str,
        file_name: str,
        source_folder_id: str,
    ) -> dict[str, Any]:
        return (
            self.service.files()
            .copy(
                fileId=file_id,
                body={
                    "name": file_name,
                    "parents": [destination_folder_id],
                    "appProperties": {
                        "kdiSourceGoogleFileId": file_id,
                        "kdiSourceFolderId": source_folder_id,
                    },
                },
                fields="id,name,mimeType,size,md5Checksum,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

    def find_existing_copy(
        self,
        *,
        source_google_file_id: str,
        source_folder_id: str,
        destination_folder_id: str,
    ) -> dict[str, Any] | None:
        safe_file_id = source_google_file_id.replace("'", "\\'")
        safe_folder_id = source_folder_id.replace("'", "\\'")
        safe_destination_id = destination_folder_id.replace("'", "\\'")
        query = (
            f"'{safe_destination_id}' in parents and trashed = false "
            "and appProperties has "
            f"{{ key='kdiSourceGoogleFileId' and value='{safe_file_id}' }} "
            "and appProperties has "
            f"{{ key='kdiSourceFolderId' and value='{safe_folder_id}' }}"
        )
        response = (
            self.service.files()
            .list(
                q=query,
                spaces="drive",
                fields=(
                    "files(id,name,mimeType,size,md5Checksum,webViewLink)"
                ),
                pageSize=1,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        files = response.get("files", [])
        return files[0] if files else None
