"""Parse, validate, and map a Step 6 recursive inventory report.

This module is deliberately local-only.  It has no Supabase or Google Drive
dependencies and performs no network operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
import csv
import hashlib
import json


FOLDER_CLASSIFICATION = "folder"
SUPPORTED_FILE_CLASSIFICATION = "supported_file"
UNSUPPORTED_FILE_CLASSIFICATION = "unsupported_file"
INACCESSIBLE_ITEM_CLASSIFICATION = "inaccessible_item"
ALLOWED_CLASSIFICATIONS = frozenset(
    {
        FOLDER_CLASSIFICATION,
        SUPPORTED_FILE_CLASSIFICATION,
        UNSUPPORTED_FILE_CLASSIFICATION,
        INACCESSIBLE_ITEM_CLASSIFICATION,
    }
)
ALLOWED_ACCESSIBILITY_STATUSES = frozenset({"accessible", "inaccessible"})

EXPECTED_ROOT_KEYS = frozenset({"file_id", "name", "mime_type"})
EXPECTED_SUMMARY_KEYS = frozenset(
    {
        "folders_scanned",
        "total_items_discovered",
        "total_files_found",
        "supported_files",
        "unsupported_files",
        "inaccessible_items",
        "errors",
        "api_pages_requested",
    }
)
ITEM_FIELDS = (
    "file_id",
    "name",
    "mime_type",
    "file_extension",
    "size",
    "created_time",
    "modified_time",
    "parent_folder_id",
    "relative_folder_path",
    "web_view_link",
    "accessibility_status",
    "classification",
)
EXPECTED_ITEM_KEYS = frozenset(ITEM_FIELDS)
EXPECTED_ERROR_KEYS = frozenset(
    {"item_id", "failure_category", "http_status", "message"}
)
EXPECTED_TOP_LEVEL_KEYS = frozenset(
    {"generated_at_utc", "root", "summary", "items", "errors"}
)


class Step6InventoryValidationError(ValueError):
    """A safe validation failure that does not include report contents."""


@dataclass(frozen=True)
class Step6Root:
    file_id: str
    name: str
    mime_type: str


@dataclass(frozen=True)
class Step6Summary:
    folders_scanned: int
    total_items_discovered: int
    total_files_found: int
    supported_files: int
    unsupported_files: int
    inaccessible_items: int
    errors: int
    api_pages_requested: int


@dataclass(frozen=True)
class Step6Item:
    file_id: str
    name: str
    mime_type: str
    file_extension: str | None
    size: int | None
    created_time: str | None
    modified_time: str | None
    parent_folder_id: str
    relative_folder_path: str
    web_view_link: str | None
    accessibility_status: str
    classification: str


@dataclass(frozen=True)
class Step6Error:
    item_id: str
    failure_category: str
    http_status: int | None
    message: str


@dataclass(frozen=True)
class Step6InventoryReport:
    report_path: Path
    report_sha256: str
    generated_at_utc: str
    root: Step6Root
    summary: Step6Summary
    items: tuple[Step6Item, ...]
    errors: tuple[Step6Error, ...]

    @property
    def folder_items(self) -> tuple[Step6Item, ...]:
        return tuple(
            item
            for item in self.items
            if item.classification == FOLDER_CLASSIFICATION
        )

    @property
    def source_file_items(self) -> tuple[Step6Item, ...]:
        return tuple(
            item
            for item in self.items
            if item.classification != FOLDER_CLASSIFICATION
        )


def calculate_report_sha256(path: str | Path) -> str:
    """Return a stable SHA-256 fingerprint of the exact report bytes."""
    report_path = Path(path)
    digest = hashlib.sha256()
    try:
        with report_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise Step6InventoryValidationError(
            "Step 6 JSON report could not be read"
        ) from exc
    return digest.hexdigest()


def parse_step6_json(
    path: str | Path,
    *,
    expected_root_id: str | None = None,
    expected_root_name: str | None = None,
) -> Step6InventoryReport:
    """Parse and strictly validate a Step 6 JSON inventory report."""
    report_path = Path(path)
    report_sha256 = calculate_report_sha256(report_path)
    try:
        with report_path.open("r", encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Step6InventoryValidationError(
            "Step 6 JSON report is not valid readable JSON"
        ) from exc

    top = _object(raw, "report")
    _exact_keys(top, EXPECTED_TOP_LEVEL_KEYS, "report")
    generated_at = _timestamp(
        top["generated_at_utc"], "generated_at_utc", required=True
    )

    root_raw = _object(top["root"], "root")
    _exact_keys(root_raw, EXPECTED_ROOT_KEYS, "root")
    root = Step6Root(
        file_id=_text(root_raw["file_id"], "root.file_id"),
        name=_text(root_raw["name"], "root.name"),
        mime_type=_text(root_raw["mime_type"], "root.mime_type"),
    )
    validate_root_identity(
        root,
        expected_root_id=expected_root_id,
        expected_root_name=expected_root_name,
    )

    summary_raw = _object(top["summary"], "summary")
    _exact_keys(summary_raw, EXPECTED_SUMMARY_KEYS, "summary")
    summary = Step6Summary(
        **{
            key: _nonnegative_integer(summary_raw[key], f"summary.{key}")
            for key in EXPECTED_SUMMARY_KEYS
        }
    )

    items_raw = _array(top["items"], "items")
    items = tuple(
        _parse_item(value, index) for index, value in enumerate(items_raw)
    )
    errors_raw = _array(top["errors"], "errors")
    errors = tuple(
        _parse_error(value, index) for index, value in enumerate(errors_raw)
    )

    report = Step6InventoryReport(
        report_path=report_path,
        report_sha256=report_sha256,
        generated_at_utc=generated_at,
        root=root,
        summary=summary,
        items=items,
        errors=errors,
    )
    reconcile_report_totals(report)
    return report


def validate_root_identity(
    root: Step6Root,
    *,
    expected_root_id: str | None,
    expected_root_name: str | None,
) -> None:
    """Validate the root without echoing an unexpected report value."""
    if expected_root_id is not None and root.file_id != expected_root_id:
        raise Step6InventoryValidationError(
            "Step 6 root folder ID does not match the approved folder"
        )
    if expected_root_name is not None and root.name != expected_root_name:
        raise Step6InventoryValidationError(
            "Step 6 root folder name does not match the approved folder"
        )


def reconcile_report_totals(report: Step6InventoryReport) -> None:
    """Reconcile every reported summary count against parsed records."""
    counts = {
        classification: sum(
            item.classification == classification for item in report.items
        )
        for classification in ALLOWED_CLASSIFICATIONS
    }
    folder_count = counts[FOLDER_CLASSIFICATION]
    supported_count = counts[SUPPORTED_FILE_CLASSIFICATION]
    unsupported_count = counts[UNSUPPORTED_FILE_CLASSIFICATION]
    inaccessible_count = counts[INACCESSIBLE_ITEM_CLASSIFICATION]
    file_count = supported_count + unsupported_count + inaccessible_count
    expected = {
        "total_items_discovered": len(report.items),
        "total_files_found": file_count,
        "supported_files": supported_count,
        "unsupported_files": unsupported_count,
        "inaccessible_items": inaccessible_count,
        "errors": len(report.errors),
    }
    for field, actual in expected.items():
        if getattr(report.summary, field) != actual:
            raise Step6InventoryValidationError(
                f"Step 6 summary field {field} does not match item records"
            )
    # The root folder is scanned but is not repeated in items.
    if report.summary.folders_scanned != folder_count + 1:
        raise Step6InventoryValidationError(
            "Step 6 folders_scanned does not match folder records"
        )


def cross_validate_step6_csv(
    report: Step6InventoryReport,
    csv_path: str | Path,
) -> None:
    """Require the CSV rows to match the JSON items exactly and in order."""
    try:
        with Path(csv_path).open(
            "r", encoding="utf-8-sig", newline=""
        ) as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != ITEM_FIELDS:
                raise Step6InventoryValidationError(
                    "Step 6 CSV columns do not match the required schema"
                )
            rows = list(reader)
    except Step6InventoryValidationError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise Step6InventoryValidationError(
            "Step 6 CSV report could not be parsed"
        ) from exc

    if len(rows) != len(report.items):
        raise Step6InventoryValidationError(
            "Step 6 JSON and CSV row counts do not match"
        )
    for index, (item, row) in enumerate(zip(report.items, rows)):
        expected = _item_csv_values(item)
        if row != expected:
            raise Step6InventoryValidationError(
                f"Step 6 JSON and CSV differ at item index {index}"
            )


def build_source_file_payloads(
    report: Step6InventoryReport,
    *,
    source_folder_id: str,
    scan_run_id: str,
) -> list[dict[str, Any]]:
    """Map non-folder report items to proposed ``source_files`` payloads."""
    source_folder_id = _text(source_folder_id, "source_folder_id")
    scan_run_id = _text(scan_run_id, "scan_run_id")
    payloads: list[dict[str, Any]] = []
    for item in report.source_file_items:
        if item.classification == SUPPORTED_FILE_CLASSIFICATION:
            decision = "TAKE"
            status = "READY"
            skip_reason = None
        elif item.classification == UNSUPPORTED_FILE_CLASSIFICATION:
            decision = "SKIP"
            status = "SKIPPED"
            skip_reason = "Unsupported by Step 6 inventory classification"
        elif item.classification == INACCESSIBLE_ITEM_CLASSIFICATION:
            decision = "PENDING"
            status = "INACCESSIBLE"
            skip_reason = None
        else:  # Protected by parsing; retained as defensive validation.
            raise Step6InventoryValidationError(
                "Cannot map an unrecognized Step 6 classification"
            )

        payloads.append(
            {
                "source_folder_id": source_folder_id,
                "last_scan_run_id": scan_run_id,
                "google_file_id": item.file_id,
                "file_name": item.name,
                "mime_type": item.mime_type,
                "file_extension": item.file_extension,
                "size_bytes": item.size,
                "md5_checksum": None,
                "drive_created_at": item.created_time,
                "drive_modified_at": item.modified_time,
                "web_view_link": item.web_view_link,
                "thumbnail_link": None,
                "parent_google_folder_id": item.parent_folder_id,
                "relative_path": item.relative_folder_path,
                "decision": decision,
                "processing_status": status,
                "processing_error": None,
                "skip_reason": skip_reason,
                "trashed": False,
                "is_missing": False,
                "last_seen_at": report.generated_at_utc,
                "metadata": {
                    "step6_classification": item.classification,
                    "step6_accessibility_status": item.accessibility_status,
                    "import_type": "STEP6_INVENTORY",
                    "report_sha256": report.report_sha256,
                },
            }
        )
    return payloads


def build_scan_run_payload(
    report: Step6InventoryReport,
    *,
    source_folder_id: str,
) -> dict[str, Any]:
    """Build the proposed in-progress ``scan_runs`` insert payload."""
    source_folder_id = _text(source_folder_id, "source_folder_id")
    summary = report.summary
    return {
        "source_folder_id": source_folder_id,
        "run_mode": "DRY_RUN",
        "status": "RUNNING",
        "started_at": report.generated_at_utc,
        "files_discovered": summary.total_files_found,
        "files_taken": summary.supported_files,
        "files_skipped": summary.unsupported_files,
        "files_uploaded": 0,
        "duplicates_found": 0,
        "files_failed": summary.errors,
        "metadata": {
            "report_sha256": report.report_sha256,
            "report_generated_at_utc": report.generated_at_utc,
            "root_file_id": report.root.file_id,
            "root_name": report.root.name,
            "root_mime_type": report.root.mime_type,
            "folders_scanned": summary.folders_scanned,
            "total_items_discovered": summary.total_items_discovered,
            "inaccessible_items": summary.inaccessible_items,
            "errors": summary.errors,
            "api_pages_requested": summary.api_pages_requested,
            "import_type": "STEP6_INVENTORY",
        },
    }


def build_migration_event_payloads(
    report: Step6InventoryReport,
    *,
    source_folder_id: str,
    scan_run_id: str,
) -> list[dict[str, Any]]:
    """Map sanitized report errors to proposed migration event payloads."""
    return [
        {
            "source_folder_id": source_folder_id,
            "scan_run_id": scan_run_id,
            "event_type": "STEP6_INVENTORY_ERROR",
            "event_status": "ERROR",
            "message": error.message,
            "details": {
                "item_id": error.item_id,
                "failure_category": error.failure_category,
                "http_status": error.http_status,
                "report_sha256": report.report_sha256,
            },
        }
        for error in report.errors
    ]


def _parse_item(value: Any, index: int) -> Step6Item:
    item = _object(value, f"items[{index}]")
    _exact_keys(item, EXPECTED_ITEM_KEYS, f"items[{index}]")
    classification = _text(
        item["classification"], f"items[{index}].classification"
    )
    if classification not in ALLOWED_CLASSIFICATIONS:
        raise Step6InventoryValidationError(
            f"Unknown classification at item index {index}"
        )
    accessibility = _text(
        item["accessibility_status"],
        f"items[{index}].accessibility_status",
    )
    if accessibility not in ALLOWED_ACCESSIBILITY_STATUSES:
        raise Step6InventoryValidationError(
            f"Unknown accessibility status at item index {index}"
        )
    if (
        classification == INACCESSIBLE_ITEM_CLASSIFICATION
        and accessibility != "inaccessible"
    ):
        raise Step6InventoryValidationError(
            f"Inaccessible classification mismatch at item index {index}"
        )
    if (
        classification != INACCESSIBLE_ITEM_CLASSIFICATION
        and accessibility != "accessible"
    ):
        raise Step6InventoryValidationError(
            f"Accessibility classification mismatch at item index {index}"
        )
    return Step6Item(
        file_id=_text(item["file_id"], f"items[{index}].file_id"),
        name=_text(item["name"], f"items[{index}].name"),
        mime_type=_text(item["mime_type"], f"items[{index}].mime_type"),
        file_extension=_optional_text(
            item["file_extension"], f"items[{index}].file_extension"
        ),
        size=_optional_nonnegative_integer(
            item["size"], f"items[{index}].size"
        ),
        created_time=_timestamp(
            item["created_time"],
            f"items[{index}].created_time",
            required=False,
        ),
        modified_time=_timestamp(
            item["modified_time"],
            f"items[{index}].modified_time",
            required=False,
        ),
        parent_folder_id=_text(
            item["parent_folder_id"],
            f"items[{index}].parent_folder_id",
        ),
        relative_folder_path=_nullable_to_empty_text(
            item["relative_folder_path"],
            f"items[{index}].relative_folder_path",
        ),
        web_view_link=_optional_text(
            item["web_view_link"], f"items[{index}].web_view_link"
        ),
        accessibility_status=accessibility,
        classification=classification,
    )


def _parse_error(value: Any, index: int) -> Step6Error:
    error = _object(value, f"errors[{index}]")
    _exact_keys(error, EXPECTED_ERROR_KEYS, f"errors[{index}]")
    status = error["http_status"]
    if status is not None:
        status = _nonnegative_integer(status, f"errors[{index}].http_status")
    return Step6Error(
        item_id=_text(error["item_id"], f"errors[{index}].item_id"),
        failure_category=_text(
            error["failure_category"], f"errors[{index}].failure_category"
        ),
        http_status=status,
        message=_text(error["message"], f"errors[{index}].message"),
    )


def _item_csv_values(item: Step6Item) -> dict[str, str]:
    values = {
        "file_id": item.file_id,
        "name": item.name,
        "mime_type": item.mime_type,
        "file_extension": item.file_extension,
        "size": item.size,
        "created_time": item.created_time,
        "modified_time": item.modified_time,
        "parent_folder_id": item.parent_folder_id,
        "relative_folder_path": item.relative_folder_path,
        "web_view_link": item.web_view_link,
        "accessibility_status": item.accessibility_status,
        "classification": item.classification,
    }
    return {
        key: "" if values[key] is None else str(values[key])
        for key in ITEM_FIELDS
    }


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise Step6InventoryValidationError(f"{field} must be an object")
    return value


def _array(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise Step6InventoryValidationError(f"{field} must be an array")
    return value


def _exact_keys(
    value: Mapping[str, Any], expected: frozenset[str], field: str
) -> None:
    if frozenset(value) != expected:
        raise Step6InventoryValidationError(
            f"{field} fields do not match the required schema"
        )


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Step6InventoryValidationError(
            f"{field} must be a non-empty string"
        )
    return value


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise Step6InventoryValidationError(
            f"{field} must be a string or null"
        )
    return value or None


def _nullable_to_empty_text(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise Step6InventoryValidationError(
            f"{field} must be a string or null"
        )
    return value


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise Step6InventoryValidationError(
            f"{field} must be a non-negative integer"
        )
    return value


def _optional_nonnegative_integer(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_integer(value, field)


def _timestamp(value: Any, field: str, *, required: bool) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise Step6InventoryValidationError(
            f"{field} must be a valid ISO-8601 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Step6InventoryValidationError(
            f"{field} must be a valid ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Step6InventoryValidationError(
            f"{field} must include a timezone"
        )
    return value
