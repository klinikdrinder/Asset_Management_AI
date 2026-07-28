"""Command-line entry point."""

from __future__ import annotations

import sys

from .config import Settings
from .drive_client import DriveClient
from .google_auth import authenticate
from .supabase_store import SupabaseStore
from .workflow import run


def main() -> int:
    try:
        settings = Settings.from_environment()
        credentials = authenticate(
            settings.google_credentials_path,
            settings.google_token_path,
        )
        store = SupabaseStore(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        drive = DriveClient(credentials)
        return run(settings, store, drive)
    except KeyboardInterrupt:
        print("Cancelled by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
