"""Safe Step 10 worker entry point.

Without --execute this command performs argument validation only and makes no
network or database calls. Production execution additionally requires the
deployed migration and an exact destination confirmation.
"""

from __future__ import annotations

import argparse
import json
import os
from uuid import UUID

from dotenv import load_dotenv
from supabase import create_client

from kdi_media.google_drive import DriveCredentialProfile
from kdi_media.step10_upload import SupabaseStep10Repository


APPROVED_DESTINATION_ROOT = "1CdmowWV5TAk5R9D5yl2cOT8Plx3ihZgl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", required=True, type=int)
    parser.add_argument("--asset-id")
    allowlist = parser.add_mutually_exclusive_group()
    allowlist.add_argument(
        "--asset-destination-id",
        action="append",
        default=None,
        help="Optional exact lifecycle-ID allowlist for controlled execution.",
    )
    allowlist.add_argument(
        "--empty-asset-destination-allowlist",
        action="store_true",
        help="Explicitly use an empty lifecycle allowlist (claim zero rows).",
    )
    parser.add_argument(
        "--destination-folder-id",
        required=True,
    )
    parser.add_argument(
        "--confirm-destination",
        choices=["KDI Master"],
    )
    parser.add_argument(
        "--source-profile",
        choices=[DriveCredentialProfile.SOURCE_READONLY.value],
        required=True,
    )
    parser.add_argument(
        "--destination-profile",
        choices=[DriveCredentialProfile.DESTINATION_WRITE.value],
        required=True,
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.limit <= 100:
        raise SystemExit("--limit must be between 1 and 100")
    if args.asset_id:
        UUID(args.asset_id)
    if args.empty_asset_destination_allowlist:
        args.asset_destination_id = []
    elif args.asset_destination_id is not None:
        args.asset_destination_id = [
            str(UUID(value)) for value in args.asset_destination_id
        ]
    if args.destination_folder_id != APPROVED_DESTINATION_ROOT:
        raise SystemExit("Destination root does not match approved KDI Master")
    if args.execute and args.dry_run:
        raise SystemExit("--execute and --dry-run are mutually exclusive")
    if args.execute and args.confirm_destination != "KDI Master":
        raise SystemExit(
            "--execute requires --confirm-destination \"KDI Master\""
        )
    if (
        args.source_profile
        != DriveCredentialProfile.SOURCE_READONLY.value
        or args.destination_profile
        != DriveCredentialProfile.DESTINATION_WRITE.value
    ):
        raise SystemExit("Credential profile isolation check failed")


def main() -> int:
    args = build_parser().parse_args()
    validate_args(args)
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "DRY_RUN",
                    "limit": args.limit,
                    "asset_filter": bool(args.asset_id),
                    "lifecycle_allowlist_count": (
                        None
                        if args.asset_destination_id is None
                        else len(args.asset_destination_id)
                    ),
                    "destination_confirmed": True,
                    "source_profile": args.source_profile,
                    "destination_profile": args.destination_profile,
                    "database_writes": 0,
                    "drive_requests": 0,
                },
                sort_keys=True,
            )
        )
        return 0

    load_dotenv()
    client = create_client(
        _required_environment("SUPABASE_URL"),
        _required_environment("SUPABASE_SERVICE_ROLE_KEY"),
    )
    repository = SupabaseStep10Repository(client)
    # This zero-row probe is deliberately first. Until the approved migration
    # is deployed, execution refuses before credentials or Drive are loaded.
    repository.require_schema()
    raise SystemExit(
        "Step 10 execution orchestration requires the separately approved "
        "database-only dry run and production pilot gate"
    )


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required configuration: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
