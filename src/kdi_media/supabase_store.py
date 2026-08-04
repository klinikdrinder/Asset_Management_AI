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

    def get_source_folder_by_google_folder_id(
        self,
        google_folder_id: str,
    ) -> dict[str, Any] | None:
        response = (
            self.client.table("source_folders")
            .select("*")
            .eq("google_folder_id", google_folder_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def get_source_folder_by_id(
        self,
        source_folder_id: str,
    ) -> dict[str, Any] | None:
        response = (
            self.client.table("source_folders")
            .select(
                "id,source_name,account_name,google_folder_id,active,"
                "access_status"
            )
            .eq("id", source_folder_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def list_active_source_folders(
        self,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            self.client.table("source_folders")
            .select(
                "id,source_name,account_name,google_folder_id,active,"
                "access_status"
            )
            .eq("active", True)
            .order("id")
        )
        if limit is not None:
            query = query.limit(limit)
        response = query.execute()
        return list(response.data or [])

    def validate_step7_schema(self) -> None:
        """Verify Step 7 columns through zero-row, read-only selections."""
        scan_run_columns = (
            "id,source_folder_id,run_mode,status,started_at,completed_at,"
            "files_discovered,files_taken,files_skipped,files_uploaded,"
            "duplicates_found,files_failed,metadata"
        )
        source_file_columns = (
            "id,source_folder_id,last_scan_run_id,google_file_id,file_name,"
            "mime_type,file_extension,size_bytes,md5_checksum,"
            "drive_created_at,drive_modified_at,web_view_link,thumbnail_link,"
            "parent_google_folder_id,relative_path,decision,"
            "processing_status,processing_error,skip_reason,trashed,"
            "is_missing,first_seen_at,last_seen_at,metadata"
        )
        (
            self.client.table("scan_runs")
            .select(scan_run_columns)
            .limit(0)
            .execute()
        )
        (
            self.client.table("source_files")
            .select(source_file_columns)
            .limit(0)
            .execute()
        )

    def read_source_files_for_folder(
        self,
        source_folder_id: str,
    ) -> list[dict[str, Any]]:
        """Read source files needed for a Step 7 dry-run comparison."""
        columns = (
            "source_folder_id,google_file_id,file_name,mime_type,"
            "file_extension,size_bytes,"
            "md5_checksum,drive_created_at,drive_modified_at,web_view_link,"
            "thumbnail_link,parent_google_folder_id,relative_path,decision,"
            "processing_status,processing_error,skip_reason,trashed,"
            "is_missing,first_seen_at,last_seen_at,metadata"
        )
        response = (
            self.client.table("source_files")
            .select(columns)
            .eq("source_folder_id", source_folder_id)
            .order("google_file_id")
            .execute()
        )
        return list(response.data or [])

    def read_step8_preview_rows(
        self,
        source_folder_id: str,
    ) -> list[dict[str, Any]]:
        """Read only the columns required by the Step 8 decision preview."""
        columns = (
            "id,source_folder_id,google_file_id,file_name,mime_type,"
            "file_extension,size_bytes,relative_path,decision,"
            "processing_status,skip_reason,trashed,is_missing,metadata"
        )
        response = (
            self.client.table("source_files")
            .select(columns)
            .eq("source_folder_id", source_folder_id)
            .order("google_file_id")
            .execute()
        )
        return list(response.data or [])

    def apply_step8_supported_document_decisions(
        self,
        *,
        source_folder_id: str,
        source_file_ids: list[str],
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Conditionally update the approved PDF/PPTX rows in one statement.

        Callers must complete the Step 8 preflight first.  The server-side
        filters protect identity, current decision/status, and both approved
        extension/MIME pairs from changes between preflight and update.
        """
        if len(source_file_ids) != 2 or len(set(source_file_ids)) != 2:
            raise ValueError("Exactly two distinct source-file IDs are required")
        approved_pairs = (
            "and(file_extension.eq.pdf,mime_type.eq.application/pdf),"
            "and(file_extension.eq.pptx,mime_type.eq."
            "application/vnd.openxmlformats-officedocument."
            "presentationml.presentation)"
        )
        response = (
            self.client.table("source_files")
            .update(
                {
                    "decision": "TAKE",
                    "processing_status": "READY",
                    "skip_reason": None,
                    "metadata": metadata,
                }
            )
            .eq("source_folder_id", source_folder_id)
            .in_("id", source_file_ids)
            .eq("decision", "SKIP")
            .eq("processing_status", "SKIPPED")
            .or_(approved_pairs)
            .execute()
        )
        return list(response.data or [])

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

    def create_scan_run_from_payload(
        self,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.client.table("scan_runs").insert(values).execute()
        rows = response.data or []
        if not rows:
            raise RuntimeError("Supabase did not return the created scan run")
        return rows[0]

    def find_scan_run_by_report_sha256(
        self,
        *,
        source_folder_id: str,
        report_sha256: str,
        import_type: str | None = None,
        test_batch: bool | None = None,
    ) -> dict[str, Any] | None:
        query = (
            self.client.table("scan_runs")
            .select("*")
            .eq("source_folder_id", source_folder_id)
            .contains("metadata", {"report_sha256": report_sha256})
        )
        if import_type is not None:
            query = query.contains("metadata", {"import_type": import_type})
        if test_batch is not None:
            query = query.contains("metadata", {"test_batch": test_batch})
        response = query.order("created_at", desc=True).limit(1).execute()
        rows = response.data or []
        return rows[0] if rows else None

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

    def finalize_scan_run_from_payload(
        self,
        scan_run_id: str,
        values: dict[str, Any],
    ) -> None:
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

    def batch_upsert_source_files(
        self,
        values: list[dict[str, Any]],
        *,
        batch_size: int = 100,
    ) -> list[dict[str, Any]]:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if not values:
            return []

        prepared = [dict(item) for item in values]
        folder_ids = {item["source_folder_id"] for item in prepared}
        if len(folder_ids) != 1:
            raise ValueError("A source-file batch must use one source folder")
        source_folder_id = next(iter(folder_ids))
        google_file_ids = [item["google_file_id"] for item in prepared]
        response = (
            self.client.table("source_files")
            .select("google_file_id,first_seen_at")
            .eq("source_folder_id", source_folder_id)
            .in_("google_file_id", google_file_ids)
            .execute()
        )
        existing_first_seen = {
            row["google_file_id"]: row["first_seen_at"]
            for row in (response.data or [])
        }
        for item in prepared:
            observed_at = item.get("last_seen_at") or utc_now()
            first_seen_at = existing_first_seen.get(item["google_file_id"])
            if first_seen_at is None:
                item["first_seen_at"] = observed_at
                item["last_seen_at"] = observed_at
            else:
                item["first_seen_at"] = first_seen_at
                item["last_seen_at"] = _latest_timestamp(
                    first_seen_at, observed_at
                )

        imported: list[dict[str, Any]] = []
        for start in range(0, len(prepared), batch_size):
            batch = prepared[start : start + batch_size]
            try:
                batch_response = (
                    self.client.table("source_files")
                    .upsert(
                        batch,
                        on_conflict="source_folder_id,google_file_id",
                    )
                    .execute()
                )
            except Exception as exc:
                batch_number = (start // batch_size) + 1
                raise RuntimeError(
                    f"Source-file batch {batch_number} failed"
                ) from exc
            imported.extend(batch_response.data or [])
        return imported

    def read_imported_source_files(
        self,
        *,
        source_folder_id: str,
        scan_run_id: str,
    ) -> list[dict[str, Any]]:
        response = (
            self.client.table("source_files")
            .select("*")
            .eq("source_folder_id", source_folder_id)
            .eq("last_scan_run_id", scan_run_id)
            .order("google_file_id")
            .execute()
        )
        return list(response.data or [])

    def record_migration_events(
        self,
        values: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not values:
            return []
        response = (
            self.client.table("migration_events").insert(values).execute()
        )
        return list(response.data or [])

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
