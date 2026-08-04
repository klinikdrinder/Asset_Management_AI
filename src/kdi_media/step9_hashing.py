"""Step 9 complete-file SHA-256 hashing primitives.

The module does not create assets, group duplicates, or copy Drive files.
Network and database effects are injected so tests remain local and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import StrEnum
import hashlib
import io
import random
import re
import time
from typing import Any, Callable, Iterable, Mapping, Protocol

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
DEFAULT_RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 16.0)
GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."
GOOGLE_SHORTCUT_MIME = "application/vnd.google-apps.shortcut"


class HashStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    QUEUED = "QUEUED"
    HASHING = "HASHING"
    HASHED = "HASHED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SOURCE_ACCESS_DENIED = "SOURCE_ACCESS_DENIED"
    SOURCE_TRASHED = "SOURCE_TRASHED"


class Step9HashingError(RuntimeError):
    code = "HASHING_ERROR"
    retryable = False


class RetryableHashingError(Step9HashingError):
    code = "DRIVE_RETRYABLE"
    retryable = True


class RateLimitedHashingError(RetryableHashingError):
    code = "DRIVE_RATE_LIMITED"


class PermanentHashingError(Step9HashingError):
    code = "DRIVE_PERMANENT"


class PartialDownloadError(RetryableHashingError):
    code = "PARTIAL_DOWNLOAD"


class SourceChangedError(PermanentHashingError):
    code = "SOURCE_CHANGED"


class SourceNotFoundError(PermanentHashingError):
    code = "SOURCE_NOT_FOUND"


class SourceAccessDeniedError(PermanentHashingError):
    code = "SOURCE_ACCESS_DENIED"


class SourceTrashedError(PermanentHashingError):
    code = "SOURCE_TRASHED"


@dataclass(frozen=True)
class SourceSnapshot:
    file_id: str
    mime_type: str
    size_bytes: int | None
    modified_time: str | None
    version: str | None = None
    revision: str | None = None
    trashed: bool = False
    can_download: bool | None = None
    provider_md5: str | None = None

    @classmethod
    def from_drive(cls, value: Mapping[str, Any]) -> "SourceSnapshot":
        raw_size = value.get("size")
        try:
            size = int(raw_size) if raw_size is not None else None
        except (TypeError, ValueError) as exc:
            raise PermanentHashingError("Drive returned invalid size metadata") from exc
        capabilities = value.get("capabilities") or {}
        return cls(
            file_id=str(value.get("id") or ""),
            mime_type=str(value.get("mimeType") or "").strip().lower(),
            size_bytes=size,
            modified_time=_optional_text(value.get("modifiedTime")),
            version=_optional_text(value.get("version")),
            revision=_optional_text(value.get("headRevisionId")),
            trashed=value.get("trashed") is True,
            can_download=capabilities.get("canDownload"),
            provider_md5=_optional_text(value.get("md5Checksum")),
        )

    def sanitized_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "modified_time": self.modified_time,
            "version": self.version,
            "revision": self.revision,
            "trashed": self.trashed,
            "can_download": self.can_download,
            "provider_md5": self.provider_md5,
        }


@dataclass(frozen=True)
class HashResult:
    algorithm: str
    content_sha256: str
    observed_bytes: int
    expected_bytes: int | None
    snapshot: SourceSnapshot

    def __post_init__(self) -> None:
        if self.algorithm != "SHA-256" or not SHA256_PATTERN.fullmatch(
            self.content_sha256
        ):
            raise ValueError("Invalid SHA-256 result")


@dataclass(frozen=True)
class FailureInfo:
    status: HashStatus
    code: str
    reason: str
    retryable: bool


class HashRepository(Protocol):
    def claim(
        self, source_file_id: str, claim_owner: str, lease_seconds: int
    ) -> Mapping[str, Any] | None: ...

    def complete(
        self, source_file_id: str, claim_owner: str, result: HashResult
    ) -> bool: ...

    def record_retry_attempt(
        self, source_file_id: str, claim_owner: str
    ) -> bool: ...

    def renew(
        self, source_file_id: str, claim_owner: str, lease_seconds: int
    ) -> bool: ...

    def fail(
        self, source_file_id: str, claim_owner: str, failure: FailureInfo
    ) -> bool: ...


def iter_drive_content(
    service: Any,
    file_id: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    downloader_factory: Callable[..., Any] = MediaIoBaseDownload,
) -> Iterable[bytes]:
    """Yield bounded chunks from an ordinary downloadable Drive file."""
    if not file_id.strip():
        raise ValueError("file_id must be non-empty")
    if chunk_size < 256 * 1024:
        raise ValueError("chunk_size must be at least 256 KiB")
    sink = io.BytesIO()
    try:
        request = service.files().get_media(fileId=file_id)
        downloader = downloader_factory(sink, request, chunksize=chunk_size)
        done = False
        while not done:
            try:
                _, done = downloader.next_chunk(num_retries=0)
            except HttpError as exc:
                raise classify_http_error(exc) from exc
            data = sink.getvalue()
            sink.seek(0)
            sink.truncate(0)
            if data:
                yield data
    finally:
        sink.close()


def read_drive_snapshot(service: Any, file_id: str) -> SourceSnapshot:
    """Read sanitized metadata required immediately before/after hashing."""
    fields = (
        "id,mimeType,size,modifiedTime,version,headRevisionId,trashed,"
        "capabilities(canDownload),md5Checksum"
    )
    try:
        value = (
            service.files()
            .get(fileId=file_id, fields=fields, supportsAllDrives=True)
            .execute()
        )
    except HttpError as exc:
        raise classify_http_error(exc) from exc
    return SourceSnapshot.from_drive(value)


def hash_chunks(
    chunks: Iterable[bytes], *, expected_bytes: int | None
) -> tuple[str, int]:
    digest = hashlib.sha256()
    observed = 0
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise PermanentHashingError("Content stream returned a non-byte chunk")
        digest.update(chunk)
        observed += len(chunk)
    if expected_bytes is not None and observed != expected_bytes:
        raise PartialDownloadError(
            f"Received byte count did not match expected size ({observed}/{expected_bytes})"
        )
    return digest.hexdigest(), observed


def compare_snapshots(
    inventory: SourceSnapshot, current: SourceSnapshot
) -> None:
    if current.trashed:
        raise SourceTrashedError("Source file is trashed")
    if current.can_download is False:
        raise SourceAccessDeniedError("Source file cannot be downloaded")
    if current.mime_type.startswith(GOOGLE_NATIVE_PREFIX):
        raise PermanentHashingError("Google-native files are not export-hashed")
    for label, before, after in (
        ("file ID", inventory.file_id, current.file_id),
        ("MIME type", inventory.mime_type, current.mime_type),
        ("size", inventory.size_bytes, current.size_bytes),
        ("version", inventory.version, current.version),
        ("revision", inventory.revision, current.revision),
    ):
        if before is not None and after is not None and before != after:
            raise SourceChangedError(f"Source {label} changed")
    if (
        inventory.modified_time is not None
        and current.modified_time is not None
        and _normalized_timestamp(inventory.modified_time)
        != _normalized_timestamp(current.modified_time)
    ):
        raise SourceChangedError("Source modified time changed")


def hash_drive_file(
    service: Any,
    inventory: SourceSnapshot,
    metadata_reader: Callable[[Any, str], SourceSnapshot],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    content_reader: Callable[..., Iterable[bytes]] = iter_drive_content,
) -> HashResult:
    before = metadata_reader(service, inventory.file_id)
    compare_snapshots(inventory, before)
    digest, observed = hash_chunks(
        content_reader(service, inventory.file_id, chunk_size=chunk_size),
        expected_bytes=before.size_bytes,
    )
    after = metadata_reader(service, inventory.file_id)
    compare_snapshots(before, after)
    return HashResult("SHA-256", digest, observed, before.size_bytes, after)


class Step9HashWorker:
    def __init__(
        self,
        repository: HashRepository,
        service: Any,
        metadata_reader: Callable[[Any, str], SourceSnapshot],
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        retry_delays: tuple[float, ...] = DEFAULT_RETRY_DELAYS,
        jitter: Callable[[], float] = random.random,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        lease_renewal_interval: float = 60.0,
        event_observer: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> None:
        self.repository = repository
        self.service = service
        self.metadata_reader = metadata_reader
        self.chunk_size = chunk_size
        self.retry_delays = retry_delays
        self.jitter = jitter
        self.sleeper = sleeper
        self.monotonic = monotonic
        self.lease_renewal_interval = lease_renewal_interval
        self.event_observer = event_observer or (lambda _event, _details: None)

    def process(
        self,
        source_file_id: str,
        claim_owner: str,
        inventory: SourceSnapshot,
        *,
        lease_seconds: int = 900,
        content_reader: Callable[..., Iterable[bytes]] = iter_drive_content,
    ) -> HashResult | None:
        claimed = self.repository.claim(
            source_file_id, claim_owner, lease_seconds
        )
        if claimed is None:
            return None
        for attempt in range(len(self.retry_delays) + 1):
            try:
                if attempt and not self.repository.record_retry_attempt(
                    source_file_id, claim_owner
                ):
                    raise PermanentHashingError(
                        "Hash claim was lost before retry"
                    )
                last_renewed = self.monotonic()

                def leased_content(
                    service: Any,
                    file_id: str,
                    *,
                    chunk_size: int,
                ) -> Iterable[bytes]:
                    nonlocal last_renewed
                    for chunk in content_reader(
                        service, file_id, chunk_size=chunk_size
                    ):
                        now = self.monotonic()
                        if now - last_renewed >= self.lease_renewal_interval:
                            if not self.repository.renew(
                                source_file_id, claim_owner, lease_seconds
                            ):
                                raise PermanentHashingError(
                                    "Hash claim expired during streaming"
                                )
                            last_renewed = now
                        yield chunk

                result = hash_drive_file(
                    self.service,
                    inventory,
                    self.metadata_reader,
                    chunk_size=self.chunk_size,
                    content_reader=leased_content,
                )
                if not self.repository.complete(
                    source_file_id, claim_owner, result
                ):
                    raise PermanentHashingError("Hash claim was lost before completion")
                return result
            except Step9HashingError as exc:
                if exc.retryable and attempt < len(self.retry_delays):
                    self.event_observer(
                        "retry",
                        {
                            "attempt": attempt + 1,
                            "failure_code": exc.code,
                            "retry_after_seconds": getattr(
                                exc, "retry_after_seconds", None
                            ),
                        },
                    )
                    delay = self.retry_delays[attempt] * (1 + self.jitter())
                    retry_after = getattr(exc, "retry_after_seconds", None)
                    if isinstance(retry_after, (int, float)):
                        delay = max(delay, float(retry_after))
                    self.sleeper(delay)
                    continue
                failure = failure_info(exc)
                self.repository.fail(source_file_id, claim_owner, failure)
                return None
        raise AssertionError("unreachable")


class SupabaseHashRepository:
    """Supabase REST/RPC adapter; all writes are confined to hash-owned fields."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def claim(
        self, source_file_id: str, claim_owner: str, lease_seconds: int
    ) -> Mapping[str, Any] | None:
        response = self.client.rpc(
            "claim_source_file_hash",
            {
                "requested_source_file_id": source_file_id,
                "requested_claim_owner": claim_owner,
                "requested_lease_seconds": lease_seconds,
            },
        ).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def complete(
        self, source_file_id: str, claim_owner: str, result: HashResult
    ) -> bool:
        values = {
            "hash_algorithm": result.algorithm,
            "content_sha256": result.content_sha256,
            "hash_status": HashStatus.HASHED.value,
            "hash_expected_bytes": result.expected_bytes,
            "hash_observed_bytes": result.observed_bytes,
            "hash_completed_at": datetime.now(timezone.utc).isoformat(),
            "hash_failure_code": None,
            "hash_failure_reason": None,
            "hash_retryable": False,
            "hash_source_snapshot": result.snapshot.sanitized_dict(),
            "hash_drive_modified_at": result.snapshot.modified_time,
            "hash_drive_size": result.snapshot.size_bytes,
            "hash_drive_mime_type": result.snapshot.mime_type,
            "hash_drive_version": result.snapshot.version or result.snapshot.revision,
            "hash_claim_owner": None,
            "hash_claimed_at": None,
            "hash_claim_expires_at": None,
        }
        response = (
            self.client.table("source_files")
            .update(values)
            .eq("id", source_file_id)
            .eq("hash_status", HashStatus.HASHING.value)
            .eq("hash_claim_owner", claim_owner)
            .execute()
        )
        return len(response.data or []) == 1

    def refresh_unchanged_snapshot(
        self,
        source_file_id: str,
        expected_sha256: str,
        result: HashResult,
    ) -> bool:
        """Refresh hash-owned metadata after a full unchanged-content rehash."""
        if result.content_sha256 != expected_sha256:
            raise ValueError("Unchanged snapshot refresh requires matching SHA-256")
        response = (
            self.client.table("source_files")
            .update(
                {
                    "hash_source_snapshot": result.snapshot.sanitized_dict(),
                    "hash_drive_modified_at": result.snapshot.modified_time,
                    "hash_drive_size": result.snapshot.size_bytes,
                    "hash_drive_mime_type": result.snapshot.mime_type,
                    "hash_drive_version": (
                        result.snapshot.version or result.snapshot.revision
                    ),
                    "hash_expected_bytes": result.expected_bytes,
                    "hash_observed_bytes": result.observed_bytes,
                    "hash_failure_code": None,
                    "hash_failure_reason": None,
                    "hash_retryable": False,
                }
            )
            .eq("id", source_file_id)
            .eq("hash_status", HashStatus.HASHED.value)
            .eq("hash_algorithm", "SHA-256")
            .eq("content_sha256", expected_sha256)
            .is_("hash_claim_owner", "null")
            .execute()
        )
        return len(response.data or []) == 1

    def record_retry_attempt(
        self, source_file_id: str, claim_owner: str
    ) -> bool:
        current = (
            self.client.table("source_files")
            .select("hash_attempt_count")
            .eq("id", source_file_id)
            .eq("hash_status", HashStatus.HASHING.value)
            .eq("hash_claim_owner", claim_owner)
            .limit(1)
            .execute()
        )
        rows = current.data or []
        if len(rows) != 1:
            return False
        response = (
            self.client.table("source_files")
            .update(
                {
                    "hash_attempt_count": int(rows[0]["hash_attempt_count"]) + 1,
                    "hash_last_attempt_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", source_file_id)
            .eq("hash_status", HashStatus.HASHING.value)
            .eq("hash_claim_owner", claim_owner)
            .eq("hash_attempt_count", rows[0]["hash_attempt_count"])
            .execute()
        )
        return len(response.data or []) == 1

    def renew(
        self, source_file_id: str, claim_owner: str, lease_seconds: int
    ) -> bool:
        response = self.client.rpc(
            "renew_source_file_hash_claim",
            {
                "requested_source_file_id": source_file_id,
                "requested_claim_owner": claim_owner,
                "requested_lease_seconds": lease_seconds,
            },
        ).execute()
        return response.data is True

    def fail(
        self, source_file_id: str, claim_owner: str, failure: FailureInfo
    ) -> bool:
        response = (
            self.client.table("source_files")
            .update(
                {
                    "hash_status": failure.status.value,
                    "hash_failure_code": failure.code,
                    "hash_failure_reason": failure.reason,
                    "hash_retryable": failure.retryable,
                    "hash_claim_owner": None,
                    "hash_claimed_at": None,
                    "hash_claim_expires_at": None,
                }
            )
            .eq("id", source_file_id)
            .eq("hash_status", HashStatus.HASHING.value)
            .eq("hash_claim_owner", claim_owner)
            .execute()
        )
        return len(response.data or []) == 1


def classify_http_error(exc: HttpError) -> Step9HashingError:
    status = getattr(exc.resp, "status", None)
    if status == 404:
        return SourceNotFoundError("Google Drive source was not found")
    if status in {401, 403}:
        return SourceAccessDeniedError("Google Drive source access was denied")
    if status == 429 or (isinstance(status, int) and status >= 500):
        error = (
            RateLimitedHashingError("Google Drive rate limit persisted")
            if status == 429
            else RetryableHashingError("Transient Google Drive request failure")
        )
        retry_after = _retry_after_seconds(exc)
        if retry_after is not None:
            setattr(error, "retry_after_seconds", retry_after)
        return error
    return PermanentHashingError("Permanent Google Drive request failure")


def failure_info(exc: Step9HashingError) -> FailureInfo:
    if isinstance(exc, SourceChangedError):
        status = HashStatus.SOURCE_CHANGED
    elif isinstance(exc, SourceNotFoundError):
        status = HashStatus.SOURCE_NOT_FOUND
    elif isinstance(exc, SourceAccessDeniedError):
        status = HashStatus.SOURCE_ACCESS_DENIED
    elif isinstance(exc, SourceTrashedError):
        status = HashStatus.SOURCE_TRASHED
    else:
        status = (
            HashStatus.FAILED_RETRYABLE
            if exc.retryable
            else HashStatus.FAILED_PERMANENT
        )
    return FailureInfo(status, exc.code, _sanitize_reason(str(exc)), exc.retryable)


def _retry_after_seconds(exc: HttpError) -> float | None:
    value = getattr(exc.resp, "get", lambda _key: None)("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
            return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None


def _sanitize_reason(value: str) -> str:
    clean = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return clean[:500]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PermanentHashingError(
            "Source metadata contained an invalid timestamp"
        ) from exc
