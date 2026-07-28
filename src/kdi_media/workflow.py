"""One-folder KDI media migration workflow."""

from __future__ import annotations

from collections import Counter
from typing import Any

from googleapiclient.errors import HttpError

from .config import Settings
from .drive_client import DriveClient
from .rules import classify
from .supabase_store import SupabaseStore, utc_now


def _permission_role(folder: dict[str, Any]) -> str:
    capabilities = folder.get("capabilities", {})
    if capabilities.get("canEdit"):
        return "EDITOR"
    if capabilities.get("canComment"):
        return "COMMENTER"
    return "VIEWER"


def _source_file_values(
    *,
    source_folder_id: str,
    scan_run_id: str,
    item: dict[str, Any],
    relative_path: str,
    decision: str,
    status: str,
    reason: str,
) -> dict[str, Any]:
    parents = item.get("parents") or []
    size = item.get("size")
    return {
        "source_folder_id": source_folder_id,
        "last_scan_run_id": scan_run_id,
        "google_file_id": item["id"],
        "file_name": item.get("name") or item["id"],
        "mime_type": item.get("mimeType"),
        "file_extension": item.get("fileExtension"),
        "size_bytes": int(size) if size is not None else None,
        "md5_checksum": item.get("md5Checksum"),
        "drive_created_at": item.get("createdTime"),
        "drive_modified_at": item.get("modifiedTime"),
        "web_view_link": item.get("webViewLink"),
        "thumbnail_link": item.get("thumbnailLink"),
        "parent_google_folder_id": parents[0] if parents else None,
        "relative_path": relative_path,
        "decision": decision,
        "processing_status": status,
        "processing_error": None,
        "skip_reason": reason if decision == "SKIP" else None,
        "trashed": bool(item.get("trashed", False)),
        "is_missing": False,
        "last_seen_at": utc_now(),
        "metadata": {"rule_reason": reason},
    }


def run(
    settings: Settings,
    store: SupabaseStore,
    drive: DriveClient,
) -> int:
    print(f"Loading active source folder: {settings.source_folder_name}")
    source_folder = store.get_active_source_folder(
        settings.source_folder_name
    )
    source_folder_id = source_folder["id"]
    google_folder_id = source_folder["google_folder_id"]
    scan_run = store.create_scan_run(source_folder_id, settings.dry_run)
    scan_run_id = scan_run["id"]
    counts: Counter[str] = Counter()

    print(
        f"Starting {'DRY RUN' if settings.dry_run else 'LIVE COPY'} "
        f"scan {scan_run_id}"
    )

    try:
        drive_folder = drive.get_folder(google_folder_id)
        store.update_source_folder(
            source_folder_id,
            {
                "access_status": "ACCESSIBLE",
                "permission_role": _permission_role(drive_folder),
                "last_access_checked_at": utc_now(),
                "last_scan_at": utc_now(),
            },
        )
    except Exception as exc:
        message = f"Folder access check failed: {exc}"
        print(f"ERROR: {message}")
        store.update_source_folder(
            source_folder_id,
            {
                "access_status": "INACCESSIBLE",
                "last_access_checked_at": utc_now(),
                "last_scan_at": utc_now(),
            },
        )
        store.finish_scan_run(
            scan_run_id,
            status="FAILED",
            counts=_normalized_counts(counts),
            metadata={"dry_run": settings.dry_run},
            error_message=message,
        )
        return 1

    try:
        drive.get_folder(settings.destination_folder_id)
    except Exception as exc:
        message = f"Destination folder access check failed: {exc}"
        print(f"ERROR: {message}")
        store.finish_scan_run(
            scan_run_id,
            status="FAILED",
            counts=_normalized_counts(counts),
            metadata={"dry_run": settings.dry_run},
            error_message=message,
        )
        return 1

    try:
        for item, relative_path in drive.iter_files_recursive(
            google_folder_id
        ):
            counts["discovered"] += 1
            try:
                _process_file(
                    settings=settings,
                    store=store,
                    drive=drive,
                    source_folder_id=source_folder_id,
                    scan_run_id=scan_run_id,
                    item=item,
                    relative_path=relative_path,
                    counts=counts,
                )
            except Exception as exc:
                counts["failed"] += 1
                print(
                    f"ERROR: {relative_path or item.get('id')}: {exc}"
                )
                _save_unexpected_failure(
                    store,
                    source_folder_id,
                    scan_run_id,
                    item,
                    relative_path,
                    exc,
                )
    except HttpError as exc:
        counts["failed"] += 1
        print(f"ERROR: Drive traversal stopped early: {exc}")

    final_status = (
        "COMPLETED_WITH_ERRORS" if counts["failed"] else "COMPLETED"
    )
    completed_at = utc_now()
    store.finish_scan_run(
        scan_run_id,
        status=final_status,
        counts=_normalized_counts(counts),
        metadata={
            "dry_run": settings.dry_run,
            "unique_files": counts["unique"],
            "duplicate_files": counts["duplicate"],
            "uploaded_files": counts["uploaded"],
        },
    )
    folder_update: dict[str, Any] = {
        "last_scan_at": completed_at,
    }
    if not counts["failed"]:
        folder_update["last_successful_scan_at"] = completed_at
    store.update_source_folder(source_folder_id, folder_update)

    print(
        "Finished "
        f"status={final_status} discovered={counts['discovered']} "
        f"taken={counts['taken']} skipped={counts['skipped']} "
        f"duplicates={counts['duplicate']} uploaded={counts['uploaded']} "
        f"failed={counts['failed']}"
    )
    return 0 if not counts["failed"] else 2


def _process_file(
    *,
    settings: Settings,
    store: SupabaseStore,
    drive: DriveClient,
    source_folder_id: str,
    scan_run_id: str,
    item: dict[str, Any],
    relative_path: str,
    counts: Counter[str],
) -> None:
    decision, reason = classify(item)
    initial_status = "SKIPPED" if decision == "SKIP" else "READY"
    existing_source_file = store.get_source_file(
        source_folder_id=source_folder_id,
        google_file_id=item["id"],
    )
    values = _source_file_values(
        source_folder_id=source_folder_id,
        scan_run_id=scan_run_id,
        item=item,
        relative_path=relative_path,
        decision=decision,
        status=initial_status,
        reason=reason,
    )
    source_file = store.upsert_source_file(values)

    if decision == "SKIP":
        counts["skipped"] += 1
        print(f"SKIP: {relative_path} ({reason})")
        return

    counts["taken"] += 1
    md5_checksum = item.get("md5Checksum")
    size = item.get("size")
    if not md5_checksum or size is None:
        raise ValueError(
            "Exact duplicate check requires both md5Checksum and file size"
        )

    duplicate = store.find_exact_duplicate(
        md5_checksum=md5_checksum,
        size_bytes=int(size),
        current_source_file_id=source_file["id"],
    )
    if duplicate:
        counts["duplicate"] += 1
        values.update(
            {
                "processing_status": "DUPLICATE",
                "duplicate_of_source_file_id": duplicate["id"],
                "metadata": {
                    "rule_reason": reason,
                    "duplicate_of_source_file_id": duplicate["id"],
                    "duplicate_of_google_file_id": duplicate[
                        "google_file_id"
                    ],
                },
            }
        )
        store.upsert_source_file(values)
        print(
            f"DUPLICATE: {relative_path} matches "
            f"{duplicate['file_name']}"
        )
        return

    counts["unique"] += 1
    if settings.dry_run:
        values["metadata"] = {
            "rule_reason": reason,
            "dry_run": True,
            "would_copy_to_folder_id": settings.destination_folder_id,
        }
        store.upsert_source_file(values)
        print(f"TAKE (dry run): {relative_path}")
        return

    if (
        existing_source_file
        and existing_source_file.get("processing_status") == "UPLOADED"
        and existing_source_file.get("md5_checksum") == md5_checksum
        and existing_source_file.get("size_bytes") == int(size)
        and existing_source_file.get("destination_file_id")
    ):
        counts["uploaded"] += 1
        values.update(
            {
                "processing_status": "UPLOADED",
                "destination_file_id": existing_source_file[
                    "destination_file_id"
                ],
                "destination_web_view_link": existing_source_file.get(
                    "destination_web_view_link"
                ),
                "uploaded_at": existing_source_file.get("uploaded_at"),
                "metadata": existing_source_file["metadata"],
            }
        )
        store.upsert_source_file(values)
        print(f"ALREADY UPLOADED: {relative_path}")
        return

    existing_copy = drive.find_existing_copy(
        source_google_file_id=item["id"],
        source_folder_id=source_folder_id,
        destination_folder_id=settings.destination_folder_id,
    )
    if existing_copy:
        counts["uploaded"] += 1
        values.update(
            {
                "processing_status": "UPLOADED",
                "destination_file_id": existing_copy["id"],
                "destination_web_view_link": existing_copy.get(
                    "webViewLink"
                ),
                "uploaded_at": utc_now(),
                "metadata": {
                    "rule_reason": reason,
                    "destination_google_file_id": existing_copy["id"],
                    "destination_web_view_link": existing_copy.get(
                        "webViewLink"
                    ),
                    "reconciled_at": utc_now(),
                },
            }
        )
        store.upsert_source_file(values)
        print(f"RECONCILED EXISTING COPY: {relative_path}")
        return

    values["processing_status"] = "UPLOADING"
    store.upsert_source_file(values)
    copied = drive.copy_file(
        item["id"],
        settings.destination_folder_id,
        item.get("name") or item["id"],
        source_folder_id,
    )
    counts["uploaded"] += 1
    values.update(
        {
            "processing_status": "UPLOADED",
            "destination_file_id": copied["id"],
            "destination_web_view_link": copied.get("webViewLink"),
            "uploaded_at": utc_now(),
            "metadata": {
                "rule_reason": reason,
                "destination_google_file_id": copied["id"],
                "destination_web_view_link": copied.get("webViewLink"),
                "uploaded_at": utc_now(),
            },
        }
    )
    store.upsert_source_file(values)
    print(f"UPLOADED: {relative_path} -> {copied['id']}")


def _save_unexpected_failure(
    store: SupabaseStore,
    source_folder_id: str,
    scan_run_id: str,
    item: dict[str, Any],
    relative_path: str,
    exc: Exception,
) -> None:
    try:
        decision, reason = classify(item)
        values = _source_file_values(
            source_folder_id=source_folder_id,
            scan_run_id=scan_run_id,
            item=item,
            relative_path=relative_path,
            decision=decision,
            status="FAILED",
            reason=reason,
        )
        values["processing_error"] = str(exc)
        store.upsert_source_file(values)
    except Exception as persistence_exc:
        print(
            "ERROR: Could not save file failure to Supabase: "
            f"{persistence_exc}"
        )


def _normalized_counts(counts: Counter[str]) -> dict[str, int]:
    return {
        "discovered": counts["discovered"],
        "taken": counts["taken"],
        "skipped": counts["skipped"],
        "uploaded": counts["uploaded"],
        "duplicate": counts["duplicate"],
        "failed": counts["failed"],
    }
