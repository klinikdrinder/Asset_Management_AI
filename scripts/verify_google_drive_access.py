"""Verify read-only access to one Google Drive folder."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kdi_media.google_drive import (  # noqa: E402
    GoogleDriveError,
    create_readonly_drive_service,
    get_authenticated_account_email,
    list_immediate_children,
    verify_folder_access,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify read-only access to a Google Drive folder."
    )
    parser.add_argument("--folder-id", required=True)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Maximum immediate child names to display (default: 5).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.sample_size < 0 or args.sample_size > 20:
        print(
            "Verification failed: sample size must be between 0 and 20.",
            file=sys.stderr,
        )
        return 2

    try:
        service = create_readonly_drive_service()
        account_email = get_authenticated_account_email(service)
        folder = verify_folder_access(service, args.folder_id)
        listing = list_immediate_children(service, folder.id)
    except GoogleDriveError as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "Verification failed due to an unexpected non-secret error.",
            file=sys.stderr,
        )
        return 1

    if account_email:
        print(f"Authenticated account: {account_email}")
    else:
        print("Authenticated account: unavailable")
    print(f"Folder name: {folder.name}")
    print(f"Folder ID: {folder.id}")
    print(f"Immediate child count: {len(listing.children)}")
    print(f"Pagination used: {'yes' if listing.pagination_used else 'no'}")
    if args.sample_size:
        print("Immediate child sample:")
        for child in listing.children[: args.sample_size]:
            print(f"- {child.name} [{child.mime_type}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
