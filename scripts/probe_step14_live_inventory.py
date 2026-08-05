"""Read-only live inventory classification for Step 14."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

from kdi_media.google_drive import FOLDER_CLASSIFICATION, create_readonly_drive_service, scan_folder_recursive
from kdi_media.incremental_sync import DriveMetadata, classify_inventory


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    load_dotenv(ROOT / ".env")
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    service = create_readonly_drive_service()
    sources = (
        client.table("source_folders")
        .select("id,google_folder_id")
        .eq("active", True)
        .order("id")
        .execute()
        .data
        or []
    )
    total = Counter()
    mismatches = Counter()
    per_source = []
    for source in sources:
        stored = (
            client.table("source_files")
            .select("id,google_file_id,drive_modified_at,size_bytes,mime_type,md5_checksum,is_missing")
            .eq("source_folder_id", source["id"])
            .execute()
            .data
            or []
        )
        scan = scan_folder_recursive(service, source["google_folder_id"])
        discovered = [
            DriveMetadata(
                google_file_id=item.file_id,
                modified_time=item.modified_time,
                size_bytes=item.size,
                mime_type=item.mime_type,
                md5_checksum=item.md5_checksum,
                accessible=item.accessibility_status == "accessible",
            )
            for item in scan.items
            if item.classification != FOLDER_CLASSIFICATION
        ]
        stored_by_id = {str(row["google_file_id"]): row for row in stored}
        for item in discovered:
            previous = stored_by_id.get(item.google_file_id)
            if previous is None:
                continue
            for field, old, new in (
                ("modified_time", previous.get("drive_modified_at"), item.modified_time),
                ("size_bytes", previous.get("size_bytes"), item.size_bytes),
                ("mime_type", previous.get("mime_type"), item.mime_type),
                ("md5_checksum", previous.get("md5_checksum"), item.md5_checksum),
            ):
                if field == "md5_checksum" and (old is None or new is None):
                    continue
                if old != new:
                    mismatches[field] += 1
        counts = Counter(value.value for value in classify_inventory(discovered, stored).values())
        total.update(counts)
        per_source.append({"stored": len(stored), "discovered": len(discovered), "classifications": dict(counts), "scan_errors": len(scan.errors)})
    report = {"sources": len(sources), "classifications": dict(total), "mismatch_fields": dict(mismatches), "per_source": per_source}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if len(sources) == 3 and not total.get("INACCESSIBLE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
