"""Apply only the two approved Step 8 PDF/PPTX decision changes.

The command performs a read-only preflight, at most one narrow conditional
Supabase update statement, and a read-only reconciliation. It has no Google
Drive, media, SQL, migration, asset, asset-source, or audit-event operations.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import sys
from typing import Any, Mapping
from uuid import UUID


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kdi_media.rules import (  # noqa: E402
    FORMAT_POLICY,
    RULE_VERSION,
    FileRuleInput,
    ReasonCode,
    evaluate_file,
    normalize_extension,
    normalize_mime_type,
)
from scripts.preview_step8_supabase import (  # noqa: E402
    SupabasePreview,
    build_preview,
)


APPROVED_EXTENSIONS = ("pdf", "pptx")
OWNED_FIELDS = frozenset(
    {"decision", "processing_status", "skip_reason", "metadata"}
)


class ControlledApplyError(RuntimeError):
    """Safe failure that never includes row identity or patient metadata."""


@dataclass(frozen=True)
class ApplyPlan:
    mode: str
    source_file_ids: tuple[str, ...]
    merged_metadata: Mapping[str, Any] | None


@dataclass(frozen=True)
class ApplyResult:
    changed: int
    unchanged: int
    pdf_updated: int
    pptx_updated: int
    pdf_take: int
    pptx_take: int
    preview: SupabasePreview
    unrelated_fields_changed: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the two approved Step 8 PDF/PPTX changes with "
            "conditional preconditions."
        )
    )
    parser.add_argument("--source-folder-id", required=True, type=_uuid)
    parser.add_argument("--expected-total", required=True, type=int)
    return parser


def build_apply_plan(
    rows: list[Mapping[str, Any]],
    *,
    source_folder_id: str,
    evaluated_at: str,
) -> ApplyPlan:
    if len(rows) != 300:
        raise ControlledApplyError("Preflight total is not 300")
    selected: list[Mapping[str, Any]] = []
    by_extension: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        extension = normalize_extension(row.get("file_extension"))
        if extension not in APPROVED_EXTENSIONS:
            continue
        policy = FORMAT_POLICY[extension]
        if normalize_mime_type(row.get("mime_type")) != policy.required_mime_type:
            continue
        if str(row.get("source_folder_id")) != source_folder_id:
            raise ControlledApplyError("Approved row source-folder mismatch")
        if extension in by_extension:
            raise ControlledApplyError("Approved format row is not unique")
        by_extension[extension] = row
        selected.append(row)

    if set(by_extension) != set(APPROVED_EXTENSIONS) or len(selected) != 2:
        raise ControlledApplyError("Exactly one PDF and one PPTX are required")

    evaluations = {
        extension: _evaluate_row(row)
        for extension, row in by_extension.items()
    }
    if any(
        value.automatic_decision != "TAKE"
        or value.target_processing_status != "READY"
        or value.reason_code != ReasonCode.SUPPORTED_FORMAT
        or value.rule_version != RULE_VERSION
        or value.accepted_for_ai_analysis
        for value in evaluations.values()
    ):
        raise ControlledApplyError(
            "Approved document no longer evaluates to the approved outcome"
        )

    states = {
        (
            str(row.get("decision") or ""),
            str(row.get("processing_status") or ""),
        )
        for row in selected
    }
    if states == {("SKIP", "SKIPPED")}:
        metadata_values = [row.get("metadata") for row in selected]
        if (
            any(not isinstance(value, Mapping) for value in metadata_values)
            or dict(metadata_values[0]) != dict(metadata_values[1])
        ):
            raise ControlledApplyError(
                "Approved rows do not share safely mergeable metadata"
            )
        merged = deepcopy(dict(metadata_values[0]))
        merged.update(
            {
                "step8_rule_version": RULE_VERSION,
                "step8_reason_code": ReasonCode.SUPPORTED_FORMAT.value,
                "accepted_for_ai_analysis": False,
                "step8_evaluated_at": evaluated_at,
            }
        )
        ids = tuple(str(row.get("id") or "") for row in selected)
        if any(not value for value in ids) or len(set(ids)) != 2:
            raise ControlledApplyError("Approved source-file identity is invalid")
        return ApplyPlan("APPLY", ids, merged)

    if states == {("TAKE", "READY")}:
        for row in selected:
            if row.get("skip_reason") is not None:
                raise ControlledApplyError(
                    "Applied document has an unexpected skip reason"
                )
            metadata = row.get("metadata")
            if not isinstance(metadata, Mapping) or not _step8_metadata_matches(
                metadata
            ):
                raise ControlledApplyError(
                    "Applied document lacks expected Step 8 metadata"
                )
        return ApplyPlan("NO_CHANGE", (), None)

    raise ControlledApplyError(
        "Approved rows are in a mixed or unexpected current state"
    )


def execute_controlled_apply(
    store: Any,
    *,
    source_folder_id: str,
    expected_total: int,
) -> ApplyResult:
    before = store.read_step8_preview_rows(source_folder_id)
    evaluated_at = datetime.now(timezone.utc).isoformat()
    plan = build_apply_plan(
        before,
        source_folder_id=source_folder_id,
        evaluated_at=evaluated_at,
    )
    before_by_id = {str(row["id"]): dict(row) for row in before}
    changed = 0
    pdf_updated = 0
    pptx_updated = 0

    if plan.mode == "APPLY":
        updated = store.apply_step8_supported_document_decisions(
            source_folder_id=source_folder_id,
            source_file_ids=list(plan.source_file_ids),
            metadata=dict(plan.merged_metadata or {}),
        )
        if len(updated) != 2:
            raise ControlledApplyError(
                "Conditional update did not change exactly two rows"
            )
        updated_extensions = Counter(
            normalize_extension(row.get("file_extension"))
            for row in updated
        )
        if updated_extensions != Counter({"pdf": 1, "pptx": 1}):
            raise ControlledApplyError(
                "Conditional update returned unexpected format totals"
            )
        changed = 2
        pdf_updated = 1
        pptx_updated = 1

    after = store.read_step8_preview_rows(source_folder_id)
    preview = build_preview(after)
    if not reconciliation_passes(preview, expected_total=expected_total):
        raise ControlledApplyError("Post-apply reconciliation failed")
    document_take_counts = _document_take_counts(after)
    if document_take_counts != Counter({"pdf": 1, "pptx": 1}):
        raise ControlledApplyError(
            "Post-apply PDF/PPTX TAKE reconciliation failed"
        )
    unrelated_changed = _unrelated_fields_changed(before_by_id, after)
    if unrelated_changed:
        raise ControlledApplyError("An unrelated selected field changed")

    return ApplyResult(
        changed=changed,
        unchanged=expected_total - changed,
        pdf_updated=pdf_updated,
        pptx_updated=pptx_updated,
        pdf_take=document_take_counts["pdf"],
        pptx_take=document_take_counts["pptx"],
        preview=preview,
        unrelated_fields_changed=unrelated_changed,
    )


def reconciliation_passes(
    preview: SupabasePreview,
    *,
    expected_total: int,
) -> bool:
    return all(
        (
            preview.total_rows == expected_total,
            preview.current_take_ready == 292,
            preview.current_skip_skipped == 8,
            preview.proposed_take_ready == 292,
            preview.proposed_skip_skipped == 8,
            preview.changed == 0,
            preview.unchanged == expected_total,
            preview.google_native_skip == 6,
            preview.heic_skip == 2,
            preview.inaccessible == 0,
            preview.folder_rows == 0,
            preview.duplicate_identities == 0,
        )
    )


def print_result(result: ApplyResult) -> None:
    preview = result.preview
    print("Supabase connection result: connected")
    print(f"Rows changed: {result.changed}")
    print(f"Rows unchanged: {result.unchanged}")
    print(f"PDF updated count: {result.pdf_updated}")
    print(f"PPTX updated count: {result.pptx_updated}")
    print(f"PDF TAKE / READY count: {result.pdf_take}")
    print(f"PPTX TAKE / READY count: {result.pptx_take}")
    print(f"Final TAKE / READY: {preview.current_take_ready}")
    print(f"Final SKIP / SKIPPED: {preview.current_skip_skipped}")
    print(f"Google-native SKIP count: {preview.google_native_skip}")
    print(f"HEIC SKIP count: {preview.heic_skip}")
    print(f"Inaccessible row count: {preview.inaccessible}")
    print(f"Duplicate identity count: {preview.duplicate_identities}")
    print(f"Folder row count: {preview.folder_rows}")
    print(
        "Unrelated selected fields changed: "
        f"{'yes' if result.unrelated_fields_changed else 'no'}"
    )
    print("Audit or event rows created: no")
    print("Assets or asset_sources changed: no")
    print("Google Drive access occurred: no")
    print("Direct SQL or migration execution occurred: no")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expected_total != 300:
        print("Expected total must be exactly 300", file=sys.stderr)
        return 2
    try:
        from dotenv import load_dotenv
        from kdi_media.supabase_store import SupabaseStore

        load_dotenv(PROJECT_ROOT / ".env")
        url = _required_environment("SUPABASE_URL")
        key = _required_environment("SUPABASE_SERVICE_ROLE_KEY")
        store = SupabaseStore(url, key)
        result = execute_controlled_apply(
            store,
            source_folder_id=str(args.source_folder_id),
            expected_total=args.expected_total,
        )
    except ControlledApplyError as exc:
        print(f"Controlled apply failed safely: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "Controlled apply failed without exposing connection or row data",
            file=sys.stderr,
        )
        return 1
    print_result(result)
    return 0


def _evaluate_row(row: Mapping[str, Any]):
    metadata = row.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    accessibility = metadata.get("step6_accessibility_status", "accessible")
    if accessibility not in {"accessible", "inaccessible"}:
        accessibility = "accessible"
    return evaluate_file(
        FileRuleInput(
            file_name=row.get("file_name"),
            mime_type=row.get("mime_type"),
            file_extension=row.get("file_extension"),
            size_bytes=row.get("size_bytes"),
            relative_path=row.get("relative_path"),
            accessibility_status=accessibility,
            trashed=row.get("trashed"),
            is_missing=row.get("is_missing"),
            is_folder=False,
        )
    )


def _step8_metadata_matches(metadata: Mapping[str, Any]) -> bool:
    return all(
        (
            metadata.get("step8_rule_version") == RULE_VERSION,
            metadata.get("step8_reason_code")
            == ReasonCode.SUPPORTED_FORMAT.value,
            metadata.get("accepted_for_ai_analysis") is False,
            isinstance(metadata.get("step8_evaluated_at"), str),
            bool(str(metadata.get("step8_evaluated_at") or "").strip()),
        )
    )


def _document_take_counts(
    rows: list[Mapping[str, Any]],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        extension = normalize_extension(row.get("file_extension"))
        if (
            extension in APPROVED_EXTENSIONS
            and normalize_mime_type(row.get("mime_type"))
            == FORMAT_POLICY[extension].required_mime_type
            and row.get("decision") == "TAKE"
            and row.get("processing_status") == "READY"
        ):
            counts[extension] += 1
    return counts


def _unrelated_fields_changed(
    before_by_id: Mapping[str, Mapping[str, Any]],
    after: list[Mapping[str, Any]],
) -> bool:
    after_by_id = {str(row["id"]): row for row in after}
    if set(before_by_id) != set(after_by_id):
        return True
    for row_id, before in before_by_id.items():
        current = after_by_id[row_id]
        for field, value in before.items():
            if field not in OWNED_FIELDS and current.get(field) != value:
                return True
    return False


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
