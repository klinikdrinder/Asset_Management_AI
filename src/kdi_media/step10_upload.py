"""Step 10 canonical-asset destination lifecycle and transfer primitives.

Importing this module performs no network, database, or filesystem operation.
Production effects require explicit adapters and an execute-enabled caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import os
from pathlib import Path
import random
import re
import tempfile
import time
import unicodedata
from typing import Any, Callable, Iterable, Mapping, Protocol
from uuid import UUID, NAMESPACE_URL, uuid5

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .google_drive import DriveCredentialProfile, require_write_profile
from .rules import FORMAT_POLICY
from .step9_hashing import iter_drive_content


MIGRATION_VERSION = "step10.v1"
APP_PROPERTY_ASSET_ID = "kdi_asset_id"
APP_PROPERTY_DESTINATION_ID = "kdi_destination_record_id"
APP_PROPERTY_VERSION = "kdi_migration_version"
DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 16.0)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class UploadStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    VERIFIED = "VERIFIED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SOURCE_ACCESS_DENIED = "SOURCE_ACCESS_DENIED"
    DESTINATION_ACCESS_DENIED = "DESTINATION_ACCESS_DENIED"
    DESTINATION_CONFLICT = "DESTINATION_CONFLICT"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class VerificationLevel(StrEnum):
    NONE = "NONE"
    SOURCE_HASH_VERIFIED = "SOURCE_HASH_VERIFIED"
    TRANSFER_BYTE_COUNT_VERIFIED = "TRANSFER_BYTE_COUNT_VERIFIED"
    DESTINATION_METADATA_VERIFIED = "DESTINATION_METADATA_VERIFIED"
    PROVIDER_CHECKSUM_VERIFIED = "PROVIDER_CHECKSUM_VERIFIED"
    DESTINATION_SHA256_VERIFIED = "DESTINATION_SHA256_VERIFIED"


class DestinationAction(StrEnum):
    CREATE = "CREATE"
    RECOVER = "RECOVER"
    SKIP = "SKIP"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    RETRY = "RETRY"


class Step10Error(RuntimeError):
    code = "STEP10_ERROR"
    retryable = False


class InvalidCanonicalState(Step10Error):
    code = "INVALID_CANONICAL_STATE"


class SourceChanged(Step10Error):
    code = "SOURCE_CHANGED"


class SourceNotFound(Step10Error):
    code = "SOURCE_NOT_FOUND"


class SourceAccessDenied(Step10Error):
    code = "SOURCE_ACCESS_DENIED"


class DestinationAccessDenied(Step10Error):
    code = "DESTINATION_ACCESS_DENIED"


class DestinationConflict(Step10Error):
    code = "DESTINATION_CONFLICT"


class RetryableTransferError(Step10Error):
    code = "TRANSFER_RETRYABLE"
    retryable = True


class PermanentTransferError(Step10Error):
    code = "TRANSFER_PERMANENT"


@dataclass(frozen=True)
class SelectedSource:
    id: str
    source_folder_id: str
    google_file_id: str
    file_name: str
    mime_type: str
    file_extension: str
    size_bytes: int
    content_sha256: str
    drive_modified_at: str | None
    drive_version: str | None
    hash_status: str = "HASHED"
    hash_completed_at: str | None = None


@dataclass(frozen=True)
class DestinationPlan:
    asset_id: str
    selected_source_file_id: str
    destination_root_id: str
    category: str
    filename: str
    relative_path: str
    migration_version: str
    idempotency_key: str
    app_properties: Mapping[str, str]
    expected_bytes: int
    source_sha256: str
    mime_type: str
    extension: str


@dataclass(frozen=True)
class TransferResult:
    destination_google_file_id: str
    transferred_bytes: int
    metadata: Mapping[str, Any]


def select_canonical_source(
    asset: Mapping[str, Any],
    relationships: Iterable[Mapping[str, Any]],
    source_rows: Iterable[Mapping[str, Any]],
) -> SelectedSource:
    asset_id = _required_text("asset.id", asset.get("id"))
    asset_hash = str(
        asset.get("content_hash") or asset.get("checksum_sha256") or ""
    ).lower()
    if not SHA256_PATTERN.fullmatch(asset_hash):
        raise InvalidCanonicalState("Canonical asset has no valid SHA-256")
    linked_ids = {
        str(row.get("source_file_id") or "")
        for row in relationships
        if str(row.get("asset_id") or "") == asset_id
    }
    if not linked_ids:
        raise InvalidCanonicalState("Canonical asset has no source relationship")
    candidates = [
        _source_from_row(row, asset_hash)
        for row in source_rows
        if str(row.get("id") or "") in linked_ids
        and _source_row_is_valid(row, asset_hash)
    ]
    if not candidates:
        raise InvalidCanonicalState("Canonical asset has no valid source")
    preferred_id = str(
        (asset.get("metadata") or {}).get("canonical_source_file_id") or ""
    )
    preferred = next(
        (candidate for candidate in candidates if candidate.id == preferred_id),
        None,
    )
    if preferred is not None:
        return preferred
    return min(
        candidates,
        key=lambda source: (
            source.source_folder_id,
            source.google_file_id,
            source.id,
        ),
    )


def route_category(extension: str, mime_type: str) -> str:
    normalized_extension = extension.strip().lower().lstrip(".")
    normalized_mime = mime_type.strip().lower()
    policy = FORMAT_POLICY.get(normalized_extension)
    if (
        policy is None
        or not policy.accepted_for_migration
        or policy.required_mime_type != normalized_mime
    ):
        raise InvalidCanonicalState("Format is not approved for migration")
    return {
        "image": "Images",
        "video": "Videos",
        "document": "Documents",
    }[policy.media_category]


def destination_filename(
    asset_id: str,
    extension: str,
    *,
    original_name: str | None = None,
    allow_safe_stem: bool = False,
    max_length: int = 120,
) -> str:
    if max_length < 32:
        raise ValueError("max_length must be at least 32")
    suffix = UUID(asset_id).hex[:8]
    normalized_extension = extension.strip().lower().lstrip(".")
    if normalized_extension not in FORMAT_POLICY:
        raise InvalidCanonicalState("Destination extension is unsupported")
    stem = ""
    if allow_safe_stem and original_name:
        stem = _sanitized_stem(original_name, normalized_extension)
        if _looks_sensitive(stem):
            stem = ""
    prefix = f"{stem}__" if stem else "asset__"
    tail = f"{suffix}.{normalized_extension}"
    room = max_length - len(tail)
    prefix = prefix[:room].rstrip(" .-")
    if not prefix:
        prefix = "asset__"
    result = f"{prefix}{tail}"
    if len(result) > max_length:
        raise InvalidCanonicalState("Destination filename exceeds limit")
    return result


def build_destination_plan(
    asset: Mapping[str, Any],
    source: SelectedSource,
    destination_root_id: str,
    *,
    destination_record_id: str,
    allow_safe_stem: bool = False,
) -> DestinationPlan:
    asset_id = _required_text("asset.id", asset.get("id"))
    root = _required_text("destination_root_id", destination_root_id)
    category = route_category(source.file_extension, source.mime_type)
    filename = destination_filename(
        asset_id,
        source.file_extension,
        original_name=source.file_name,
        allow_safe_stem=allow_safe_stem,
    )
    key = deterministic_idempotency_key(asset_id, root, MIGRATION_VERSION)
    properties = destination_app_properties(
        asset_id, destination_record_id, MIGRATION_VERSION
    )
    return DestinationPlan(
        asset_id=asset_id,
        selected_source_file_id=source.id,
        destination_root_id=root,
        category=category,
        filename=filename,
        relative_path=f"{category}/{filename}",
        migration_version=MIGRATION_VERSION,
        idempotency_key=key,
        app_properties=properties,
        expected_bytes=source.size_bytes,
        source_sha256=source.content_sha256,
        mime_type=source.mime_type,
        extension=source.file_extension.lower().lstrip("."),
    )


def lifecycle_values(
    plan: DestinationPlan,
    *,
    destination_record_id: str,
    destination_drive_id: str | None = None,
    source_metadata_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = dict(
        source_metadata_snapshot
        or {
            "source_file_id": plan.selected_source_file_id,
            "hash_algorithm": "SHA-256",
            "expected_bytes": plan.expected_bytes,
            "mime_type": plan.mime_type,
            "file_extension": plan.extension,
        }
    )
    return {
        "id": str(UUID(destination_record_id)),
        "asset_id": plan.asset_id,
        "selected_source_file_id": plan.selected_source_file_id,
        "destination_folder_id": plan.destination_root_id,
        "destination_drive_id": destination_drive_id,
        "destination_filename": plan.filename,
        "destination_relative_path": plan.relative_path,
        "migration_version": plan.migration_version,
        "idempotency_key": plan.idempotency_key,
        "upload_status": UploadStatus.NOT_STARTED.value,
        "verification_level": VerificationLevel.SOURCE_HASH_VERIFIED.value,
        "expected_bytes": plan.expected_bytes,
        "transferred_bytes": 0,
        "source_sha256": plan.source_sha256,
        "upload_attempt_count": 0,
        "next_retry_at": None,
        "source_metadata_snapshot": snapshot,
        "destination_metadata_snapshot": {},
    }


def prepare_lifecycle_initialization(
    assets: Iterable[Mapping[str, Any]],
    relationships: Iterable[Mapping[str, Any]],
    source_rows: Iterable[Mapping[str, Any]],
    destination_root_id: str,
) -> tuple[dict[str, Any], ...]:
    """Build only valid canonical lifecycle rows without reading file content."""

    all_relationships = tuple(relationships)
    all_sources = tuple(source_rows)
    rows: list[dict[str, Any]] = []
    for asset in assets:
        try:
            selected = select_canonical_source(
                asset, all_relationships, all_sources
            )
        except InvalidCanonicalState:
            continue
        asset_id = _required_text("asset.id", asset.get("id"))
        record_id = str(
            uuid5(
                NAMESPACE_URL,
                "kdi-step10-destination-record:"
                f"{asset_id}|{destination_root_id}|{MIGRATION_VERSION}",
            )
        )
        plan = build_destination_plan(
            asset,
            selected,
            destination_root_id,
            destination_record_id=record_id,
            allow_safe_stem=False,
        )
        rows.append(
            lifecycle_values(
                plan,
                destination_record_id=record_id,
                source_metadata_snapshot={
                    "source_file_id": selected.id,
                    "source_folder_id": selected.source_folder_id,
                    "google_file_id": selected.google_file_id,
                    "hash_algorithm": "SHA-256",
                    "hash_status": selected.hash_status,
                    "hash_completed_at": selected.hash_completed_at,
                    "expected_bytes": selected.size_bytes,
                    "mime_type": selected.mime_type,
                    "file_extension": selected.file_extension,
                    "drive_modified_at": selected.drive_modified_at,
                    "drive_version": selected.drive_version,
                },
            )
        )
    return tuple(sorted(rows, key=lambda row: (row["asset_id"], row["id"])))


def deterministic_idempotency_key(
    asset_id: str, destination_folder_id: str, migration_version: str
) -> str:
    material = "|".join(
        (
            str(UUID(asset_id)),
            _required_text("destination_folder_id", destination_folder_id),
            _required_text("migration_version", migration_version),
        )
    )
    return str(uuid5(NAMESPACE_URL, f"kdi-step10:{material}"))


def destination_app_properties(
    asset_id: str, destination_record_id: str, migration_version: str
) -> dict[str, str]:
    return {
        APP_PROPERTY_ASSET_ID: str(UUID(asset_id)),
        APP_PROPERTY_DESTINATION_ID: str(UUID(destination_record_id)),
        APP_PROPERTY_VERSION: _required_text(
            "migration_version", migration_version
        ),
    }


def decide_destination_action(
    lifecycle: Mapping[str, Any],
    marker_matches: Iterable[Mapping[str, Any]],
) -> DestinationAction:
    status = str(lifecycle.get("upload_status") or "NOT_STARTED")
    destination_id = str(lifecycle.get("destination_google_file_id") or "")
    matches = list(marker_matches)
    if len(matches) > 1:
        return DestinationAction.MANUAL_REVIEW
    if status == UploadStatus.VERIFIED:
        if destination_id and len(matches) == 1:
            return DestinationAction.SKIP
        return DestinationAction.MANUAL_REVIEW
    if destination_id:
        if len(matches) == 1 and matches[0].get("id") == destination_id:
            return DestinationAction.RECOVER
        return DestinationAction.MANUAL_REVIEW
    if len(matches) == 1:
        return DestinationAction.RECOVER
    if status == UploadStatus.FAILED_RETRYABLE:
        return DestinationAction.RETRY
    if status in (
        UploadStatus.FAILED_PERMANENT,
        UploadStatus.DESTINATION_CONFLICT,
        UploadStatus.MANUAL_REVIEW_REQUIRED,
    ):
        return DestinationAction.MANUAL_REVIEW
    return DestinationAction.CREATE


def preflight_source(
    stored: Mapping[str, Any],
    current: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not current:
        raise SourceNotFound("Source metadata is missing")
    if current.get("access_denied") is True:
        raise SourceAccessDenied("Source access is denied")
    if current.get("trashed") is True:
        raise SourceChanged("Source is trashed")
    expected_id = _required_text("google_file_id", stored.get("google_file_id"))
    if str(current.get("id") or "") != expected_id:
        raise SourceChanged("Source identity changed")
    expected_size = stored.get("hash_expected_bytes", stored.get("size_bytes"))
    if not isinstance(expected_size, int) or expected_size < 0:
        raise InvalidCanonicalState("Expected source byte count is missing")
    current_size = _integer_or_none(current.get("size"))
    if current_size is None or current_size != expected_size:
        raise SourceChanged("Source size changed")
    expected_mime = str(
        stored.get("hash_drive_mime_type") or stored.get("mime_type") or ""
    ).lower()
    current_mime = str(current.get("mimeType") or "").lower()
    if not expected_mime or current_mime != expected_mime:
        raise SourceChanged("Source MIME type changed")
    expected_modified = _optional_text(
        stored.get("hash_drive_modified_at")
        or stored.get("drive_modified_at")
    )
    current_modified = _optional_text(current.get("modifiedTime"))
    if (
        expected_modified
        and current_modified
        and _normalized_drive_timestamp(expected_modified)
        != _normalized_drive_timestamp(current_modified)
    ):
        raise SourceChanged("Source modified time changed")
    expected_version = _optional_text(stored.get("hash_drive_version"))
    current_version = _optional_text(
        current.get("version") or current.get("headRevisionId")
    )
    if expected_version and current_version and expected_version != current_version:
        raise SourceChanged("Source version changed")
    content_hash = str(stored.get("content_sha256") or "").lower()
    if not SHA256_PATTERN.fullmatch(content_hash):
        raise InvalidCanonicalState("Expected source SHA-256 is missing")
    extension = str(stored.get("file_extension") or "").lower().lstrip(".")
    route_category(extension, current_mime)
    return {
        "file_id": expected_id,
        "size_bytes": current_size,
        "mime_type": current_mime,
        "modified_time": current_modified,
        "version": current_version,
        "trashed": False,
    }


class DestinationRootGuard:
    def __init__(
        self,
        approved_root_id: str,
        approved_children: Mapping[str, str] | None = None,
    ) -> None:
        self.approved_root_id = _required_text(
            "approved_root_id", approved_root_id
        )
        self.approved_children = dict(approved_children or {})

    def require_root(self, parent_id: str) -> None:
        if parent_id != self.approved_root_id:
            raise DestinationAccessDenied(
                "Destination parent is not the approved KDI Master root"
            )

    def require_category_parent(self, category: str, parent_id: str) -> None:
        if self.approved_children.get(category) != parent_id:
            raise DestinationAccessDenied(
                "Destination parent is not an approved category child"
            )


def resolve_category_folder(
    service: Any,
    guard: DestinationRootGuard,
    category: str,
    *,
    allow_create: bool = False,
) -> str:
    if category not in {"Images", "Videos", "Documents"}:
        raise DestinationAccessDenied("Destination category is not approved")
    guard.require_root(guard.approved_root_id)
    safe_root = _escape_query(guard.approved_root_id)
    safe_category = _escape_query(category)
    query = (
        f"'{safe_root}' in parents and trashed = false "
        f"and mimeType = '{FOLDER_MIME_TYPE}' "
        "and appProperties has "
        f"{{ key='kdi_folder_role' and value='{safe_category}' }}"
    )
    response = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id,name,mimeType,parents,trashed,appProperties)",
            pageSize=2,
        )
        .execute()
    )
    matches = response.get("files") or []
    if len(matches) > 1:
        raise DestinationConflict("Duplicate category folders found")
    if len(matches) == 1:
        folder_id = _required_text("category folder id", matches[0].get("id"))
        return folder_id
    if not allow_create:
        raise DestinationConflict("Approved category folder is missing")
    body = {
        "name": category,
        "mimeType": FOLDER_MIME_TYPE,
        "parents": [guard.approved_root_id],
        "appProperties": {
            "kdi_folder_role": category,
            "kdi_root_id": guard.approved_root_id,
        },
    }
    created = (
        service.files()
        .create(body=body, fields="id", supportsAllDrives=True)
        .execute()
    )
    return _required_text("created category folder id", created.get("id"))


class DriveResumableTransfer:
    """Controlled temporary-spool transfer using separate Drive services."""

    def __init__(
        self,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        temp_root: Path,
        content_reader: Callable[..., Iterable[bytes]] = iter_drive_content,
        media_upload_factory: Callable[..., Any] = MediaFileUpload,
    ) -> None:
        if chunk_size < 256 * 1024:
            raise ValueError("chunk_size must be at least 256 KiB")
        self.chunk_size = chunk_size
        self.temp_root = temp_root
        self.content_reader = content_reader
        self.media_upload_factory = media_upload_factory

    def transfer(
        self,
        *,
        source_service: Any,
        destination_service: Any,
        source_profile: DriveCredentialProfile,
        destination_profile: DriveCredentialProfile,
        source_file_id: str,
        destination_parent_id: str,
        plan: DestinationPlan,
        guard: DestinationRootGuard,
    ) -> TransferResult:
        if source_profile is not DriveCredentialProfile.SOURCE_READONLY:
            raise DestinationAccessDenied(
                "Source reads require source_readonly profile"
            )
        require_write_profile(destination_profile)
        guard.require_category_parent(plan.category, destination_parent_id)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        media: Any = None
        request: Any = None
        observed = 0
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                prefix="step10-",
                suffix=".transfer",
                dir=self.temp_root,
                delete=False,
            ) as temporary:
                temp_path = Path(temporary.name)
                for chunk in self.content_reader(
                    source_service,
                    source_file_id,
                    chunk_size=self.chunk_size,
                ):
                    if not isinstance(chunk, bytes):
                        raise PermanentTransferError(
                            "Source stream returned a non-byte chunk"
                        )
                    temporary.write(chunk)
                    observed += len(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            if observed != plan.expected_bytes:
                raise RetryableTransferError(
                    "Transferred source byte count does not match expected"
                )
            media = self.media_upload_factory(
                str(temp_path),
                mimetype=plan.mime_type,
                chunksize=self.chunk_size,
                resumable=True,
            )
            request = destination_service.files().create(
                body={
                    "name": plan.filename,
                    "parents": [destination_parent_id],
                    "appProperties": dict(plan.app_properties),
                },
                media_body=media,
                fields=(
                    "id,name,mimeType,size,parents,trashed,appProperties,"
                    "md5Checksum,webViewLink"
                ),
                supportsAllDrives=True,
            )
            response = None
            while response is None:
                try:
                    _, response = request.next_chunk(num_retries=0)
                except HttpError as exc:
                    raise classify_transfer_http_error(exc) from exc
            return TransferResult(
                destination_google_file_id=_required_text(
                    "destination file id", response.get("id")
                ),
                transferred_bytes=observed,
                metadata=response,
            )
        finally:
            request = None
            media_file = getattr(media, "_fd", None)
            close_media_file = getattr(media_file, "close", None)
            if callable(close_media_file):
                close_media_file()
            media = None
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


class Step10UploadWorker:
    """One-asset worker; all effects are explicit and independently injected."""

    def __init__(
        self,
        *,
        repository: Any,
        source_service: Any,
        destination_service: Any,
        transfer_adapter: DriveResumableTransfer,
        root_guard: DestinationRootGuard,
        source_metadata_reader: Callable[[Any, str], Mapping[str, Any]],
        destination_lookup: Callable[
            [Any, str, DestinationPlan], list[Mapping[str, Any]]
        ],
        destination_metadata_reader: Callable[
            [Any, str], Mapping[str, Any]
        ],
    ) -> None:
        self.repository = repository
        self.source_service = source_service
        self.destination_service = destination_service
        self.transfer_adapter = transfer_adapter
        self.root_guard = root_guard
        self.source_metadata_reader = source_metadata_reader
        self.destination_lookup = destination_lookup
        self.destination_metadata_reader = destination_metadata_reader

    def process(
        self,
        *,
        lifecycle: Mapping[str, Any],
        asset: Mapping[str, Any],
        source: SelectedSource,
        stored_source_row: Mapping[str, Any],
        category_parent_id: str,
        worker_id: str,
        execute: bool = False,
    ) -> Mapping[str, Any]:
        plan = build_destination_plan(
            asset,
            source,
            str(lifecycle.get("destination_folder_id") or ""),
            destination_record_id=str(lifecycle.get("id") or ""),
            allow_safe_stem=False,
        )
        if (
            int(lifecycle.get("upload_attempt_count") or 0) > 0
            and str(lifecycle.get("selected_source_file_id") or "")
            != source.id
        ):
            raise DestinationConflict(
                "Source representative cannot change during an attempted upload"
            )
        if not execute:
            return {
                "outcome": "DRY_RUN",
                "asset_id": plan.asset_id,
                "relative_path": plan.relative_path,
            }
        self.root_guard.require_category_parent(
            plan.category, category_parent_id
        )
        current = self.source_metadata_reader(
            self.source_service, source.google_file_id
        )
        snapshot = preflight_source(stored_source_row, current)
        matches = self.destination_lookup(
            self.destination_service, category_parent_id, plan
        )
        action = decide_destination_action(lifecycle, matches)
        if action is DestinationAction.SKIP:
            return {"outcome": "SKIPPED_VERIFIED", "asset_id": plan.asset_id}
        if action is DestinationAction.MANUAL_REVIEW:
            raise DestinationConflict(
                "Destination identity requires manual review"
            )
        if not self.repository.mark_started(
            str(lifecycle.get("id") or ""),
            worker_id,
            snapshot,
        ):
            raise DestinationConflict("Upload start transition was not persisted")
        if action is DestinationAction.RECOVER:
            metadata = matches[0]
            destination_id = _required_text(
                "recovered destination id", metadata.get("id")
            )
            transferred = plan.expected_bytes
        else:
            result = self.transfer_adapter.transfer(
                source_service=self.source_service,
                destination_service=self.destination_service,
                source_profile=DriveCredentialProfile.SOURCE_READONLY,
                destination_profile=DriveCredentialProfile.DESTINATION_WRITE,
                source_file_id=source.google_file_id,
                destination_parent_id=category_parent_id,
                plan=plan,
                guard=self.root_guard,
            )
            destination_id = result.destination_google_file_id
            transferred = result.transferred_bytes
            metadata = result.metadata
        if not metadata:
            metadata = self.destination_metadata_reader(
                self.destination_service, destination_id
            )
        level = verify_destination_metadata(
            metadata,
            plan=plan,
            expected_parent_id=category_parent_id,
        )
        if not self.repository.complete_upload(
            str(lifecycle.get("id") or ""),
            worker_id,
            destination_id,
            transferred,
            metadata,
            level,
        ):
            raise DestinationConflict(
                "Upload completion transition was not persisted"
            )
        return {
            "outcome": (
                "RECOVERED"
                if action is DestinationAction.RECOVER
                else "UPLOADED"
            ),
            "asset_id": plan.asset_id,
            "destination_google_file_id": destination_id,
            "verification_level": level.value,
        }


def read_source_metadata(service: Any, file_id: str) -> Mapping[str, Any]:
    fields = (
        "id,mimeType,size,modifiedTime,version,headRevisionId,trashed,"
        "capabilities(canDownload)"
    )
    try:
        return (
            service.files()
            .get(fileId=file_id, fields=fields, supportsAllDrives=True)
            .execute()
        )
    except HttpError as exc:
        status = getattr(exc.resp, "status", None)
        if status == 404:
            raise SourceNotFound("Source file was not found") from exc
        if status in {401, 403}:
            raise SourceAccessDenied("Source file access is denied") from exc
        raise RetryableTransferError(
            "Source metadata request failed"
        ) from exc


def read_destination_metadata(
    service: Any, file_id: str
) -> Mapping[str, Any]:
    fields = (
        "id,name,mimeType,size,parents,trashed,appProperties,"
        "md5Checksum,webViewLink"
    )
    try:
        return (
            service.files()
            .get(fileId=file_id, fields=fields, supportsAllDrives=True)
            .execute()
        )
    except HttpError as exc:
        raise classify_transfer_http_error(exc) from exc


def lookup_destination_identity(
    service: Any,
    parent_id: str,
    plan: DestinationPlan,
) -> list[Mapping[str, Any]]:
    safe_parent = _escape_query(parent_id)
    properties = plan.app_properties
    clauses = [
        "appProperties has "
        f"{{ key='{_escape_query(key)}' and "
        f"value='{_escape_query(value)}' }}"
        for key, value in properties.items()
    ]
    query = (
        f"'{safe_parent}' in parents and trashed = false and "
        + " and ".join(clauses)
    )
    response = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields=(
                "files(id,name,mimeType,size,parents,trashed,"
                "appProperties,md5Checksum,webViewLink)"
            ),
            pageSize=2,
        )
        .execute()
    )
    return list(response.get("files") or [])


def verify_destination_metadata(
    metadata: Mapping[str, Any],
    *,
    plan: DestinationPlan,
    expected_parent_id: str,
) -> VerificationLevel:
    if not metadata or not metadata.get("id"):
        raise DestinationConflict("Destination file is missing")
    if metadata.get("trashed") is True:
        raise DestinationConflict("Destination file is trashed")
    if expected_parent_id not in (metadata.get("parents") or []):
        raise DestinationConflict("Destination parent is incorrect")
    size = _integer_or_none(metadata.get("size"))
    if size != plan.expected_bytes:
        raise DestinationConflict("Destination size is incorrect")
    if str(metadata.get("mimeType") or "").lower() != plan.mime_type.lower():
        raise DestinationConflict("Destination MIME type is incorrect")
    if str(metadata.get("name") or "") != plan.filename:
        raise DestinationConflict("Destination filename is incorrect")
    properties = metadata.get("appProperties") or {}
    if any(properties.get(key) != value for key, value in plan.app_properties.items()):
        raise DestinationConflict("Destination application identity is incorrect")
    return VerificationLevel.DESTINATION_METADATA_VERIFIED


def verify_destination_sha256(
    service: Any,
    file_id: str,
    expected_sha256: str,
    *,
    enabled: bool = False,
    profile: DriveCredentialProfile,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    content_reader: Callable[..., Iterable[bytes]] = iter_drive_content,
) -> VerificationLevel:
    if not enabled:
        raise DestinationAccessDenied(
            "Destination SHA-256 verification is disabled by default"
        )
    require_write_profile(profile)
    expected = expected_sha256.lower()
    if not SHA256_PATTERN.fullmatch(expected):
        raise InvalidCanonicalState("Expected destination SHA-256 is invalid")
    digest = hashlib.sha256()
    for chunk in content_reader(service, file_id, chunk_size=chunk_size):
        digest.update(chunk)
    if digest.hexdigest() != expected:
        raise DestinationConflict("Destination SHA-256 does not match source")
    return VerificationLevel.DESTINATION_SHA256_VERIFIED


class SupabaseStep10Repository:
    """Step 10-only persistence adapter; never updates Step 9 tables."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def require_schema(self) -> None:
        self.client.table("asset_destinations").select("id").limit(0).execute()

    def initialize(self, values: Iterable[Mapping[str, Any]]) -> list[dict]:
        payload = [dict(value) for value in values]
        if not payload:
            return []
        response = (
            self.client.table("asset_destinations")
            .upsert(
                payload,
                on_conflict="asset_id,destination_folder_id",
                ignore_duplicates=True,
            )
            .execute()
        )
        return list(response.data or [])

    def claim_batch(
        self,
        worker_id: str,
        limit: int,
        lease_seconds: int,
        allowed_ids: Iterable[str] | None = None,
        destination_folder_id: str | None = None,
    ) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("claim limit must be between 1 and 100")
        normalized_ids = (
            None
            if allowed_ids is None
            else [str(UUID(value)) for value in allowed_ids]
        )
        response = self.client.rpc(
            "claim_asset_destinations",
            {
                "requested_claim_owner": worker_id,
                "requested_limit": limit,
                "requested_lease_seconds": lease_seconds,
                "requested_asset_destination_ids": normalized_ids,
                "requested_destination_folder_id": (
                    _optional_text(destination_folder_id)
                ),
            },
        ).execute()
        return list(response.data or [])

    def renew(self, record_id: str, worker_id: str, lease_seconds: int) -> bool:
        response = self.client.rpc(
            "renew_asset_destination_claim",
            {
                "requested_asset_destination_id": record_id,
                "requested_claim_owner": worker_id,
                "requested_lease_seconds": lease_seconds,
            },
        ).execute()
        return bool(response.data)

    def release(self, record_id: str, worker_id: str) -> bool:
        response = self.client.rpc(
            "release_asset_destination_claim",
            {
                "requested_asset_destination_id": record_id,
                "requested_claim_owner": worker_id,
            },
        ).execute()
        return bool(response.data)

    def mark_started(
        self,
        record_id: str,
        worker_id: str,
        source_snapshot: Mapping[str, Any],
    ) -> bool:
        response = (
            self.client.table("asset_destinations")
            .update(
                {
                    "upload_status": "UPLOADING",
                    "upload_started_at": _utc_now(),
                    "source_metadata_snapshot": dict(source_snapshot),
                }
            )
            .eq("id", record_id)
            .eq("claim_owner", worker_id)
            .eq("upload_status", "CLAIMED")
            .execute()
        )
        return len(response.data or []) == 1

    def complete_upload(
        self,
        record_id: str,
        worker_id: str,
        destination_file_id: str,
        transferred_bytes: int,
        destination_snapshot: Mapping[str, Any],
        verification_level: VerificationLevel,
    ) -> bool:
        response = (
            self.client.table("asset_destinations")
            .update(
                {
                    "upload_status": "VERIFIED",
                    "verification_level": verification_level.value,
                    "destination_google_file_id": destination_file_id,
                    "destination_url": destination_snapshot.get(
                        "webViewLink"
                    ),
                    "transferred_bytes": transferred_bytes,
                    "destination_reported_bytes": _integer_or_none(
                        destination_snapshot.get("size")
                    ),
                    "destination_metadata_snapshot": dict(
                        destination_snapshot
                    ),
                    "provider_checksum_type": (
                        "MD5"
                        if destination_snapshot.get("md5Checksum")
                        else None
                    ),
                    "provider_checksum_value": destination_snapshot.get(
                        "md5Checksum"
                    ),
                    "upload_completed_at": _utc_now(),
                    "verified_at": _utc_now(),
                    "retryable": False,
                    "next_retry_at": None,
                    "failure_code": None,
                    "failure_reason": None,
                    "claim_owner": None,
                    "claim_started_at": None,
                    "claim_expires_at": None,
                    "claim_renewed_at": None,
                }
            )
            .eq("id", record_id)
            .eq("claim_owner", worker_id)
            .in_("upload_status", ["CLAIMED", "UPLOADING"])
            .execute()
        )
        return len(response.data or []) == 1

    def set_verification_level(
        self,
        record_id: str,
        destination_file_id: str,
        verification_level: VerificationLevel,
    ) -> bool:
        """Promote one completed destination after enhanced verification."""
        response = (
            self.client.table("asset_destinations")
            .update({"verification_level": verification_level.value})
            .eq("id", record_id)
            .eq("destination_google_file_id", destination_file_id)
            .eq("upload_status", "VERIFIED")
            .execute()
        )
        return len(response.data or []) == 1

    def recover_unchanged_source(
        self,
        record_id: str,
        source_file_id: str,
    ) -> bool:
        """Queue one false-positive SOURCE_CHANGED row without resetting history."""
        response = (
            self.client.table("asset_destinations")
            .update(
                {
                    "upload_status": "QUEUED",
                    "retryable": False,
                    "next_retry_at": None,
                    "failure_code": None,
                    "failure_reason": None,
                }
            )
            .eq("id", record_id)
            .eq("selected_source_file_id", source_file_id)
            .eq("upload_status", "SOURCE_CHANGED")
            .is_("destination_google_file_id", "null")
            .is_("claim_owner", "null")
            .is_("claim_expires_at", "null")
            .is_("next_retry_at", "null")
            .execute()
        )
        return len(response.data or []) == 1

    def fail(
        self,
        record_id: str,
        worker_id: str,
        error: Step10Error,
        *,
        retry_delay_seconds: float = 1.0,
    ) -> bool:
        response = (
            self.client.table("asset_destinations")
            .update(
                {
                    "upload_status": (
                        "FAILED_RETRYABLE"
                        if error.retryable
                        else error.code
                        if error.code in UploadStatus._value2member_map_
                        else "FAILED_PERMANENT"
                    ),
                    "retryable": error.retryable,
                    "next_retry_at": (
                        _utc_after(retry_delay_seconds)
                        if error.retryable
                        else None
                    ),
                    "failure_code": error.code,
                    "failure_reason": _sanitize_text(str(error)),
                    "claim_owner": None,
                    "claim_started_at": None,
                    "claim_expires_at": None,
                    "claim_renewed_at": None,
                }
            )
            .eq("id", record_id)
            .eq("claim_owner", worker_id)
            .execute()
        )
        return len(response.data or []) == 1

    def append_event(self, values: Mapping[str, Any]) -> None:
        safe = dict(values)
        safe["details"] = sanitize_event_details(safe.get("details") or {})
        self.client.table("migration_events").insert(safe).execute()


def retry_delay(
    attempt: int,
    *,
    retry_after: float | None = None,
    delays: tuple[float, ...] = DEFAULT_RETRY_DELAYS,
    jitter: Callable[[], float] = random.random,
) -> float:
    if attempt < 1 or attempt > len(delays):
        raise PermanentTransferError("Retry attempts are exhausted")
    base = max(delays[attempt - 1], retry_after or 0.0)
    return base + min(1.0, max(0.0, jitter()))


def run_with_retry(
    operation: Callable[[], Any],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except RetryableTransferError:
            if attempt >= max_attempts:
                raise
            sleep(retry_delay(attempt))
    raise PermanentTransferError("Retry loop ended unexpectedly")


def classify_transfer_http_error(exc: HttpError) -> Step10Error:
    status = getattr(exc.resp, "status", None)
    if status in {429, 500, 502, 503, 504}:
        return RetryableTransferError(f"Drive HTTP {status}")
    if status in {401, 403}:
        return DestinationAccessDenied("Destination access is denied")
    return PermanentTransferError(f"Drive HTTP {status or 'unknown'}")


def sanitize_event_details(details: Mapping[str, Any]) -> dict[str, Any]:
    prohibited = {
        "access_token", "refresh_token", "authorization", "client_secret",
        "password", "signed_url", "connection_string",
    }
    result: dict[str, Any] = {}
    for key, value in details.items():
        if key.casefold() in prohibited:
            continue
        if isinstance(value, Mapping):
            result[str(key)] = sanitize_event_details(value)
        else:
            result[str(key)] = _sanitize_text(str(value)) if value is not None else None
    return result


AUDIT_EVENT_TYPES = (
    "LIFECYCLE_INITIALIZED",
    "UPLOAD_QUEUED",
    "UPLOAD_CLAIMED",
    "CLAIM_RENEWED",
    "CLAIM_RELEASED",
    "CLAIM_RECOVERED",
    "UPLOAD_STARTED",
    "UPLOAD_CREATED",
    "UPLOAD_RECOVERED",
    "UPLOAD_VERIFIED",
    "UPLOAD_FAILED",
    "UPLOAD_RETRY_SCHEDULED",
    "SOURCE_CHANGED",
    "SOURCE_NOT_FOUND",
    "SOURCE_ACCESS_DENIED",
    "DESTINATION_ACCESS_DENIED",
    "DESTINATION_CONFLICT",
    "MANUAL_REVIEW_REQUIRED",
)


def _source_row_is_valid(row: Mapping[str, Any], asset_hash: str) -> bool:
    extension = str(row.get("file_extension") or "").lower().lstrip(".")
    mime_type = str(row.get("mime_type") or "").lower()
    policy = FORMAT_POLICY.get(extension)
    return bool(
        row.get("decision") == "TAKE"
        and row.get("processing_status") == "READY"
        and row.get("hash_status") == "HASHED"
        and row.get("hash_algorithm") == "SHA-256"
        and str(row.get("content_sha256") or "").lower() == asset_hash
        and row.get("trashed") is not True
        and row.get("is_missing") is not True
        and row.get("access_status") not in {"INACCESSIBLE", "ERROR"}
        and row.get("google_file_id")
        and isinstance(row.get("size_bytes"), int)
        and row.get("size_bytes") >= 0
        and policy is not None
        and policy.accepted_for_migration
        and policy.required_mime_type == mime_type
    )


def _source_from_row(row: Mapping[str, Any], asset_hash: str) -> SelectedSource:
    return SelectedSource(
        id=_required_text("source_file.id", row.get("id")),
        source_folder_id=_required_text(
            "source_folder_id", row.get("source_folder_id")
        ),
        google_file_id=_required_text(
            "google_file_id", row.get("google_file_id")
        ),
        file_name=_required_text("file_name", row.get("file_name")),
        mime_type=str(row.get("mime_type")).lower(),
        file_extension=str(row.get("file_extension")).lower().lstrip("."),
        size_bytes=int(row.get("size_bytes")),
        content_sha256=asset_hash,
        drive_modified_at=_optional_text(
            row.get("hash_drive_modified_at")
            or row.get("drive_modified_at")
        ),
        drive_version=_optional_text(row.get("hash_drive_version")),
        hash_status=str(row.get("hash_status") or ""),
        hash_completed_at=_optional_text(row.get("hash_completed_at")),
    )


def _sanitized_stem(name: str, extension: str) -> str:
    normalized = unicodedata.normalize("NFC", name).strip()
    suffix = f".{extension}".casefold()
    if normalized.casefold().endswith(suffix):
        normalized = normalized[: -len(suffix)]
    normalized = re.sub(r"[\x00-\x1f/\\]+", "-", normalized)
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"[-_.]{2,}", "-", normalized).strip(" ._-")
    if normalized.casefold() in WINDOWS_RESERVED:
        return ""
    return normalized


def _looks_sensitive(stem: str) -> bool:
    if not stem:
        return True
    lowered = stem.casefold()
    return bool(
        "@" in stem
        or re.search(r"\b(?:patient|mrn|dob|mobile|phone|email)\b", lowered)
        or re.search(r"\d{7,}", stem)
    )


def _required_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidCanonicalState(f"{name} must be non-empty")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _normalized_drive_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _integer_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _sanitize_text(value: str) -> str:
    value = re.sub(
        r"(?i)(bearer|access_token|refresh_token|client_secret|password)"
        r"\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        value,
    )
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())[:500]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_after(seconds: float) -> str:
    if seconds < 0:
        raise ValueError("retry delay must be non-negative")
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
