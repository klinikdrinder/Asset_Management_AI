"""Strictly read-only Google Drive authentication and metadata access."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping
import os
from unittest.mock import patch

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from .rules import FileRuleInput, ReasonCode, evaluate_file


DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_READONLY_SCOPES = (DRIVE_READONLY_SCOPE,)
DRIVE_DESTINATION_WRITE_SCOPE = "https://www.googleapis.com/auth/drive"
DRIVE_DESTINATION_WRITE_SCOPES = (DRIVE_DESTINATION_WRITE_SCOPE,)
EXPECTED_AUTOMATION_ACCOUNT = "kdimediaautomation@gmail.com"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
ITEM_FIELDS = (
    "id,name,mimeType,fileExtension,size,createdTime,modifiedTime,"
    "parents,driveId,webViewLink,md5Checksum"
)
LIST_FIELDS = f"nextPageToken,files({ITEM_FIELDS})"
FOLDER_CLASSIFICATION = "folder"
SUPPORTED_FILE_CLASSIFICATION = "supported_file"
UNSUPPORTED_FILE_CLASSIFICATION = "unsupported_file"
INACCESSIBLE_ITEM_CLASSIFICATION = "inaccessible_item"
ACCESSIBLE_STATUS = "accessible"
INACCESSIBLE_STATUS = "inaccessible"


class GoogleDriveError(RuntimeError):
    """Base class for safe, non-secret Google Drive errors."""


class GoogleDriveConfigurationError(GoogleDriveError):
    """Raised when local OAuth configuration is incomplete or unsafe."""


class GoogleDriveAuthenticationError(GoogleDriveError):
    """Raised when read-only OAuth authentication cannot be completed."""


class GoogleDriveBrowserLaunchError(GoogleDriveAuthenticationError):
    """Raised when the desktop OAuth page cannot be opened."""


class DriveCredentialProfile(StrEnum):
    SOURCE_READONLY = "source_readonly"
    DESTINATION_WRITE = "destination_write"


class GoogleDriveAccessError(GoogleDriveError):
    """Raised when Drive metadata cannot be accessed."""


class GoogleDriveNotFolderError(GoogleDriveError):
    """Raised when a requested Drive item is not a folder."""


@dataclass(frozen=True)
class GoogleDriveOAuthConfig:
    """Filesystem locations used by the desktop OAuth flow."""

    credentials_file: Path
    token_file: Path


@dataclass(frozen=True)
class DriveItem:
    """Selected non-content metadata for one Google Drive item."""

    id: str
    name: str
    mime_type: str
    file_extension: str | None
    created_time: str | None
    modified_time: str | None
    size: int | None
    md5_checksum: str | None
    parents: tuple[str, ...]
    drive_id: str | None
    web_view_link: str | None

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "DriveItem":
        item_id = str(value.get("id") or "")
        if not item_id:
            raise GoogleDriveAccessError(
                "Google Drive returned metadata without an item ID"
            )
        raw_size = value.get("size")
        try:
            size = int(raw_size) if raw_size is not None else None
        except (TypeError, ValueError) as exc:
            raise GoogleDriveAccessError(
                f"Google Drive returned an invalid size for item {item_id}"
            ) from exc
        return cls(
            id=item_id,
            name=str(value.get("name") or item_id),
            mime_type=str(value.get("mimeType") or ""),
            file_extension=_optional_text(value.get("fileExtension")),
            created_time=_optional_text(value.get("createdTime")),
            modified_time=_optional_text(value.get("modifiedTime")),
            size=size,
            md5_checksum=_optional_text(value.get("md5Checksum")),
            parents=tuple(str(parent) for parent in value.get("parents") or ()),
            drive_id=_optional_text(value.get("driveId")),
            web_view_link=_optional_text(value.get("webViewLink")),
        )


@dataclass(frozen=True)
class FolderListing:
    """Immediate children returned from one folder listing."""

    children: tuple[DriveItem, ...]
    page_count: int

    @property
    def pagination_used(self) -> bool:
        return self.page_count > 1


@dataclass(frozen=True)
class RecursiveScanItem:
    """Sanitized metadata retained for one recursively discovered Drive item."""

    file_id: str
    name: str
    mime_type: str
    file_extension: str | None
    size: int | None
    created_time: str | None
    modified_time: str | None
    md5_checksum: str | None
    parent_folder_id: str
    relative_folder_path: str
    web_view_link: str | None
    accessibility_status: str
    classification: str


@dataclass(frozen=True)
class RecursiveScanError:
    """Non-sensitive failure information from a recursive metadata scan."""

    item_id: str
    failure_category: str
    http_status: int | None
    message: str


@dataclass(frozen=True)
class RecursiveScanSummary:
    folders_scanned: int
    total_items_discovered: int
    total_files_found: int
    supported_files: int
    unsupported_files: int
    inaccessible_items: int
    errors: int
    api_pages_requested: int


@dataclass(frozen=True)
class RecursiveScanReport:
    root: DriveItem
    items: tuple[RecursiveScanItem, ...]
    errors: tuple[RecursiveScanError, ...]
    summary: RecursiveScanSummary


def load_oauth_config(
    environment: Mapping[str, str] | None = None,
) -> GoogleDriveOAuthConfig:
    """Load required OAuth file locations without reading either file."""

    if environment is None:
        load_dotenv()
        environment = os.environ
    credentials_value = _required_environment(
        environment,
        "GOOGLE_DRIVE_CREDENTIALS_FILE",
    )
    token_value = _required_environment(
        environment,
        "GOOGLE_DRIVE_TOKEN_FILE",
    )
    return GoogleDriveOAuthConfig(
        credentials_file=Path(credentials_value).expanduser(),
        token_file=Path(token_value).expanduser(),
    )


def load_destination_oauth_config(
    environment: Mapping[str, str] | None = None,
) -> GoogleDriveOAuthConfig:
    """Load the explicit destination-write token path without source fallback."""

    if environment is None:
        load_dotenv()
        environment = os.environ
    credentials_value = _required_environment(
        environment,
        "GOOGLE_DRIVE_CREDENTIALS_FILE",
    )
    source_token_value = _required_environment(
        environment,
        "GOOGLE_DRIVE_TOKEN_FILE",
    )
    destination_token_value = _required_environment(
        environment,
        "GOOGLE_DRIVE_DESTINATION_TOKEN_FILE",
    )
    source_token = Path(source_token_value).expanduser().resolve()
    destination_token = Path(destination_token_value).expanduser().resolve()
    if source_token == destination_token:
        raise GoogleDriveConfigurationError(
            "Source and destination OAuth token paths must differ"
        )
    return GoogleDriveOAuthConfig(
        credentials_file=Path(credentials_value).expanduser(),
        token_file=destination_token,
    )


def load_readonly_credentials(
    config: GoogleDriveOAuthConfig,
) -> Credentials:
    """Reuse, refresh, or create credentials with only Drive read access."""

    if not config.credentials_file.is_file():
        raise GoogleDriveConfigurationError(
            "Google OAuth desktop credentials file is missing"
        )

    credentials: Credentials | None = None
    if config.token_file.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(
                str(config.token_file),
                scopes=list(DRIVE_READONLY_SCOPES),
            )
        except (OSError, ValueError):
            credentials = None

    if credentials is not None:
        _require_exact_readonly_scopes(credentials)
        if credentials.valid:
            return credentials
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except RefreshError as exc:
                raise GoogleDriveAuthenticationError(
                    "Saved Google OAuth token could not be refreshed"
                ) from exc
            _require_exact_readonly_scopes(credentials)
            _save_token(config.token_file, credentials)
            return credentials

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(config.credentials_file),
            scopes=list(DRIVE_READONLY_SCOPES),
        )
        with patch("webbrowser.open", new=_open_oauth_in_default_browser):
            credentials = flow.run_local_server(
                port=0,
                authorization_prompt_message="",
            )
    except (OSError, ValueError) as exc:
        raise GoogleDriveAuthenticationError(
            "Google OAuth browser authentication could not be started"
        ) from exc
    if credentials is None or not credentials.valid:
        raise GoogleDriveAuthenticationError(
            "Google OAuth browser authentication did not return a valid token"
        )
    _require_exact_readonly_scopes(credentials)
    _save_token(config.token_file, credentials)
    return credentials


def load_destination_write_credentials(
    config: GoogleDriveOAuthConfig,
) -> Credentials:
    """Reuse, refresh, or create the isolated destination-write credential."""

    return _load_exact_scope_credentials(
        config,
        scopes=DRIVE_DESTINATION_WRITE_SCOPES,
        profile=DriveCredentialProfile.DESTINATION_WRITE,
    )


def _load_exact_scope_credentials(
    config: GoogleDriveOAuthConfig,
    *,
    scopes: tuple[str, ...],
    profile: DriveCredentialProfile,
) -> Credentials:
    if not config.credentials_file.is_file():
        raise GoogleDriveConfigurationError(
            "Google OAuth desktop credentials file is missing"
        )

    credentials: Credentials | None = None
    if config.token_file.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(
                str(config.token_file),
                scopes=list(scopes),
            )
        except (OSError, ValueError):
            credentials = None

    if credentials is not None:
        _require_exact_scopes(credentials, scopes, profile)
        if credentials.valid:
            return credentials
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except RefreshError as exc:
                raise GoogleDriveAuthenticationError(
                    f"Saved {profile.value} OAuth token could not be refreshed"
                ) from exc
            _require_exact_scopes(credentials, scopes, profile)
            _save_token(config.token_file, credentials)
            return credentials

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(config.credentials_file),
            scopes=list(scopes),
        )
        with patch("webbrowser.open", new=_open_oauth_in_default_browser):
            credentials = flow.run_local_server(
                port=0,
                authorization_prompt_message="",
            )
    except (OSError, ValueError) as exc:
        raise GoogleDriveAuthenticationError(
            f"{profile.value} OAuth browser authentication could not be started"
        ) from exc
    if credentials is None or not credentials.valid:
        raise GoogleDriveAuthenticationError(
            f"{profile.value} OAuth authentication did not return a valid token"
        )
    _require_exact_scopes(credentials, scopes, profile)
    _save_token(config.token_file, credentials)
    return credentials


def create_readonly_drive_service(
    config: GoogleDriveOAuthConfig | None = None,
) -> Resource:
    """Create an authenticated Drive API v3 service with read-only OAuth."""

    resolved_config = config or load_oauth_config()
    credentials = load_readonly_credentials(resolved_config)
    try:
        return build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
    except Exception as exc:
        raise GoogleDriveAuthenticationError(
            "Authenticated Google Drive service could not be created"
        ) from exc


def create_service_account_readonly_drive_service(
    credentials_path: str | Path | None = None,
) -> Resource:
    """Create the permanent KDI Master reader from a service-account key."""
    configured = credentials_path or os.environ.get(
        "GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH",
        r"C:\Users\Public\Asset_Management_AI\.secrets\kdi-media-reader.json",
    )
    path = Path(configured).expanduser()
    if not path.is_file():
        raise GoogleDriveConfigurationError(
            "Google Drive service-account credentials file is missing"
        )
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(path), scopes=list(DRIVE_READONLY_SCOPES)
        )
        return build("drive", "v3", credentials=credentials, cache_discovery=False)
    except Exception as exc:
        raise GoogleDriveAuthenticationError(
            "Google Drive service-account authentication failed"
        ) from exc


def create_destination_write_drive_service(
    config: GoogleDriveOAuthConfig | None = None,
) -> Resource:
    """Create Drive service only from the explicit destination-write profile."""

    resolved_config = config or load_destination_oauth_config()
    credentials = load_destination_write_credentials(resolved_config)
    try:
        return build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
    except Exception as exc:
        raise GoogleDriveAuthenticationError(
            "Destination-write Drive service could not be created"
        ) from exc


def require_write_profile(profile: DriveCredentialProfile | str) -> None:
    """Reject write-required work unless destination_write was explicit."""

    try:
        resolved = DriveCredentialProfile(profile)
    except ValueError as exc:
        raise GoogleDriveConfigurationError(
            "Unknown Google Drive credential profile"
        ) from exc
    if resolved is not DriveCredentialProfile.DESTINATION_WRITE:
        raise GoogleDriveConfigurationError(
            "Write-required Drive work requires destination_write profile"
        )


def require_expected_account(
    service: Resource,
    expected_email: str = EXPECTED_AUTOMATION_ACCOUNT,
) -> str:
    """Return account email or reject a mismatched destination identity."""

    actual = get_authenticated_account_email(service)
    if actual is None or actual.casefold() != expected_email.casefold():
        raise GoogleDriveAuthenticationError(
            "Authenticated Google account does not match the expected account"
        )
    return actual


def get_item_metadata(service: Resource, item_id: str) -> DriveItem:
    """Retrieve selected metadata for one Drive item without file content."""

    item_id = _required_text("item_id", item_id)
    try:
        response = (
            service.files()
            .get(
                fileId=item_id,
                fields=ITEM_FIELDS,
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleDriveAccessError(
            f"Google Drive item {item_id} is not accessible"
        ) from exc
    return DriveItem.from_api(response)


def verify_folder_access(service: Resource, folder_id: str) -> DriveItem:
    """Confirm that an accessible Drive item is a folder."""

    item = get_item_metadata(service, folder_id)
    if item.mime_type != FOLDER_MIME_TYPE:
        raise GoogleDriveNotFolderError(
            f"Google Drive item {item.id} is not a folder"
        )
    return item


def list_immediate_children(
    service: Resource,
    folder_id: str,
    *,
    page_size: int = 1000,
) -> FolderListing:
    """List direct children only, following API pagination safely."""

    folder_id = _required_text("folder_id", folder_id)
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size must be between 1 and 1000")
    safe_folder_id = folder_id.replace("\\", "\\\\").replace("'", "\\'")
    page_token: str | None = None
    children: list[DriveItem] = []
    page_count = 0

    while True:
        try:
            response = (
                service.files()
                .list(
                    q=f"'{safe_folder_id}' in parents and trashed = false",
                    spaces="drive",
                    fields=LIST_FIELDS,
                    pageSize=page_size,
                    pageToken=page_token,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
        except HttpError as exc:
            raise GoogleDriveAccessError(
                f"Google Drive folder {folder_id} could not be listed"
            ) from exc
        page_count += 1
        children.extend(
            DriveItem.from_api(item) for item in response.get("files", ())
        )
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break
        page_token = str(next_page_token)

    return FolderListing(tuple(children), page_count)


def scan_folder_recursive(
    service: Resource,
    root_folder_id: str,
    *,
    page_size: int = 1000,
) -> RecursiveScanReport:
    """Breadth-first, metadata-only scan of an accessible Drive folder tree."""

    root = verify_folder_access(service, root_folder_id)
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size must be between 1 and 1000")

    pending = deque([(root.id, "")])
    visited = {root.id}
    folder_metadata = {root.id: root}
    items: list[RecursiveScanItem] = []
    errors: list[RecursiveScanError] = []
    folders_scanned = 0
    api_pages_requested = 0

    while pending:
        folder_id, folder_path = pending.popleft()
        page_token: str | None = None
        folder_listed = False
        safe_folder_id = _escape_drive_query_value(folder_id)

        while True:
            api_pages_requested += 1
            try:
                response = (
                    service.files()
                    .list(
                        q=(
                            f"'{safe_folder_id}' in parents "
                            "and trashed = false"
                        ),
                        spaces="drive",
                        fields=LIST_FIELDS,
                        pageSize=page_size,
                        pageToken=page_token,
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                    )
                    .execute()
                )
            except HttpError as exc:
                known_folder = folder_metadata[folder_id]
                _record_inaccessible_folder(
                    items,
                    known_folder,
                    folder_path,
                    is_root=folder_id == root.id,
                )
                errors.append(
                    _sanitized_scan_error(
                        folder_id,
                        "folder_listing_failed",
                        exc,
                        "Nested folder metadata could not be listed",
                    )
                )
                break
            except (OSError, ValueError, TypeError) as exc:
                known_folder = folder_metadata[folder_id]
                _record_inaccessible_folder(
                    items,
                    known_folder,
                    folder_path,
                    is_root=folder_id == root.id,
                )
                errors.append(
                    _sanitized_scan_error(
                        folder_id,
                        "folder_listing_failed",
                        exc,
                        "Nested folder metadata could not be listed",
                    )
                )
                break

            folder_listed = True
            for raw_item in response.get("files", ()):
                raw_item_id = str(raw_item.get("id") or "unknown")
                try:
                    item = DriveItem.from_api(raw_item)
                except (GoogleDriveAccessError, TypeError, ValueError) as exc:
                    items.append(
                        RecursiveScanItem(
                            file_id=raw_item_id,
                            name=str(raw_item.get("name") or raw_item_id),
                            mime_type=str(raw_item.get("mimeType") or ""),
                            file_extension=_optional_text(
                                raw_item.get("fileExtension")
                            ),
                            size=None,
                            created_time=_optional_text(
                                raw_item.get("createdTime")
                            ),
                            modified_time=_optional_text(
                                raw_item.get("modifiedTime")
                            ),
                            md5_checksum=_optional_text(
                                raw_item.get("md5Checksum")
                            ),
                            parent_folder_id=folder_id,
                            relative_folder_path=folder_path,
                            web_view_link=None,
                            accessibility_status=INACCESSIBLE_STATUS,
                            classification=INACCESSIBLE_ITEM_CLASSIFICATION,
                        )
                    )
                    errors.append(
                        _sanitized_scan_error(
                            raw_item_id,
                            "item_metadata_invalid",
                            exc,
                            "Item metadata was incomplete or invalid",
                        )
                    )
                    continue

                is_folder = item.mime_type == FOLDER_MIME_TYPE
                item_folder_path = (
                    _join_relative_path(folder_path, item.name)
                    if is_folder
                    else folder_path
                )
                classification = _classify_drive_item(item)
                items.append(
                    RecursiveScanItem(
                        file_id=item.id,
                        name=item.name,
                        mime_type=item.mime_type,
                        file_extension=item.file_extension,
                        size=item.size,
                        created_time=item.created_time,
                        modified_time=item.modified_time,
                        md5_checksum=item.md5_checksum,
                        parent_folder_id=folder_id,
                        relative_folder_path=item_folder_path,
                        web_view_link=item.web_view_link,
                        accessibility_status=ACCESSIBLE_STATUS,
                        classification=classification,
                    )
                )

                if is_folder and item.id not in visited:
                    visited.add(item.id)
                    folder_metadata[item.id] = item
                    pending.append((item.id, item_folder_path))

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
            page_token = str(next_page_token)

        if folder_listed:
            folders_scanned += 1

    supported_files = sum(
        item.classification == SUPPORTED_FILE_CLASSIFICATION
        for item in items
    )
    unsupported_files = sum(
        item.classification == UNSUPPORTED_FILE_CLASSIFICATION
        for item in items
    )
    inaccessible_items = sum(
        item.classification == INACCESSIBLE_ITEM_CLASSIFICATION
        for item in items
    )
    return RecursiveScanReport(
        root=root,
        items=tuple(items),
        errors=tuple(errors),
        summary=RecursiveScanSummary(
            folders_scanned=folders_scanned,
            total_items_discovered=len(items),
            total_files_found=supported_files + unsupported_files,
            supported_files=supported_files,
            unsupported_files=unsupported_files,
            inaccessible_items=inaccessible_items,
            errors=len(errors),
            api_pages_requested=api_pages_requested,
        ),
    )


def get_authenticated_account_email(service: Resource) -> str | None:
    """Return the authenticated account email when the API makes it available."""

    try:
        response = service.about().get(fields="user(emailAddress)").execute()
    except HttpError as exc:
        raise GoogleDriveAccessError(
            "Authenticated Google account metadata is not accessible"
        ) from exc
    return _optional_text((response.get("user") or {}).get("emailAddress"))


def _save_token(token_file: Path, credentials: Credentials) -> None:
    try:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    except OSError as exc:
        raise GoogleDriveAuthenticationError(
            "Google OAuth token could not be saved at the configured location"
        ) from exc


def _open_oauth_in_default_browser(
    authorization_url: str,
    new: int = 0,
    autoraise: bool = True,
) -> bool:
    """Open an OAuth URL through the Windows default-browser association."""

    del new, autoraise
    try:
        os.startfile(authorization_url)
    except (AttributeError, OSError) as exc:
        raise GoogleDriveBrowserLaunchError(
            "Google OAuth browser launch failed"
        ) from exc
    return True


def _require_exact_readonly_scopes(credentials: Credentials) -> None:
    scopes = credentials.granted_scopes or credentials.scopes
    if scopes is not None and set(scopes) != set(DRIVE_READONLY_SCOPES):
        raise GoogleDriveAuthenticationError(
            "Google OAuth token does not use exactly the required read-only scope"
        )
    if not credentials.has_scopes(list(DRIVE_READONLY_SCOPES)):
        raise GoogleDriveAuthenticationError(
            "Google OAuth token is missing the required read-only scope"
        )


def _require_exact_scopes(
    credentials: Credentials,
    expected_scopes: tuple[str, ...],
    profile: DriveCredentialProfile,
) -> None:
    granted = credentials.granted_scopes or credentials.scopes
    if granted is not None and set(granted) != set(expected_scopes):
        raise GoogleDriveAuthenticationError(
            f"{profile.value} OAuth token scope does not match its profile"
        )
    if not credentials.has_scopes(list(expected_scopes)):
        raise GoogleDriveAuthenticationError(
            f"{profile.value} OAuth token is missing its required scope"
        )


def _required_environment(
    environment: Mapping[str, str],
    name: str,
) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise GoogleDriveConfigurationError(
            f"Missing required environment variable: {name}"
        )
    return value


def _required_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _classify_drive_item(item: DriveItem) -> str:
    if item.mime_type == FOLDER_MIME_TYPE:
        return FOLDER_CLASSIFICATION
    decision = evaluate_file(
        FileRuleInput(
            file_name=item.name,
            mime_type=item.mime_type,
            file_extension=item.file_extension,
            size_bytes=item.size,
            accessibility_status=ACCESSIBLE_STATUS,
            is_folder=False,
        )
    )
    if (
        decision.automatic_decision == "TAKE"
        and decision.reason_code == ReasonCode.SUPPORTED_FORMAT
    ):
        return SUPPORTED_FILE_CLASSIFICATION
    return UNSUPPORTED_FILE_CLASSIFICATION


def _inaccessible_scan_item(
    item: DriveItem,
    *,
    parent_folder_id: str,
    relative_folder_path: str,
) -> RecursiveScanItem:
    return RecursiveScanItem(
        file_id=item.id,
        name=item.name,
        mime_type=item.mime_type,
        file_extension=item.file_extension,
        size=item.size,
        created_time=item.created_time,
        modified_time=item.modified_time,
        md5_checksum=item.md5_checksum,
        parent_folder_id=parent_folder_id,
        relative_folder_path=relative_folder_path,
        web_view_link=item.web_view_link,
        accessibility_status=INACCESSIBLE_STATUS,
        classification=INACCESSIBLE_ITEM_CLASSIFICATION,
    )


def _record_inaccessible_folder(
    items: list[RecursiveScanItem],
    folder: DriveItem,
    folder_path: str,
    *,
    is_root: bool,
) -> None:
    inaccessible = _inaccessible_scan_item(
        folder,
        parent_folder_id=folder.parents[0] if folder.parents else "",
        relative_folder_path=folder_path,
    )
    for index, item in enumerate(items):
        if item.file_id == folder.id:
            items[index] = inaccessible
            return
    if not is_root:
        items.append(inaccessible)


def _sanitized_scan_error(
    item_id: str,
    category: str,
    error: Exception,
    message: str,
) -> RecursiveScanError:
    response = getattr(error, "resp", None)
    raw_status = getattr(response, "status", None)
    try:
        status = int(raw_status) if raw_status is not None else None
    except (TypeError, ValueError):
        status = None
    return RecursiveScanError(
        item_id=item_id,
        failure_category=category,
        http_status=status,
        message=message,
    )


def _escape_drive_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _join_relative_path(parent: str, name: str) -> str:
    return f"{parent}/{name}" if parent else name
