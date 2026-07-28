"""Google OAuth authentication for Drive API v3."""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


def authenticate(credentials_path: Path, token_path: Path) -> Credentials:
    if not credentials_path.is_file():
        raise FileNotFoundError(
            f"Google OAuth credentials file not found: {credentials_path}"
        )

    credentials = None
    if token_path.is_file():
        credentials = Credentials.from_authorized_user_file(
            str(token_path),
            [DRIVE_SCOPE],
        )

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path),
            [DRIVE_SCOPE],
        )
        credentials = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials
