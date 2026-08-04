"""CLI for the explicitly gated Step 10 full-production upload."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

from kdi_media.step10_production import (
    ProductionOptions,
    ProductionOrchestrator,
    READY,
    write_report,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--execute-production", action="store_true")
    result.add_argument("--authorize-drive-transfer", action="store_true")
    result.add_argument("--expected-total-count", type=int, required=True)
    result.add_argument("--expected-completed-count", type=int, required=True)
    result.add_argument("--expected-remaining-count", type=int, required=True)
    result.add_argument("--destination-root-id", required=True)
    result.add_argument("--source-profile", required=True)
    result.add_argument("--destination-profile", required=True)
    result.add_argument("--batch-size", type=int, default=50)
    result.add_argument("--report-path", type=Path, required=True)
    result.add_argument(
        "--pilot-report-path",
        type=Path,
        default=Path("reports/step_10_limited_production_pilot_report.json"),
    )
    result.add_argument(
        "--spool-root",
        type=Path,
        default=Path("tmp/step10-production-spool"),
    )
    return result


def main() -> int:
    args = parser().parse_args()
    options = ProductionOptions(
        execute=args.execute_production,
        authorize=args.authorize_drive_transfer,
        expected_total=args.expected_total_count,
        expected_completed=args.expected_completed_count,
        expected_remaining=args.expected_remaining_count,
        root_id=args.destination_root_id,
        source_profile=args.source_profile,
        destination_profile=args.destination_profile,
        batch_size=args.batch_size,
        report_path=args.report_path,
        pilot_report_path=args.pilot_report_path,
        spool_root=args.spool_root,
    )
    options.validate()
    if not options.execute:
        report = {
            **ProductionOrchestrator(None, options).plan(),
            "report_path": str(options.report_path),
        }
        write_report(options.report_path, report)
        print(json.dumps(report, sort_keys=True))
        return 0
    load_dotenv(".env")
    client = create_client(
        _required("SUPABASE_URL"), _required("SUPABASE_SERVICE_ROLE_KEY")
    )
    report = ProductionOrchestrator(client, options).execute()
    print(
        json.dumps(
            {"verdict": report["verdict"], "report_path": str(options.report_path)},
            sort_keys=True,
        )
    )
    return 0 if report["verdict"] == READY else 2


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required configuration: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
