"""Read-only Step 8 preview over existing Supabase ``source_files`` rows.

The command performs one metadata SELECT and never inserts, updates, deletes,
upserts, invokes Google Drive, creates audit events, or touches media.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import os
import sys
from typing import Any, Iterable, Mapping
from uuid import UUID


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kdi_media.rules import (  # noqa: E402
    FOLDER_MIME_TYPE,
    FileRuleInput,
    ReasonCode,
    evaluate_file,
    normalize_extension,
    normalize_mime_type,
)


@dataclass(frozen=True)
class ChangeCategory:
    extension: str
    mime_type: str
    current_decision: str
    current_status: str
    proposed_decision: str
    proposed_status: str
    reason_code: str
    accepted_for_ai_analysis: bool


@dataclass(frozen=True)
class SupabasePreview:
    total_rows: int
    current_take_ready: int
    current_skip_skipped: int
    proposed_take_ready: int
    proposed_skip_skipped: int
    unchanged: int
    changed: int
    inaccessible: int
    folder_rows: int
    duplicate_identities: int
    google_native_skip: int
    heic_skip: int
    reasons: tuple[tuple[str, int], ...]
    changes: tuple[tuple[ChangeCategory, int], ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview Step 8 decisions using read-only Supabase rows."
    )
    parser.add_argument("--source-folder-id", required=True, type=_uuid)
    parser.add_argument("--expected-total", required=True, type=int)
    parser.add_argument("--expected-changes", required=True, type=int)
    return parser


def build_preview(rows: Iterable[Mapping[str, Any]]) -> SupabasePreview:
    row_list = list(rows)
    reasons: Counter[str] = Counter()
    changes: Counter[ChangeCategory] = Counter()
    identities: Counter[tuple[str, str]] = Counter()
    current_take_ready = 0
    current_skip_skipped = 0
    proposed_take_ready = 0
    proposed_skip_skipped = 0
    unchanged = 0
    inaccessible = 0
    folder_rows = 0
    google_native_skip = 0
    heic_skip = 0

    for row in row_list:
        metadata = row.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        mime_type = normalize_mime_type(row.get("mime_type"))
        extension = normalize_extension(row.get("file_extension"))
        is_folder = (
            mime_type == FOLDER_MIME_TYPE
            or metadata.get("step6_classification") == "folder"
        )
        accessibility = metadata.get("step6_accessibility_status")
        if row.get("processing_status") == "INACCESSIBLE":
            accessibility = "inaccessible"
        if accessibility not in {"accessible", "inaccessible"}:
            accessibility = "accessible"

        proposed = evaluate_file(
            FileRuleInput(
                file_name=row.get("file_name"),
                mime_type=row.get("mime_type"),
                file_extension=row.get("file_extension"),
                size_bytes=row.get("size_bytes"),
                relative_path=row.get("relative_path"),
                accessibility_status=accessibility,
                trashed=row.get("trashed"),
                is_missing=row.get("is_missing"),
                is_folder=is_folder,
            )
        )

        current_decision = str(row.get("decision") or "")
        current_status = str(row.get("processing_status") or "")
        if current_decision == "TAKE" and current_status == "READY":
            current_take_ready += 1
        if current_decision == "SKIP" and current_status == "SKIPPED":
            current_skip_skipped += 1
        if (
            proposed.automatic_decision == "TAKE"
            and proposed.target_processing_status == "READY"
        ):
            proposed_take_ready += 1
        if (
            proposed.automatic_decision == "SKIP"
            and proposed.target_processing_status == "SKIPPED"
        ):
            proposed_skip_skipped += 1

        reasons[proposed.reason_code.value] += 1
        if proposed.reason_code == ReasonCode.INACCESSIBLE:
            inaccessible += 1
        if proposed.reason_code == ReasonCode.FOLDER_ITEM:
            folder_rows += 1
        if (
            proposed.reason_code == ReasonCode.GOOGLE_NATIVE_FILE
            and proposed.automatic_decision == "SKIP"
        ):
            google_native_skip += 1
        if (
            extension == "heic"
            and proposed.automatic_decision == "SKIP"
        ):
            heic_skip += 1

        identity = (
            str(row.get("source_folder_id") or ""),
            str(row.get("google_file_id") or ""),
        )
        identities[identity] += 1

        if (
            current_decision == proposed.automatic_decision
            and current_status == proposed.target_processing_status
        ):
            unchanged += 1
        else:
            changes[
                ChangeCategory(
                    extension=extension or "(missing)",
                    mime_type=mime_type or "(missing)",
                    current_decision=current_decision or "(missing)",
                    current_status=current_status or "(missing)",
                    proposed_decision=proposed.automatic_decision,
                    proposed_status=proposed.target_processing_status,
                    reason_code=proposed.reason_code.value,
                    accepted_for_ai_analysis=(
                        proposed.accepted_for_ai_analysis
                    ),
                )
            ] += 1

    duplicate_identities = sum(
        count - 1 for count in identities.values() if count > 1
    )
    ordered_changes = tuple(
        sorted(
            changes.items(),
            key=lambda value: (
                value[0].extension,
                value[0].mime_type,
                value[0].current_decision,
            ),
        )
    )
    return SupabasePreview(
        total_rows=len(row_list),
        current_take_ready=current_take_ready,
        current_skip_skipped=current_skip_skipped,
        proposed_take_ready=proposed_take_ready,
        proposed_skip_skipped=proposed_skip_skipped,
        unchanged=unchanged,
        changed=len(row_list) - unchanged,
        inaccessible=inaccessible,
        folder_rows=folder_rows,
        duplicate_identities=duplicate_identities,
        google_native_skip=google_native_skip,
        heic_skip=heic_skip,
        reasons=tuple(sorted(reasons.items())),
        changes=ordered_changes,
    )


def preview_passes(
    preview: SupabasePreview,
    *,
    expected_total: int,
    expected_changes: int,
) -> bool:
    change_extensions = Counter()
    for change, count in preview.changes:
        change_extensions[change.extension] += count
    return all(
        (
            preview.total_rows == expected_total,
            preview.current_take_ready == 290,
            preview.current_skip_skipped == 10,
            preview.proposed_take_ready == 292,
            preview.proposed_skip_skipped == 8,
            preview.changed == expected_changes,
            preview.unchanged == expected_total - expected_changes,
            change_extensions == Counter({"pdf": 1, "pptx": 1}),
            preview.google_native_skip == 6,
            preview.heic_skip == 2,
            preview.inaccessible == 0,
            preview.folder_rows == 0,
            preview.duplicate_identities == 0,
        )
    )


def print_preview(preview: SupabasePreview, *, passed: bool) -> None:
    print("Supabase connection result: connected (read-only)")
    print(f"Total rows read: {preview.total_rows}")
    print(f"Current TAKE / READY: {preview.current_take_ready}")
    print(f"Current SKIP / SKIPPED: {preview.current_skip_skipped}")
    print(f"Proposed TAKE / READY: {preview.proposed_take_ready}")
    print(f"Proposed SKIP / SKIPPED: {preview.proposed_skip_skipped}")
    print(f"Changed count: {preview.changed}")
    print(f"Unchanged count: {preview.unchanged}")
    print("Reason-code distribution:")
    for reason, count in preview.reasons:
        print(f"  {reason}: {count}")
    print("Safe change distribution:")
    for change, count in preview.changes:
        print(
            "  "
            f"extension={change.extension} "
            f"mime_type={change.mime_type} "
            f"current={change.current_decision}/{change.current_status} "
            f"proposed={change.proposed_decision}/"
            f"{change.proposed_status} "
            f"reason_code={change.reason_code} "
            f"accepted_for_ai_analysis="
            f"{str(change.accepted_for_ai_analysis).lower()} "
            f"count={count}"
        )
    print(f"Google-native SKIP count: {preview.google_native_skip}")
    print(f"HEIC SKIP count: {preview.heic_skip}")
    print(f"Inaccessible row count: {preview.inaccessible}")
    print(f"Folder row count: {preview.folder_rows}")
    print(f"Duplicate identity count: {preview.duplicate_identities}")
    print(f"Final preview: {'PASS' if passed else 'FAIL'}")
    print("Supabase writes occurred: no")
    print("Audit events created: no")
    print("Google Drive access occurred: no")
    print("Assets or asset_sources changed: no")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expected_total <= 0 or args.expected_changes < 0:
        print("Expected counts are invalid", file=sys.stderr)
        return 2
    try:
        from dotenv import load_dotenv
        from kdi_media.supabase_store import SupabaseStore

        load_dotenv(PROJECT_ROOT / ".env")
        url = _required_environment("SUPABASE_URL")
        key = _required_environment("SUPABASE_SERVICE_ROLE_KEY")
        store = SupabaseStore(url, key)
        rows = store.read_step8_preview_rows(str(args.source_folder_id))
        preview = build_preview(rows)
    except Exception:
        print(
            "Supabase connection result: failed without exposing "
            "connection or row data",
            file=sys.stderr,
        )
        print("Supabase writes occurred: no", file=sys.stderr)
        return 1

    passed = preview_passes(
        preview,
        expected_total=args.expected_total,
        expected_changes=args.expected_changes,
    )
    print_preview(preview, passed=passed)
    return 0 if passed else 1


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--source-folder-id must be a UUID"
        ) from exc


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError("Required Supabase configuration is missing")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
