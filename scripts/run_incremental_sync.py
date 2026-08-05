"""Step 14 daily incremental synchronization command."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from supabase import create_client


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kdi_media.daily_sync import IncrementalSyncRunner
from kdi_media.google_drive import (
    create_destination_write_drive_service,
    create_readonly_drive_service,
)
from kdi_media.production_sync_adapter import ProductionSyncAdapter
from kdi_media.step9_hashing import RetryableHashingError, iter_drive_content
from kdi_media.step10_production import APPROVED_ROOT


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="KDI Step 14 incremental synchronization")
    result.add_argument("sync", nargs="?", default="sync")
    result.add_argument("--incremental", action="store_true", required=True)
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--source-id", action="append")
    result.add_argument("--run-id")
    result.add_argument("--trigger", choices=("manual", "scheduled"), default="manual")
    result.add_argument("--controlled-transient-hash-once", action="store_true", help=argparse.SUPPRESS)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    load_dotenv(ROOT / ".env")
    try:
        client = create_client(_required("SUPABASE_URL"), _required("SUPABASE_SERVICE_ROLE_KEY"))
        source_service = create_readonly_drive_service()

        def adapter_factory() -> ProductionSyncAdapter:
            destination_service = create_destination_write_drive_service()
            root_id = os.getenv("DESTINATION_FOLDER_ID", "").strip() or APPROVED_ROOT
            if root_id != APPROVED_ROOT:
                raise RuntimeError("Configured destination is not the approved KDI Master root")
            content_reader = iter_drive_content
            if args.controlled_transient_hash_once:
                if args.source_id != ["0e24d6b7-0429-461c-87b4-75471c759e4f"]:
                    raise RuntimeError("Controlled failure hook is restricted to the approved Step 14 fixture")
                attempts = {"count": 0}
                def controlled_reader(service, file_id, *, chunk_size):
                    attempts["count"] += 1
                    if attempts["count"] == 1:
                        raise RetryableHashingError("Controlled one-time transient hash failure")
                    return iter_drive_content(service, file_id, chunk_size=chunk_size)
                content_reader = controlled_reader
            return ProductionSyncAdapter(
                client=client,
                source_service=source_service,
                destination_service=destination_service,
                destination_root_id=root_id,
                spool_root=ROOT / "tmp" / "step14-production-spool",
                hash_content_reader=content_reader,
            )

        runner = IncrementalSyncRunner(
            client=client,
            source_service=source_service,
            adapter_factory=adapter_factory,
            report_root=ROOT / "reports" / "step-14",
        )
        report = runner.run(
            dry_run=args.dry_run,
            trigger=args.trigger,
            source_ids=args.source_id,
            run_id=args.run_id,
        )
    except Exception as exc:
        print(json.dumps({"status": "FAILED_CONFIGURATION_OR_PREFLIGHT", "error": _safe(exc)}))
        return 2
    print(json.dumps({
        "run_id": report["run_id"], "status": report["status"],
        "dry_run": report["dry_run"], "report": report.get("report_path"),
        "totals": report["totals"], "reconciliation": report.get("reconciliation"),
    }, sort_keys=True))
    return 0 if report["status"] in {"COMPLETED", "DRY_RUN_RECONCILED", "OVERLAP_REJECTED"} else 1


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


def _safe(exc: BaseException) -> str:
    return " ".join(str(exc).replace("\r", " ").replace("\n", " ").split())[:500]


if __name__ == "__main__":
    raise SystemExit(main())
