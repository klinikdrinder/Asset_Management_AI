"""Environment-backed workflow configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _boolean(name: str) -> bool:
    value = _required(name).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false, not {value!r}")


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_service_role_key: str
    google_credentials_path: Path
    google_token_path: Path
    destination_folder_id: str
    source_folder_name: str
    dry_run: bool

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        return cls(
            supabase_url=_required("SUPABASE_URL"),
            supabase_service_role_key=_required(
                "SUPABASE_SERVICE_ROLE_KEY"
            ),
            google_credentials_path=Path(
                _required("GOOGLE_CREDENTIALS_PATH")
            ).expanduser(),
            google_token_path=Path(
                _required("GOOGLE_TOKEN_PATH")
            ).expanduser(),
            destination_folder_id=_required("DESTINATION_FOLDER_ID"),
            source_folder_name=_required("SOURCE_FOLDER_NAME"),
            dry_run=_boolean("DRY_RUN"),
        )
