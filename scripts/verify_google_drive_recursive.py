"""Run an approved, metadata-only recursive Google Drive verification scan."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
REPORT_ROOT = PROJECT_ROOT / "tmp" / "step6-recursive-scan"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kdi_media.google_drive import (  # noqa: E402
    GoogleDriveError,
    RecursiveScanReport,
    create_readonly_drive_service,
    scan_folder_recursive,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recursively verify metadata in the approved Google Drive folder "
            "using read-only OAuth."
        )
    )
    parser.add_argument("--folder-id", required=True)
    return parser


def write_recursive_scan_reports(
    report: RecursiveScanReport,
    *,
    report_root: Path = REPORT_ROOT,
    timestamp: str | None = None,
) -> tuple[Path, Path]:
    """Write a new timestamped JSON/CSV report pair without overwriting."""
    report_root.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc)
    stamp = timestamp or generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    json_path = report_root / f"step6-recursive-{stamp}.json"
    csv_path = report_root / f"step6-recursive-{stamp}.csv"
    if json_path.exists() or csv_path.exists():
        raise FileExistsError("Timestamped scan report already exists")

    json_payload = {
        "generated_at_utc": generated_at.isoformat(),
        "root": {
            "file_id": report.root.id,
            "name": report.root.name,
            "mime_type": report.root.mime_type,
        },
        "summary": asdict(report.summary),
        "items": [asdict(item) for item in report.items],
        "errors": [asdict(error) for error in report.errors],
    }
    json_path.write_text(
        json.dumps(json_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    fieldnames = [
        "file_id",
        "name",
        "mime_type",
        "file_extension",
        "size",
        "created_time",
        "modified_time",
        "parent_folder_id",
        "relative_folder_path",
        "web_view_link",
        "accessibility_status",
        "classification",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for item in report.items:
            writer.writerow(asdict(item))

    return json_path, csv_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    folder_id = args.folder_id.strip()
    if not folder_id:
        print("Verification failed: folder ID is required.", file=sys.stderr)
        return 2

    try:
        service = create_readonly_drive_service()
        report = scan_folder_recursive(service, folder_id)
        json_path, csv_path = write_recursive_scan_reports(report)
    except GoogleDriveError as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print(
            "Verification failed: local reports could not be written.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "Verification failed due to an unexpected non-secret error.",
            file=sys.stderr,
        )
        return 1

    summary = report.summary
    print(f"Folder name: {report.root.name}")
    print(f"Folder ID: {report.root.id}")
    print(f"Folders scanned: {summary.folders_scanned}")
    print(f"Total items discovered: {summary.total_items_discovered}")
    print(f"Total files found: {summary.total_files_found}")
    print(f"Supported files: {summary.supported_files}")
    print(f"Unsupported files: {summary.unsupported_files}")
    print(f"Inaccessible items: {summary.inaccessible_items}")
    print(f"Errors: {summary.errors}")
    print(f"API pages requested: {summary.api_pages_requested}")
    print(f"JSON report: {json_path.relative_to(PROJECT_ROOT)}")
    print(f"CSV report: {csv_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
