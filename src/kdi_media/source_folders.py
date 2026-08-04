"""Validation and registration of Google Drive source folders."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit
import os
import re

from dotenv import load_dotenv
from supabase import Client, create_client


_FOLDER_PATH = re.compile(r"^/drive/folders/([A-Za-z0-9_-]+)/?$")
_NOT_SUPPLIED = object()


def extract_google_folder_id(folder_url: str) -> str:
    """Return the folder ID from a standard Google Drive folder URL."""
    if not isinstance(folder_url, str) or not folder_url.strip():
        raise ValueError("Google Drive folder URL must be a non-empty string")

    try:
        parsed = urlsplit(folder_url.strip())
    except ValueError as exc:
        raise ValueError("Malformed Google Drive folder URL") from exc

    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() != "drive.google.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
    ):
        raise ValueError(
            "Folder URL must be an HTTPS URL on drive.google.com"
        )

    match = _FOLDER_PATH.fullmatch(parsed.path)
    if match is None:
        raise ValueError(
            "URL is not a Google Drive folder URL; expected "
            "https://drive.google.com/drive/folders/FOLDER_ID"
        )
    return match.group(1)


def normalize_google_folder_url(folder_url: str) -> str:
    """Return a canonical folder URL without query parameters or fragments."""
    folder_id = extract_google_folder_id(folder_url)
    return f"https://drive.google.com/drive/folders/{folder_id}"


def create_supabase_client_from_environment() -> Client:
    """Create a Supabase client from required environment variables."""
    load_dotenv()
    url = _required_environment("SUPABASE_URL")
    service_role_key = _required_environment("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, service_role_key)


def register_source_folder(
    client: Client,
    *,
    source_name: str,
    account_name: str,
    folder_url: str,
    notes: Any = _NOT_SUPPLIED,
    active: Any = _NOT_SUPPLIED,
    access_status: Any = _NOT_SUPPLIED,
    permission_role: Any = _NOT_SUPPLIED,
    last_access_checked_at: Any = _NOT_SUPPLIED,
    last_scan_at: Any = _NOT_SUPPLIED,
    last_successful_scan_at: Any = _NOT_SUPPLIED,
) -> dict[str, Any]:
    """Insert or selectively update a source folder by Google folder ID."""
    source_name = _required_text("source_name", source_name)
    account_name = _required_text("account_name", account_name)
    google_folder_id = extract_google_folder_id(folder_url)

    values: dict[str, Any] = {
        "source_name": source_name,
        "account_name": account_name,
        "folder_url": normalize_google_folder_url(folder_url),
        "google_folder_id": google_folder_id,
    }
    optional_values = {
        "notes": notes,
        "active": active,
        "access_status": access_status,
        "permission_role": permission_role,
        "last_access_checked_at": last_access_checked_at,
        "last_scan_at": last_scan_at,
        "last_successful_scan_at": last_successful_scan_at,
    }
    values.update(
        {
            key: value
            for key, value in optional_values.items()
            if value is not _NOT_SUPPLIED
        }
    )

    response = (
        client.table("source_folders")
        .upsert(values, on_conflict="google_folder_id")
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise RuntimeError("Supabase did not return the registered source folder")
    return rows[0]


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _required_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
