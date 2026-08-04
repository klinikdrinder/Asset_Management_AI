"""One-time local PKCE bootstrap for the read-only dashboard reader.

Uses only the public Supabase project URL/key and never prints auth material.
"""
from __future__ import annotations

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

PROJECT = "wcqqjpndlwsvatjuqnol"
APPROVED_EMAIL = "kdimediaautomation@gmail.com"
CALLBACK_BASE = "http://127.0.0.1:8765/auth/callback"
ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "dashboard" / ".env.local"
SESSION_PATH = ROOT / "dashboard" / ".reader-session.json"
TIMEOUT_SECONDS = 600


def load_public_environment() -> tuple[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    url = values.get("NEXT_PUBLIC_SUPABASE_URL", "")
    key = values.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != f"{PROJECT}.supabase.co" or not key:
        raise RuntimeError("READER_BOOTSTRAP_INVALID_PUBLIC_CONFIGURATION")
    return url.rstrip("/"), key


def request_json(url: str, key: str, body: dict[str, object]) -> dict[str, object]:
    request = Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "apikey": key, "Content-Type": "application/json",
    })
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        if exc.code in (400, 422):
            raise RuntimeError("READER_BOOTSTRAP_REQUIRES_REDIRECT_ALLOWLIST") from None
        raise RuntimeError("READER_BOOTSTRAP_REQUEST_FAILED") from None
    except URLError:
        raise RuntimeError("READER_BOOTSTRAP_REQUEST_FAILED") from None


def decode_claims(token: str) -> dict[str, object]:
    try:
        part = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except Exception:
        raise RuntimeError("READER_BOOTSTRAP_INVALID_SESSION") from None


def validate_session(url: str, key: str, payload: dict[str, object]) -> dict[str, object]:
    access = str(payload.get("access_token") or "")
    refresh = str(payload.get("refresh_token") or "")
    claims = decode_claims(access)
    metadata = claims.get("app_metadata") if isinstance(claims.get("app_metadata"), dict) else {}
    expected_issuer = f"{url}/auth/v1"
    if (claims.get("iss") != expected_issuer or claims.get("aud") != "authenticated"
            or metadata.get("kdi_media_reader") != "true"
            or metadata.get("kdi_media_access") is not True
            or not isinstance(claims.get("exp"), (int, float))
            or float(claims["exp"]) <= time.time() or not refresh):
        raise RuntimeError("READER_BOOTSTRAP_INVALID_SESSION")
    user_request = Request(f"{url}/auth/v1/user", headers={
        "apikey": key, "Authorization": f"Bearer {access}",
    })
    try:
        with urlopen(user_request, timeout=30) as response:
            user = json.loads(response.read().decode())
    except (HTTPError, URLError):
        raise RuntimeError("READER_BOOTSTRAP_INVALID_SESSION") from None
    if str(user.get("email") or "").strip().lower() != APPROVED_EMAIL:
        raise RuntimeError("READER_BOOTSTRAP_INVALID_IDENTITY")
    return {"access_token": access, "refresh_token": refresh,
            "expires_at": int(claims["exp"]), "project_ref": PROJECT}


def atomic_write_session(session: dict[str, object]) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".reader-session.json.", dir=SESSION_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(session, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, SESSION_PATH)
        if os.name == "nt":
            user = os.environ.get("USERNAME", "")
            if user:
                subprocess.run(["icacls", str(SESSION_PATH), "/inheritance:r", "/grant:r", f"{user}:(R,W)"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            os.chmod(SESSION_PATH, 0o600)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def main() -> int:
    url, key = load_public_environment()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    callback = f"{CALLBACK_BASE}?{urlencode({'state': state})}"
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            valid_peer = self.client_address[0] in ("127.0.0.1", "::1")
            if parsed.path != "/auth/callback" or not valid_peer or query.get("state", [""])[0] != state:
                self.send_response(400); self.end_headers(); self.wfile.write(b"Invalid sign-in callback."); return
            code = query.get("code", [""])[0]
            if not code or result:
                self.send_response(400); self.end_headers(); self.wfile.write(b"Invalid or reused sign-in callback."); return
            result["code"] = code
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(b"<!doctype html><title>KDI Reader</title><h1>Sign-in received</h1><p>You may close this tab.</p>")

    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    server.timeout = 1
    try:
        request_json(f"{url}/auth/v1/otp?{urlencode({'redirect_to': callback})}", key, {
            "email": APPROVED_EMAIL, "create_user": False,
            "code_challenge": challenge, "code_challenge_method": "s256",
        })
        print("MAGIC_LINK_SENT")
        print("Check the approved reader inbox and click the newest sign-in link.")
        print("Waiting for the local callback...")
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while not result and time.monotonic() < deadline:
            server.handle_request()
        if not result:
            raise RuntimeError("READER_BOOTSTRAP_CALLBACK_TIMEOUT")
        token_response = request_json(f"{url}/auth/v1/token?grant_type=pkce", key, {
            "auth_code": result.pop("code"), "code_verifier": verifier,
        })
        session = validate_session(url, key, token_response)
        atomic_write_session(session)
        print("READER_SESSION_VALID")
        print(f"PROJECT={PROJECT}")
        print("AUDIENCE=authenticated")
        print("READER_CLAIMS=VALID_EXACT_TYPES")
        print("READER_IDENTITY=kd***@gmail.com")
        print("MANAGED_SESSION_STORED")
        return 0
    finally:
        verifier = ""; state = ""; result.clear(); server.server_close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
