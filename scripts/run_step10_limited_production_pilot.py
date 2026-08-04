"""Explicitly gated exact-eight Step 10 production pilot."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

from kdi_media.step10_pilot import (
    BLOCKED_VERDICT,
    MANUAL_VERDICT,
    READY_VERDICT,
    PilotOptions,
    PilotOrchestrator,
    SupabaseDrivePilotBackend,
    write_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or run the exact-eight Step 10 production pilot."
    )
    parser.add_argument("--execute-pilot", action="store_true")
    parser.add_argument("--production-pilot", action="store_true")
    parser.add_argument("--pilot-only", action="store_true")
    parser.add_argument("--authorize-drive-transfer", action="store_true")
    parser.add_argument("--expected-pilot-count", required=True, type=int)
    parser.add_argument("--expected-non-pilot-count", required=True, type=int)
    parser.add_argument("--expected-jpeg-count", type=int, default=3)
    parser.add_argument("--expected-mp4-count", type=int, default=3)
    parser.add_argument("--expected-pdf-count", type=int, default=1)
    parser.add_argument("--expected-pptx-count", type=int, default=1)
    parser.add_argument("--manifest-path", required=True, type=Path)
    parser.add_argument("--destination-root-id", required=True)
    parser.add_argument("--source-profile", required=True)
    parser.add_argument("--destination-profile", required=True)
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument(
        "--spool-root",
        type=Path,
        default=Path("tmp/step10-pilot-spool"),
    )
    return parser


def options_from_args(args: argparse.Namespace) -> PilotOptions:
    if (
        args.expected_jpeg_count,
        args.expected_mp4_count,
        args.expected_pdf_count,
        args.expected_pptx_count,
    ) != (3, 3, 1, 1):
        raise SystemExit("Expected pilot format mix must be 3/3/1/1")
    return PilotOptions(
        execute=args.execute_pilot,
        production_pilot=args.production_pilot,
        pilot_only=args.pilot_only,
        authorize_drive_transfer=args.authorize_drive_transfer,
        expected_pilot_count=args.expected_pilot_count,
        expected_non_pilot_count=args.expected_non_pilot_count,
        destination_root_id=args.destination_root_id,
        source_profile=args.source_profile,
        destination_profile=args.destination_profile,
        manifest_path=args.manifest_path,
        report_path=args.report_path,
        spool_root=args.spool_root,
    )


class _PlanningBackend:
    pass


def main() -> int:
    args = build_parser().parse_args()
    options = options_from_args(args)
    if not args.execute_pilot:
        report = PilotOrchestrator(_PlanningBackend(), options).plan()
        write_report(options.report_path, report)
        print(json.dumps(report, sort_keys=True))
        return 0
    # Fail all execution gates before constructing a database or Drive client.
    options.validate()
    load_dotenv(".env")
    client = create_client(
        _required_environment("SUPABASE_URL"),
        _required_environment("SUPABASE_SERVICE_ROLE_KEY"),
    )
    backend = SupabaseDrivePilotBackend(client, options)
    report = PilotOrchestrator(backend, options).execute()
    write_report(options.report_path, report)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "report_path": str(options.report_path),
            },
            sort_keys=True,
        )
    )
    return verdict_exit_code(report["verdict"])


def verdict_exit_code(verdict: str) -> int:
    if verdict == READY_VERDICT:
        return 0
    if verdict == MANUAL_VERDICT:
        return 3
    if verdict == BLOCKED_VERDICT:
        return 2
    return 2


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required configuration: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
