"""Explicit, narrowly scoped Supabase Auth dashboard-reader provisioning.

Administrative utility only. It never reads or writes application tables,
alters RLS, prints credentials, or exposes Auth tokens.
"""

from __future__ import annotations

import argparse
from getpass import getpass
import json
import os
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from supabase import create_client


REQUIRED_METADATA = {
    "kdi_media_reader": "true",
    "kdi_media_access": True,
}
APPROVED_EMAIL = "kdimediaautomation@gmail.com"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--email", required=True)
    result.add_argument("--authorize-administration", action="store_true")
    result.add_argument("--email-confirmed", action="store_true")
    result.add_argument("--confirm-existing-email", action="store_true")
    result.add_argument("--configure-dashboard-env", action="store_true")
    result.add_argument(
        "--dashboard-env-path",
        type=Path,
        default=Path("dashboard/.env.local"),
    )
    return result


def validate_request(email: str, authorized: bool) -> str:
    normalized = email.strip().lower()
    if not authorized:
        raise RuntimeError("Explicit administrative authorization is required")
    if normalized != APPROVED_EMAIL:
        raise RuntimeError("Reader email does not match the approved identity")
    return normalized


def find_user(users: Iterable[Any], email: str) -> Any | None:
    matches = [
        user
        for user in users
        if str(getattr(user, "email", "") or "").strip().lower() == email
    ]
    if len(matches) > 1:
        raise RuntimeError("Duplicate Auth users require manual review")
    return matches[0] if matches else None


def claims_are_exact(metadata: dict[str, Any]) -> bool:
    kdi_claims = {key: value for key, value in metadata.items() if key.startswith("kdi_")}
    return kdi_claims == REQUIRED_METADATA


def sanitized_result(status: str, created: bool) -> str:
    return json.dumps(
        {
            "status": status,
            "reader_email": "kd***@gmail.com",
            "created": created,
            "claims_verified": True,
            "secrets_printed": False,
        },
        sort_keys=True,
    )


def confirm_existing_email(admin: Any, existing: Any) -> Any:
    if existing is None:
        raise RuntimeError("Confirmation-only mode requires an existing reader")
    user_id = str(getattr(existing, "id", "") or "")
    if not user_id:
        raise RuntimeError("Existing reader has no safe Auth identifier")
    original_metadata = dict(getattr(existing, "app_metadata", {}) or {})
    response = admin.auth.admin.update_user_by_id(
        user_id,
        {"email_confirm": True},
    )
    user = getattr(response, "user", response)
    if str(getattr(user, "id", "") or "") != user_id:
        raise RuntimeError("Confirmation response changed the Auth user identity")
    if dict(getattr(user, "app_metadata", {}) or {}) != original_metadata:
        raise RuntimeError("Confirmation-only mode changed app metadata")
    if not (
        getattr(user, "email_confirmed_at", None)
        or getattr(user, "confirmed_at", None)
    ):
        raise RuntimeError("Reader email confirmation was not verified")
    return user


def main() -> int:
    args = parser().parse_args()
    email = validate_request(args.email, args.authorize_administration)
    load_dotenv(".env")
    url = _required("SUPABASE_URL")
    admin_key = _required("SUPABASE_SERVICE_ROLE_KEY")
    admin = create_client(url, admin_key)
    users = list(admin.auth.admin.list_users(page=1, per_page=100) or [])
    existing = find_user(users, email)

    if args.confirm_existing_email:
        confirm_existing_email(admin, existing)
        admin_key = ""
        print(sanitized_result("EXISTING_READER_EMAIL_CONFIRMED", False))
        return 0

    password = getpass("Reader password (hidden): ")
    if not password:
        raise SystemExit("A non-empty hidden reader password is required")

    attributes = {
        "email": email,
        "password": password,
        "email_confirm": bool(args.email_confirmed),
        "app_metadata": dict(REQUIRED_METADATA),
    }
    if existing is None:
        response = admin.auth.admin.create_user(attributes)
        user = getattr(response, "user", response)
        created = True
    else:
        user_id = str(getattr(existing, "id", "") or "")
        if not user_id:
            raise RuntimeError("Existing reader has no safe Auth identifier")
        response = admin.auth.admin.update_user_by_id(user_id, attributes)
        user = getattr(response, "user", response)
        created = False

    metadata = dict(getattr(user, "app_metadata", {}) or {})
    if not claims_are_exact(metadata):
        raise RuntimeError("Reader claims were not assigned exactly")

    if args.configure_dashboard_env:
        anon_key = getpass("Public anon/publishable key (hidden input): ")
        if not anon_key:
            raise RuntimeError("Public anon/publishable key is required")
        reader = create_client(url, anon_key)
        session_response = reader.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        session = getattr(session_response, "session", None)
        access_token = str(getattr(session, "access_token", "") or "")
        if not access_token:
            raise RuntimeError("Restricted reader session was not created")
        _write_ignored_env(args.dashboard_env_path, url, anon_key, access_token)

    password = ""
    admin_key = ""
    print(sanitized_result("PROVISIONED_AND_VERIFIED", created))
    return 0


def _write_ignored_env(path: Path, url: str, anon_key: str, token: str) -> None:
    if path.name != ".env.local" or path.parent.name != "dashboard":
        raise RuntimeError("Dashboard credentials must use dashboard/.env.local")
    path.write_text(
        "\n".join(
            (
                f"NEXT_PUBLIC_SUPABASE_URL={url}",
                f"NEXT_PUBLIC_SUPABASE_ANON_KEY={anon_key}",
                f"SUPABASE_DASHBOARD_ACCESS_TOKEN={token}",
                "",
            )
        ),
        encoding="utf-8",
    )


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing administrative prerequisite: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
