"""Canonical, pure TAKE/SKIP eligibility rules.

This module is deliberately local-only.  It performs no network, Google Drive,
Supabase, filesystem-content, or database operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase
from types import MappingProxyType
from typing import Any, Mapping


RULE_VERSION = "step8.v1"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."


class ReasonCode(StrEnum):
    SUPPORTED_FORMAT = "SUPPORTED_FORMAT"
    FOLDER_ITEM = "FOLDER_ITEM"
    UNSUPPORTED_EXTENSION = "UNSUPPORTED_EXTENSION"
    UNSUPPORTED_MIME_TYPE = "UNSUPPORTED_MIME_TYPE"
    GOOGLE_NATIVE_FILE = "GOOGLE_NATIVE_FILE"
    GOOGLE_DRIVE_SHORTCUT = "GOOGLE_DRIVE_SHORTCUT"
    ZERO_BYTE_FILE = "ZERO_BYTE_FILE"
    INVALID_SIZE = "INVALID_SIZE"
    TEMPORARY_FILE = "TEMPORARY_FILE"
    SYSTEM_FILE = "SYSTEM_FILE"
    EXCLUDED_FILENAME = "EXCLUDED_FILENAME"
    EXCLUDED_PATH = "EXCLUDED_PATH"
    ADMINISTRATIVE_SKIP = "ADMINISTRATIVE_SKIP"
    INACCESSIBLE = "INACCESSIBLE"
    INVALID_METADATA = "INVALID_METADATA"
    TRASHED_FILE = "TRASHED_FILE"
    MISSING_FILE = "MISSING_FILE"


@dataclass(frozen=True)
class FormatPolicy:
    extension: str
    required_mime_type: str
    accepted_for_inventory: bool
    accepted_for_migration: bool
    accepted_for_duplicate_detection: bool
    accepted_for_ai_analysis: bool
    media_category: str


def _format(
    extension: str,
    mime_type: str,
    category: str,
    *,
    ai_analysis: bool,
) -> FormatPolicy:
    return FormatPolicy(
        extension=extension,
        required_mime_type=mime_type,
        accepted_for_inventory=True,
        accepted_for_migration=True,
        accepted_for_duplicate_detection=True,
        accepted_for_ai_analysis=ai_analysis,
        media_category=category,
    )


# The immutable, canonical default registry.  Image/video analysis remains
# enabled in line with the existing media-oriented workflow; document content
# analysis is explicitly outside Step 8 Phase A.
FORMAT_POLICY: Mapping[str, FormatPolicy] = MappingProxyType(
    {
        "jpg": _format("jpg", "image/jpeg", "image", ai_analysis=True),
        "jpeg": _format("jpeg", "image/jpeg", "image", ai_analysis=True),
        "png": _format("png", "image/png", "image", ai_analysis=True),
        "webp": _format("webp", "image/webp", "image", ai_analysis=True),
        "mp4": _format("mp4", "video/mp4", "video", ai_analysis=True),
        "mov": _format(
            "mov", "video/quicktime", "video", ai_analysis=True
        ),
        "pdf": _format(
            "pdf", "application/pdf", "document", ai_analysis=False
        ),
        "pptx": _format(
            "pptx",
            (
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            "document",
            ai_analysis=False,
        ),
    }
)


@dataclass(frozen=True)
class RuleConfiguration:
    formats: Mapping[str, FormatPolicy] = FORMAT_POLICY
    excluded_filename_patterns: tuple[str, ...] = ()
    excluded_path_patterns: tuple[str, ...] = ()
    reject_all_dotfiles: bool = False


DEFAULT_RULE_CONFIGURATION = RuleConfiguration()


@dataclass(frozen=True)
class FileRuleInput:
    file_name: Any
    mime_type: Any
    file_extension: Any
    size_bytes: Any
    relative_path: Any = ""
    accessibility_status: Any = "accessible"
    trashed: Any = False
    is_missing: Any = False
    is_folder: Any = False


Evidence = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DecisionResult:
    automatic_decision: str
    target_processing_status: str
    reason_code: ReasonCode
    rule_version: str
    normalized_extension: str
    normalized_mime_type: str
    media_category: str | None
    accepted_for_inventory: bool
    accepted_for_migration: bool
    accepted_for_duplicate_detection: bool
    accepted_for_ai_analysis: bool
    evidence: Evidence


def normalize_extension(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().lower()
    return normalized[1:] if normalized.startswith(".") else normalized


def normalize_mime_type(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def normalize_path(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parts = [part for part in value.replace("\\", "/").split("/") if part]
    return "/".join(parts).lower()


def evaluate_file(
    item: FileRuleInput,
    *,
    configuration: RuleConfiguration = DEFAULT_RULE_CONFIGURATION,
) -> DecisionResult:
    """Evaluate one metadata record using deterministic Step 8 priority."""
    extension = normalize_extension(item.file_extension)
    mime_type = normalize_mime_type(item.mime_type)
    path = normalize_path(item.relative_path)
    file_name = item.file_name if isinstance(item.file_name, str) else ""
    file_name_lower = file_name.lower()

    def result(
        decision: str,
        status: str,
        reason: ReasonCode,
        *,
        policy: FormatPolicy | None = None,
        evidence: Evidence = (),
    ) -> DecisionResult:
        return DecisionResult(
            automatic_decision=decision,
            target_processing_status=status,
            reason_code=reason,
            rule_version=RULE_VERSION,
            normalized_extension=extension,
            normalized_mime_type=mime_type,
            media_category=policy.media_category if policy else None,
            accepted_for_inventory=(
                policy.accepted_for_inventory if policy else False
            ),
            accepted_for_migration=(
                policy.accepted_for_migration if policy else False
            ),
            accepted_for_duplicate_detection=(
                policy.accepted_for_duplicate_detection if policy else False
            ),
            accepted_for_ai_analysis=(
                policy.accepted_for_ai_analysis if policy else False
            ),
            evidence=evidence,
        )

    # A. Folder.
    if item.is_folder is True or mime_type == FOLDER_MIME_TYPE:
        return result(
            "PENDING",
            "DISCOVERED",
            ReasonCode.FOLDER_ITEM,
            evidence=(("item_kind", "folder"),),
        )

    # B. Inaccessible.
    if item.accessibility_status == "inaccessible":
        return result(
            "PENDING",
            "INACCESSIBLE",
            ReasonCode.INACCESSIBLE,
            evidence=(("accessibility_status", "inaccessible"),),
        )

    # C. Invalid core metadata.  Extension and MIME absence have their own
    # ordered outcomes below, but invalid types cannot be evaluated safely.
    if (
        not file_name.strip()
        or not isinstance(item.mime_type, (str, type(None)))
        or not isinstance(item.file_extension, (str, type(None)))
        or not isinstance(item.relative_path, (str, type(None)))
        or not isinstance(item.trashed, bool)
        or not isinstance(item.is_missing, bool)
        or not isinstance(item.is_folder, bool)
        or item.accessibility_status not in {"accessible", "inaccessible"}
    ):
        return result(
            "SKIP", "SKIPPED", ReasonCode.INVALID_METADATA
        )

    # D-E. Source state.
    if item.trashed:
        return result("SKIP", "SKIPPED", ReasonCode.TRASHED_FILE)
    if item.is_missing:
        return result("SKIP", "SKIPPED", ReasonCode.MISSING_FILE)

    # F-G. Google-specific non-binary types.
    if mime_type == SHORTCUT_MIME_TYPE:
        return result(
            "SKIP", "SKIPPED", ReasonCode.GOOGLE_DRIVE_SHORTCUT
        )
    if mime_type.startswith(GOOGLE_NATIVE_PREFIX):
        return result(
            "SKIP", "SKIPPED", ReasonCode.GOOGLE_NATIVE_FILE
        )

    # H. Temporary filename.
    temporary = (
        file_name_lower.startswith("~$")
        or file_name_lower.startswith(".~lock.")
        or file_name_lower.endswith(
            (".tmp", ".temp", ".part", ".crdownload")
        )
    )
    if temporary:
        return result("SKIP", "SKIPPED", ReasonCode.TEMPORARY_FILE)

    # I. Known system names.  Other dotfiles are allowed by default.
    system = (
        file_name_lower in {".ds_store", "thumbs.db", "desktop.ini", "icon\r"}
        or file_name_lower.startswith("._")
        or (
            configuration.reject_all_dotfiles
            and file_name_lower.startswith(".")
        )
    )
    if system:
        return result("SKIP", "SKIPPED", ReasonCode.SYSTEM_FILE)

    # J-K. Configured exclusions use normalized, case-insensitive globs.
    if _matches(file_name_lower, configuration.excluded_filename_patterns):
        return result(
            "SKIP", "SKIPPED", ReasonCode.EXCLUDED_FILENAME
        )
    if _matches(path, configuration.excluded_path_patterns, path=True):
        return result("SKIP", "SKIPPED", ReasonCode.EXCLUDED_PATH)

    # L. The authoritative extension must be present and enabled.
    policy = configuration.formats.get(extension)
    if policy is None or not policy.accepted_for_inventory:
        return result(
            "SKIP",
            "SKIPPED",
            ReasonCode.UNSUPPORTED_EXTENSION,
            evidence=(("extension", extension or "(missing)"),),
        )

    # M-N. Strict extension-to-MIME pairing.
    if not mime_type:
        return result(
            "SKIP",
            "SKIPPED",
            ReasonCode.INVALID_METADATA,
            policy=policy,
            evidence=(("metadata_field", "mime_type"),),
        )
    if mime_type != policy.required_mime_type:
        return result(
            "SKIP",
            "SKIPPED",
            ReasonCode.UNSUPPORTED_MIME_TYPE,
            policy=policy,
            evidence=(("expected_mime_type", policy.required_mime_type),),
        )

    # O-P. All approved formats are binary Drive files and require a positive
    # integer size.  bool is rejected even though it subclasses int.
    if (
        isinstance(item.size_bytes, bool)
        or not isinstance(item.size_bytes, int)
        or item.size_bytes < 0
    ):
        return result(
            "SKIP",
            "SKIPPED",
            ReasonCode.INVALID_SIZE,
            policy=policy,
        )
    if item.size_bytes == 0:
        return result(
            "SKIP",
            "SKIPPED",
            ReasonCode.ZERO_BYTE_FILE,
            policy=policy,
        )

    # Q. Valid supported format.
    return result(
        "TAKE",
        "READY",
        ReasonCode.SUPPORTED_FORMAT,
        policy=policy,
        evidence=(
            ("extension", extension),
            ("mime_type", mime_type),
        ),
    )


def _matches(
    value: str,
    patterns: tuple[str, ...],
    *,
    path: bool = False,
) -> bool:
    for pattern in patterns:
        normalized = normalize_path(pattern) if path else pattern.strip().lower()
        if normalized and fnmatchcase(value, normalized):
            return True
    return False


def classify(file_metadata: Mapping[str, Any]) -> tuple[str, str]:
    """Compatibility adapter for the existing workflow.

    It delegates completely to the canonical engine; callers should migrate to
    :func:`evaluate_file` when they need the structured result.
    """
    raw_size = file_metadata.get("size")
    try:
        size: Any = int(raw_size) if raw_size is not None else None
    except (TypeError, ValueError):
        size = raw_size
    result = evaluate_file(
        FileRuleInput(
            file_name=file_metadata.get("name"),
            mime_type=file_metadata.get("mimeType"),
            file_extension=file_metadata.get("fileExtension"),
            size_bytes=size,
            relative_path=file_metadata.get("relativePath", ""),
            accessibility_status=file_metadata.get(
                "accessibilityStatus", "accessible"
            ),
            trashed=file_metadata.get("trashed", False),
            is_missing=file_metadata.get("isMissing", False),
            is_folder=(
                normalize_mime_type(file_metadata.get("mimeType"))
                == FOLDER_MIME_TYPE
            ),
        )
    )
    return result.automatic_decision, result.reason_code.value
