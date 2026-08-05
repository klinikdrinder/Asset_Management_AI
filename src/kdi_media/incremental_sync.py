"""Pure Step 14 incremental-sync controls."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
import random
import re
import time
from typing import Any, Callable, Iterable, Mapping


class FileClassification(StrEnum):
    NEW = "NEW"
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    INACCESSIBLE = "INACCESSIBLE"
    REMOVED_FROM_SOURCE = "REMOVED_FROM_SOURCE"


TRUSTED_COMPLETE_STATES = frozenset({"HASHED", "DUPLICATE", "UPLOADED", "VERIFIED"})
RECONCILIATION_OUTCOMES = frozenset({
    "UNCHANGED", "SKIPPED", "LINKED_DUPLICATE", "UPLOADED_VERIFIED",
    "FAILED", "AWAITING_RETRY", "INACCESSIBLE", "REMOVED_FROM_SOURCE",
})
SECRET_PATTERN = re.compile(
    r"(?i)(access[_ -]?token|refresh[_ -]?token|service[_ -]?role|password|authorization)\s*[:=]\s*\S+"
)


@dataclass(frozen=True)
class DriveMetadata:
    google_file_id: str
    modified_time: str | None
    size_bytes: int | None
    mime_type: str | None
    md5_checksum: str | None = None
    accessible: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DriveMetadata":
        raw_size = value.get("size_bytes", value.get("size"))
        return cls(
            google_file_id=str(value.get("google_file_id", value.get("id")) or ""),
            modified_time=value.get("drive_modified_at", value.get("modifiedTime")),
            size_bytes=int(raw_size) if raw_size is not None else None,
            mime_type=value.get("mime_type", value.get("mimeType")),
            md5_checksum=value.get("md5_checksum", value.get("md5Checksum")),
            accessible=bool(value.get("accessible", True)),
        )


def classify_file(current: DriveMetadata, stored: Mapping[str, Any] | None) -> FileClassification:
    """Classify from stable Drive identity and cheap metadata only."""
    if not current.accessible or not current.google_file_id:
        return FileClassification.INACCESSIBLE
    if stored is None:
        return FileClassification.NEW
    if bool(stored.get("is_missing")):
        return FileClassification.CHANGED
    comparisons = (
        ("drive_modified_at", current.modified_time),
        ("size_bytes", current.size_bytes),
        ("mime_type", current.mime_type),
        ("md5_checksum", current.md5_checksum),
    )
    for key, value in comparisons:
        previous = stored.get(key)
        if key == "drive_modified_at":
            previous = _normalized_instant(previous)
            value = _normalized_instant(value)
        if key == "md5_checksum" and (previous is None or value is None):
            continue
        if previous != value:
            return FileClassification.CHANGED
    return FileClassification.UNCHANGED


def _normalized_instant(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        return parsed.isoformat()
    return parsed.astimezone(timezone.utc).isoformat()


def classify_inventory(discovered: Iterable[DriveMetadata], stored_rows: Iterable[Mapping[str, Any]]) -> dict[str, FileClassification]:
    stored = {str(row["google_file_id"]): row for row in stored_rows}
    results = {item.google_file_id: classify_file(item, stored.get(item.google_file_id)) for item in discovered}
    for file_id in stored.keys() - results.keys():
        results[file_id] = FileClassification.REMOVED_FROM_SOURCE
    return results


def trusted_unchanged_checksum(current: DriveMetadata, stored: Mapping[str, Any]) -> bool:
    return (
        classify_file(current, stored) is FileClassification.UNCHANGED
        and str(stored.get("hash_status") or stored.get("processing_status") or "") in TRUSTED_COMPLETE_STATES
        and bool(stored.get("content_sha256") or stored.get("destination_file_id"))
    )


@dataclass
class RunTotals:
    sources_checked: int = 0
    files_discovered: int = 0
    new_files_detected: int = 0
    changed_files_detected: int = 0
    unchanged_files_ignored: int = 0
    files_skipped: int = 0
    files_hashed: int = 0
    exact_duplicates_found: int = 0
    unique_files_uploaded: int = 0
    existing_assets_reused: int = 0
    failed_files: int = 0
    retried_files: int = 0
    unresolved_exceptions: int = 0
    removed_from_source: int = 0
    inaccessible: int = 0


@dataclass(frozen=True)
class FileOutcome:
    source_file_id: str
    outcome: str
    reason: str | None = None


def reconcile(discovered_relevant: int, outcomes: Iterable[FileOutcome]) -> dict[str, Any]:
    values = tuple(outcomes)
    invalid = [item.source_file_id for item in values if item.outcome not in RECONCILIATION_OUTCOMES]
    duplicate_ids = len({item.source_file_id for item in values}) != len(values)
    unresolved = sum(item.outcome in {"FAILED", "AWAITING_RETRY", "INACCESSIBLE"} for item in values)
    clean = not invalid and not duplicate_ids and len(values) == discovered_relevant and unresolved == 0
    return {"clean": clean, "expected_outcomes": discovered_relevant, "recorded_outcomes": len(values), "unresolved": unresolved, "invalid_outcome_ids": invalid, "duplicate_outcome_ids": duplicate_ids, "counts": dict(Counter(item.outcome for item in values)), "status": "RECONCILED" if clean else "CONTRADICTION_OR_EXCEPTION"}


class RetryableSyncError(RuntimeError):
    pass


def bounded_retry(operation: Callable[[], Any], *, max_attempts: int = 5, delays: tuple[float, ...] = (1, 2, 4, 8), sleeper: Callable[[float], None] = time.sleep, jitter: Callable[[], float] = random.random, on_retry: Callable[[int, str], None] | None = None) -> Any:
    if max_attempts < 1 or len(delays) < max_attempts - 1:
        raise ValueError("retry configuration is incomplete")
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except RetryableSyncError as exc:
            if attempt == max_attempts:
                raise
            if on_retry:
                on_retry(attempt, sanitize_error(exc))
            sleeper(delays[attempt - 1] + min(1.0, max(0.0, jitter())))
    raise AssertionError("unreachable")


def sanitize_error(error: BaseException) -> str:
    text = " ".join(str(error).replace("\r", " ").replace("\n", " ").split())
    return SECRET_PATTERN.sub(r"\1=[REDACTED]", text)[:500]


def write_json_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def totals_dict(totals: RunTotals) -> dict[str, int]:
    return asdict(totals)
