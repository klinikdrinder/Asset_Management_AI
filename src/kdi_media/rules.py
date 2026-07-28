"""Pilot TAKE/SKIP classification rules."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .drive_client import GOOGLE_NATIVE_PREFIX, SHORTCUT_MIME_TYPE


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".mp4",
    ".mov",
    ".pptx",
}


def classify(file_metadata: dict[str, Any]) -> tuple[str, str]:
    mime_type = file_metadata.get("mimeType", "")
    name = file_metadata.get("name", "")

    if mime_type == SHORTCUT_MIME_TYPE:
        return "SKIP", "Google Drive shortcuts are temporarily skipped"

    if mime_type.startswith(GOOGLE_NATIVE_PREFIX):
        return "SKIP", "Google-native files are temporarily skipped"

    extension = PurePosixPath(name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        return "SKIP", f"Unsupported file extension: {extension or '(none)'}"

    return "TAKE", f"Supported pilot file type: {extension}"
