"""Register a Google Drive source folder in the KDI media library."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kdi_media.source_folders import (  # noqa: E402
    create_supabase_client_from_environment,
    register_source_folder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Register or update a Google Drive source folder."
    )
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--account-name", required=True)
    parser.add_argument("--folder-url", required=True)
    parser.add_argument("--notes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = create_supabase_client_from_environment()
        folder = register_source_folder(
            client,
            source_name=args.source_name,
            account_name=args.account_name,
            folder_url=args.folder_url,
            **({"notes": args.notes} if args.notes is not None else {}),
        )
    except Exception as exc:
        print(f"Registration failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Source folder registered: "
        f"{folder.get('source_name', args.source_name)} "
        f"({folder.get('google_folder_id', 'unknown folder ID')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
