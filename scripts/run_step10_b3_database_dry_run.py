"""Explicitly gated, database-only Step 10 Phase B3 command."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

from kdi_media.step10_b3 import (
    B3Options,
    B3Orchestrator,
    MANUAL_VERDICT,
    READY_VERDICT,
    SupabaseB3Database,
    write_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute the database-only Step 10 Phase B3 run."
    )
    parser.add_argument("--execute-database-tests", action="store_true")
    parser.add_argument("--database-only", action="store_true")
    parser.add_argument("--drive-operations-disabled", action="store_true")
    parser.add_argument("--expected-canonical-count", required=True, type=int)
    parser.add_argument(
        "--expected-preexisting-destination-count", required=True, type=int
    )
    parser.add_argument("--controlled-row-count", type=int, default=3)
    parser.add_argument("--destination-folder-id", required=True)
    parser.add_argument("--report-path", required=True, type=Path)
    return parser


def options_from_args(args: argparse.Namespace) -> B3Options:
    if args.execute_database_tests and not args.database_only:
        raise SystemExit("--execute-database-tests requires --database-only")
    if args.execute_database_tests and not args.drive_operations_disabled:
        raise SystemExit(
            "--execute-database-tests requires --drive-operations-disabled"
        )
    return B3Options(
        expected_canonical_count=args.expected_canonical_count,
        expected_preexisting_destination_count=(
            args.expected_preexisting_destination_count
        ),
        controlled_row_count=args.controlled_row_count,
        destination_folder_id=args.destination_folder_id,
        database_only=(
            args.database_only or not args.execute_database_tests
        ),
        execute=args.execute_database_tests,
        report_path=args.report_path,
    )


def main() -> int:
    args = build_parser().parse_args()
    options = options_from_args(args)
    if not args.execute_database_tests:
        # Planning constructs neither a Supabase client nor a Drive client.
        report = B3Orchestrator(_PlanningDatabase(), options).plan()
        write_report(options.report_path, report)
        print(json.dumps(report, sort_keys=True))
        return 0

    load_dotenv(".env")
    client = create_client(
        _required_environment("SUPABASE_URL"),
        _required_environment("SUPABASE_SERVICE_ROLE_KEY"),
    )
    report = B3Orchestrator(SupabaseB3Database(client), options).execute()
    write_report(options.report_path, report)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "report_path": str(options.report_path),
                "drive_operations": 0,
            },
            sort_keys=True,
        )
    )
    return verdict_exit_code(report["verdict"])


class _PlanningDatabase:
    """Unreachable placeholder proving plan mode has no database effects."""


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required configuration: {name}")
    return value


def verdict_exit_code(verdict: str) -> int:
    if verdict == READY_VERDICT:
        return 0
    if verdict == MANUAL_VERDICT:
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
