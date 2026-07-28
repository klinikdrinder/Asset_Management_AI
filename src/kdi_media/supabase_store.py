"""Supabase persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseStore:
    def __init__(self, url: str, service_role_key: str) -> None:
        self.client: Client = create_client(url, service_role_key)

    def get_active_source_folder(self, source_name: str) -> dict[str, Any]:
        response = (
            self.client.table("source_folders")
            .select("*")
            .eq("source_name", source_name)
            .eq("active", True)
            .limit(2)
            .execute()
        )
        rows = response.data or []
        if not rows:
            raise LookupError(
                f"No active source folder named {source_name!r} was found"
            )
        if len(rows) > 1:
            raise LookupError(
                f"Multiple active source folders named {source_name!r} found"
            )
        return rows[0]

    def update_source_folder(
        self,
        source_folder_id: str,
        values: dict[str, Any],
    ) -> None:
        (
            self.client.table("source_folders")
            .update(values)
            .eq("id", source_folder_id)
            .execute()
        )

    def create_scan_run(
        self,
        source_folder_id: str,
        dry_run: bool,
    ) -> dict[str, Any]:
        response = (
            self.client.table("scan_runs")
            .insert(
                {
                    "source_folder_id": source_folder_id,
                    "run_mode": "DRY_RUN" if dry_run else "MIGRATION",
                    "status": "RUNNING",
                    "started_at": utc_now(),
                    "metadata": {"dry_run": dry_run},
                }
            )
            .execute()
        )
        return response.data[0]

    def finish_scan_run(
        self,
        scan_run_id: str,
        *,
        status: str,
        counts: dict[str, int],
        metadata: dict[str, Any],
        error_message: str | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "completed_at": utc_now(),
            "files_discovered": counts["discovered"],
            "files_taken": counts["taken"],
            "files_skipped": counts["skipped"],
            "files_uploaded": counts["uploaded"],
            "duplicates_found": counts["duplicate"],
            "files_failed": counts["failed"],
            "metadata": metadata,
            "error_message": error_message,
        }
        (
            self.client.table("scan_runs")
            .update(values)
            .eq("id", scan_run_id)
            .execute()
        )

    def upsert_source_file(
        self,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        observed_at = values.get("last_seen_at") or utc_now()
        existing = self.get_source_file(
            source_folder_id=values["source_folder_id"],
            google_file_id=values["google_file_id"],
        )
        if existing:
            first_seen_at = existing["first_seen_at"]
            values["first_seen_at"] = first_seen_at
            values["last_seen_at"] = _latest_timestamp(
                first_seen_at,
                observed_at,
            )
        else:
            values["first_seen_at"] = observed_at
            values["last_seen_at"] = observed_at

        response = (
            self.client.table("source_files")
            .upsert(
                values,
                on_conflict="source_folder_id,google_file_id",
            )
            .execute()
        )
        return response.data[0]

    def get_source_file(
        self,
        *,
        source_folder_id: str,
        google_file_id: str,
    ) -> dict[str, Any] | None:
        response = (
            self.client.table("source_files")
            .select("*")
            .eq("source_folder_id", source_folder_id)
            .eq("google_file_id", google_file_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None
    def find_exact_duplicate(
        self,
        *,
        md5_checksum: str,
        size_bytes: int,
        current_source_file_id: str,
    ) -> dict[str, Any] | None:
        response = (
            self.client.table("source_files")
            .select(
                "id,source_folder_id,google_file_id,file_name,"
                "md5_checksum,size_bytes,processing_status,metadata"
            )
            .eq("md5_checksum", md5_checksum)
            .eq("size_bytes", size_bytes)
            .eq("processing_status", "UPLOADED")
            .neq("id", current_source_file_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None


def _latest_timestamp(first: str, second: str) -> str:
    first_value = datetime.fromisoformat(first.replace("Z", "+00:00"))
    second_value = datetime.fromisoformat(second.replace("Z", "+00:00"))
    return max(first_value, second_value).isoformat()
