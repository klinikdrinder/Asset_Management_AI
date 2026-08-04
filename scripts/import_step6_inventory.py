"""Validate or import a completed Step 6 inventory report."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import os
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kdi_media.step6_inventory import (  # noqa: E402
    Step6InventoryReport,
    Step6InventoryValidationError,
    build_migration_event_payloads,
    build_scan_run_payload,
    build_source_file_payloads,
    cross_validate_step6_csv,
    parse_step6_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or import a Step 6 inventory report."
    )
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--csv", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--verify-only", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--expected-root-id")
    parser.add_argument("--expected-root-name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        print("Validation failed: --limit must be a positive integer", file=sys.stderr)
        return 2
    if args.limit is not None and not args.execute:
        print("Validation failed: --limit requires --execute", file=sys.stderr)
        return 2
    if args.csv is None and not args.verify_only:
        print("Validation failed: --csv is required for this mode", file=sys.stderr)
        return 2

    try:
        report = parse_step6_json(
            args.json,
            expected_root_id=args.expected_root_id,
            expected_root_name=args.expected_root_name,
        )
        if args.csv is not None:
            cross_validate_step6_csv(report, args.csv)
        if args.validate_only:
            _print_validation_summary(report, csv_consistent=True)
            return 0
        return _run_database_mode(args, report)
    except Step6InventoryValidationError as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "Step 7 operation failed without exposing report or secret data",
            file=sys.stderr,
        )
        return 1


def _print_validation_summary(
    report: Step6InventoryReport, *, csv_consistent: bool
) -> None:
    summary = report.summary
    payload_count = len(
        build_source_file_payloads(
            report,
            source_folder_id="validation-only",
            scan_run_id="validation-only",
        )
    )
    print(f"Report filename: {report.report_path.name}")
    print(f"Report SHA-256: {report.report_sha256}")
    print(f"Root folder name: {report.root.name}")
    print(f"Root folder ID: {report.root.file_id}")
    print(f"Folder count: {summary.folders_scanned}")
    print(f"File count: {summary.total_files_found}")
    print(f"Supported count: {summary.supported_files}")
    print(f"Unsupported count: {summary.unsupported_files}")
    print(f"Inaccessible count: {summary.inaccessible_items}")
    print(f"Error count: {summary.errors}")
    print(
        "JSON/CSV consistency result: "
        + ("consistent" if csv_consistent else "inconsistent")
    )
    print(f"Proposed source_files payloads: {payload_count}")
    print("Supabase connection occurred: no")


def _run_database_mode(
    args: argparse.Namespace, report: Step6InventoryReport
) -> int:
    """Run a database-aware mode; never reached by ``--validate-only``."""
    from kdi_media.supabase_store import SupabaseStore
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    url = _required_environment("SUPABASE_URL")
    key = _required_environment("SUPABASE_SERVICE_ROLE_KEY")
    store = SupabaseStore(url, key)
    source_folder = store.get_source_folder_by_google_folder_id(
        report.root.file_id
    )
    if source_folder is None:
        raise LookupError("Approved source folder is not registered")
    source_folder_id = source_folder["id"]
    store.validate_step7_schema()
    lookup_import_type = None
    lookup_test_batch = None
    if args.execute and args.limit == 10:
        lookup_import_type = "STEP6_INVENTORY_TEST_BATCH"
        lookup_test_batch = True
    elif args.execute and args.limit is None:
        lookup_import_type = "STEP6_INVENTORY"
        lookup_test_batch = False
    existing_run = store.find_scan_run_by_report_sha256(
        source_folder_id=source_folder_id,
        report_sha256=report.report_sha256,
        import_type=lookup_import_type,
        test_batch=lookup_test_batch,
    )

    if args.verify_only:
        if existing_run is None:
            print("Verification result: report has not been imported")
            return 1
        rows = store.read_imported_source_files(
            source_folder_id=source_folder_id,
            scan_run_id=existing_run["id"],
        )
        print(f"Verification result: {len(rows)} source_files rows")
        return 0

    scan_payload = build_scan_run_payload(
        report, source_folder_id=source_folder_id
    )
    proposed = build_source_file_payloads(
        report,
        source_folder_id=source_folder_id,
        scan_run_id="pending-scan-run",
    )
    if args.dry_run:
        current_rows = store.read_source_files_for_folder(source_folder_id)
        current_by_id = {
            row["google_file_id"]: row for row in current_rows
        }
        inserted = sum(
            payload["google_file_id"] not in current_by_id
            for payload in proposed
        )
        existing_payloads = [
            payload
            for payload in proposed
            if payload["google_file_id"] in current_by_id
        ]
        unchanged = sum(
            _same_inventory_values(
                payload, current_by_id[payload["google_file_id"]]
            )
            for payload in existing_payloads
        )
        updated = len(existing_payloads) - unchanged
        print("Connection result: connected (read-only dry run)")
        print("Source-folder lookup result: found")
        print(f"Live source-folder UUID: {source_folder_id}")
        print(f"Source name: {source_folder['source_name']}")
        print(f"Active status: {source_folder['active']}")
        print(f"Access status: {source_folder['access_status']}")
        print(f"Permission role: {source_folder['permission_role']}")
        print("Schema compatibility result: compatible")
        print(
            "Duplicate report fingerprint result: "
            + ("found" if existing_run is not None else "not found")
        )
        print(f"Current source_files row count: {len(current_rows)}")
        print(f"Proposed source_files payloads: {len(proposed)}")
        print(f"Would insert: {inserted}")
        print(f"Would update: {updated}")
        print(f"Semantically unchanged: {unchanged}")
        print("Dry-run validation result: passed")
        print("Database writes occurred: no")
        return 0

    all_payloads = build_source_file_payloads(
        report,
        source_folder_id=source_folder_id,
        scan_run_id="pending-scan-run",
    )
    if args.limit is not None:
        if args.limit != 10:
            raise RuntimeError("Only the approved 10-row test batch is allowed")
        selected = _select_test_batch(all_payloads, args.limit)
        scan_payload = _test_batch_scan_payload(
            scan_payload, selected, args.limit
        )
    else:
        selected = all_payloads
        scan_payload["metadata"]["test_batch"] = False

    reuse_test_run = (
        existing_run is not None
        and args.limit == 10
        and existing_run.get("metadata", {}).get("test_batch") is True
        and existing_run.get("metadata", {}).get("batch_limit") == 10
        and existing_run.get("metadata", {}).get("import_type")
        == "STEP6_INVENTORY_TEST_BATCH"
    )
    reuse_full_run = (
        existing_run is not None
        and args.limit is None
        and existing_run.get("metadata", {}).get("test_batch") is False
        and existing_run.get("metadata", {}).get("import_type")
        == "STEP6_INVENTORY"
    )
    if existing_run is not None and not (reuse_test_run or reuse_full_run):
        raise RuntimeError("This report fingerprint already has a scan run")
    if reuse_test_run or reuse_full_run:
        scan_run = existing_run
    else:
        scan_run = store.create_scan_run_from_payload(scan_payload)
    scan_run_id = scan_run["id"]
    payloads = [
        {**payload, "last_scan_run_id": scan_run_id}
        for payload in selected
    ]
    before_rows = store.read_source_files_for_folder(source_folder_id)
    before_ids = {row["google_file_id"] for row in before_rows}
    inserted_count = sum(
        payload["google_file_id"] not in before_ids for payload in payloads
    )
    updated_count = len(payloads) - inserted_count
    try:
        imported = store.batch_upsert_source_files(payloads)
        if len(imported) != len(payloads):
            raise RuntimeError("Supabase did not return every test-batch row")
        events = build_migration_event_payloads(
            report,
            source_folder_id=source_folder_id,
            scan_run_id=scan_run_id,
        )
        if events:
            store.record_migration_events(events)
        store.finalize_scan_run_from_payload(
            scan_run_id,
            {
                "status": "COMPLETED",
                "completed_at": report.generated_at_utc,
                "files_discovered": len(payloads),
                "files_taken": sum(
                    value["decision"] == "TAKE" for value in payloads
                ),
                "files_skipped": sum(
                    value["decision"] == "SKIP" for value in payloads
                ),
                "files_uploaded": 0,
                "duplicates_found": 0,
                "files_failed": 0,
            },
        )
    except Exception:
        store.finalize_scan_run_from_payload(
            scan_run_id,
            {
                "status": "FAILED",
                "completed_at": report.generated_at_utc,
                "files_failed": 1,
                "error_message": "Step 6 inventory test batch failed",
            },
        )
        raise

    verified = store.read_imported_source_files(
        source_folder_id=source_folder_id,
        scan_run_id=scan_run_id,
    )
    expected_ids = {payload["google_file_id"] for payload in payloads}
    verified = [
        row for row in verified if row["google_file_id"] in expected_ids
    ]
    current_folder_rows = store.read_source_files_for_folder(source_folder_id)
    take_ready = sum(
        row["decision"] == "TAKE"
        and row["processing_status"] == "READY"
        for row in verified
    )
    skip_skipped = sum(
        row["decision"] == "SKIP"
        and row["processing_status"] == "SKIPPED"
        for row in verified
    )
    folder_inserted = any(
        row.get("metadata", {}).get("step6_classification") == "folder"
        for row in verified
    )
    supported_count = sum(
        row.get("metadata", {}).get("step6_classification")
        == "supported_file"
        for row in current_folder_rows
    )
    unsupported_count = sum(
        row.get("metadata", {}).get("step6_classification")
        == "unsupported_file"
        for row in current_folder_rows
    )
    inaccessible_count = sum(
        row["processing_status"] == "INACCESSIBLE"
        for row in current_folder_rows
    )
    google_file_ids = [
        row["google_file_id"] for row in current_folder_rows
    ]
    duplicate_google_file_ids = (
        len(google_file_ids) - len(set(google_file_ids))
    )
    required_fields = (
        "google_file_id",
        "file_name",
        "source_folder_id",
        "decision",
        "processing_status",
        "first_seen_at",
        "last_seen_at",
        "metadata",
    )
    missing_required = sum(
        any(row.get(field) is None for field in required_fields)
        for row in verified
    )
    if (
        len(verified) != len(payloads)
        or take_ready + skip_skipped != len(payloads)
        or skip_skipped < 1
        or folder_inserted
        or any(row["last_scan_run_id"] != scan_run_id for row in verified)
    ):
        raise RuntimeError("Test-batch read-back verification failed")
    print(f"Scan run ID: {scan_run_id}")
    print(f"Execution inserted count: {inserted_count}")
    print(f"Execution updated count: {updated_count}")
    print(f"Batches executed: {(len(payloads) + 99) // 100}")
    print("Batch size: 100")
    print(f"Supported row count: {supported_count}")
    print(f"Unsupported row count: {unsupported_count}")
    print(f"TAKE / READY count: {take_ready}")
    print(f"SKIP / SKIPPED count: {skip_skipped}")
    print(f"Verified import rows: {len(verified)}")
    print(f"Total source-folder rows: {len(current_folder_rows)}")
    print(f"Inaccessible count: {inaccessible_count}")
    print(f"Rows linked to scan run: {len(verified)}")
    print(f"Duplicate google_file_id count: {duplicate_google_file_ids}")
    print(f"Missing required-field count: {missing_required}")
    print("All rows reference scan run: yes")
    print("Folder row inserted: no")
    print("Assets or asset_sources created: no")
    return 0


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is missing")
    return value


def _same_inventory_values(
    proposed: dict[str, Any],
    existing: dict[str, Any],
) -> bool:
    """Compare report-owned fields, excluding scan/observation bookkeeping."""
    fields = (
        "google_file_id",
        "file_name",
        "mime_type",
        "file_extension",
        "size_bytes",
        "md5_checksum",
        "drive_created_at",
        "drive_modified_at",
        "web_view_link",
        "thumbnail_link",
        "parent_google_folder_id",
        "relative_path",
        "decision",
        "processing_status",
        "processing_error",
        "skip_reason",
        "trashed",
        "is_missing",
    )
    timestamp_fields = {"drive_created_at", "drive_modified_at"}
    for field in fields:
        proposed_value = proposed.get(field)
        existing_value = existing.get(field)
        if field in timestamp_fields:
            proposed_value = _comparable_timestamp(proposed_value)
            existing_value = _comparable_timestamp(existing_value)
        if proposed_value != existing_value:
            return False
    return True


def _comparable_timestamp(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value


def _select_test_batch(
    payloads: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    """Select a stable mixed batch in report order."""
    supported = [
        payload for payload in payloads if payload["decision"] == "TAKE"
    ]
    unsupported = [
        payload for payload in payloads if payload["decision"] == "SKIP"
    ]
    if limit < 2 or len(supported) < limit - 1 or not unsupported:
        raise RuntimeError("A mixed deterministic test batch is unavailable")
    return supported[: limit - 1] + unsupported[:1]


def _test_batch_scan_payload(
    payload: dict[str, Any],
    selected: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    result = {**payload, "metadata": dict(payload["metadata"])}
    result.update(
        {
            "files_discovered": len(selected),
            "files_taken": sum(
                value["decision"] == "TAKE" for value in selected
            ),
            "files_skipped": sum(
                value["decision"] == "SKIP" for value in selected
            ),
            "files_uploaded": 0,
            "duplicates_found": 0,
            "files_failed": 0,
        }
    )
    result["metadata"].update(
        {
            "import_type": "STEP6_INVENTORY_TEST_BATCH",
            "test_batch": True,
            "batch_limit": limit,
        }
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
