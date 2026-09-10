"""Interactive one-time reauthorization for the approved source Drive token.

This does not index media or write semantic data. It only refreshes/replaces
the read-only source OAuth token used by the scheduled repository sync.
"""
from pathlib import Path
import sys
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from kdi_media.google_drive import load_oauth_config, load_readonly_credentials  # noqa: E402


if __name__ == "__main__":
    config = load_oauth_config()
    credentials = load_readonly_credentials(config)
    print({"status": "PASS", "token_path": str(config.token_file), "scopes": list(credentials.scopes or [])})
