"""Validate, preview, or register source folders from a CSV manifest."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Protocol


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kdi_media.source_folders import (  # noqa: E402
    create_supabase_client_from_environment,
    extract_google_folder_id,
    normalize_google_folder_url,
    register_source_folder,
)


REQUIRED_COLUMNS = (
    "source_name",
    "account_name",
    "folder_url",
    "notes",
    "active",
)
OPTIONAL_COLUMNS = (
    "expected_folder_id",
    "clinical_content",
    "processing_enabled",
)
ALLOWED_COLUMNS = frozenset(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)


@dataclass(frozen=True)
class SourceManifestRow:
    row_number: int
    source_name: str
    account_name: str
    folder_url: str
    google_folder_id: str
    notes: str
    active: bool
    expected_folder_id: str | None
    clinical_content: bool | None
    processing_enabled: bool | None

    def registration_values(self) -> dict[str, Any]:
        notes = self.notes
        metadata_notes = []
        if self.clinical_content is not None:
            metadata_notes.append(
                f"clinical_content={str(self.clinical_content).lower()}"
            )
        if self.processing_enabled is not None:
            metadata_notes.append(
                "processing_enabled="
                f"{str(self.processing_enabled).lower()}"
            )
        if metadata_notes:
            notes = "; ".join(filter(None, (notes, *metadata_notes)))
        return {
            "source_name": self.source_name,
            "account_name": self.account_name,
            "folder_url": self.folder_url,
            "notes": notes,
            "active": self.active,
        }


@dataclass(frozen=True)
class RejectedManifestRow:
    row_number: int
    reason: str


@dataclass(frozen=True)
class OnboardingPlanItem:
    row: SourceManifestRow
    action: str


class OnboardingRepository(Protocol):
    def read_existing(self, google_folder_ids: list[str]) -> list[dict[str, Any]]:
        ...

    def register(self, row: SourceManifestRow) -> dict[str, Any]:
        ...


class SupabaseOnboardingRepository:
    def __init__(self, client: Any) -> None:
        self.client = client

    def read_existing(self, google_folder_ids: list[str]) -> list[dict[str, Any]]:
        if not google_folder_ids:
            return []
        response = (
            self.client.table("source_folders")
            .select(
                "id,source_name,account_name,folder_url,google_folder_id,"
                "notes,active"
            )
            .in_("google_folder_id", google_folder_ids)
            .execute()
        )
        return list(response.data or [])

    def register(self, row: SourceManifestRow) -> dict[str, Any]:
        return register_source_folder(
            self.client,
            **row.registration_values(),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bulk validate or register source folders from CSV."
    )
    parser.add_argument("--csv", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    return parser


def parse_manifest(
    path: Path,
) -> tuple[list[SourceManifestRow], list[RejectedManifestRow]]:
    accepted: list[SourceManifestRow] = []
    rejected: list[RejectedManifestRow] = []
    seen_folder_ids: set[str] = set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = tuple(reader.fieldnames or ())
            missing = set(REQUIRED_COLUMNS) - set(fields)
            unexpected = set(fields) - ALLOWED_COLUMNS
            if missing:
                raise ValueError("CSV is missing required columns")
            if unexpected:
                raise ValueError("CSV contains unsupported columns")
            for row_number, raw in enumerate(reader, start=2):
                try:
                    row = _parse_row(raw, row_number)
                    if row.google_folder_id in seen_folder_ids:
                        raise ValueError("Duplicate Google folder ID in CSV")
                    seen_folder_ids.add(row.google_folder_id)
                    accepted.append(row)
                except ValueError as exc:
                    rejected.append(
                        RejectedManifestRow(row_number, str(exc))
                    )
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError("CSV could not be read safely") from exc
    return accepted, rejected


def plan_onboarding(
    rows: Iterable[SourceManifestRow],
    existing_rows: Iterable[Mapping[str, Any]],
) -> list[OnboardingPlanItem]:
    existing = {
        str(row.get("google_folder_id")): row for row in existing_rows
    }
    plan: list[OnboardingPlanItem] = []
    for row in rows:
        current = existing.get(row.google_folder_id)
        if current is None:
            action = "INSERT"
        elif _same_registration(row, current):
            action = "UNCHANGED"
        else:
            action = "UPDATE"
        plan.append(OnboardingPlanItem(row, action))
    return plan


def execute_plan(
    plan: Iterable[OnboardingPlanItem],
    repository: OnboardingRepository,
    *,
    continue_on_error: bool,
) -> tuple[int, int]:
    changed = 0
    failed = 0
    for item in plan:
        if item.action == "UNCHANGED":
            continue
        try:
            repository.register(item.row)
            changed += 1
        except Exception:
            failed += 1
            if not continue_on_error:
                break
    return changed, failed


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows, rejected = parse_manifest(args.csv)
    except ValueError as exc:
        print(f"CSV validation failed: {exc}", file=sys.stderr)
        return 1

    if args.validate_only:
        _print_validation(rows, rejected)
        return 0 if not rejected else 1

    try:
        repository = SupabaseOnboardingRepository(
            create_supabase_client_from_environment()
        )
        existing = repository.read_existing(
            [row.google_folder_id for row in rows]
        )
        plan = plan_onboarding(rows, existing)
    except Exception:
        print(
            "Onboarding preview failed without exposing connection data",
            file=sys.stderr,
        )
        return 1

    _print_plan(plan, rejected)
    if args.dry_run:
        print("Supabase writes occurred: no")
        return 0 if not rejected else 1

    changed, failed = execute_plan(
        plan,
        repository,
        continue_on_error=args.continue_on_error,
    )
    print(f"Rows registered or updated: {changed}")
    print(f"Registration failures: {failed}")
    return 0 if failed == 0 and not rejected else 1


def _parse_row(
    raw: Mapping[str, str | None],
    row_number: int,
) -> SourceManifestRow:
    source_name = _required_text(raw.get("source_name"), "Missing source name")
    account_name = _required_text(
        raw.get("account_name"), "Missing account name"
    )
    folder_url_raw = _required_text(
        raw.get("folder_url"), "Missing folder URL"
    )
    google_folder_id = extract_google_folder_id(folder_url_raw)
    expected = _optional_text(raw.get("expected_folder_id"))
    if expected is not None and expected != google_folder_id:
        raise ValueError("Expected folder ID does not match folder URL")
    return SourceManifestRow(
        row_number=row_number,
        source_name=source_name,
        account_name=account_name,
        folder_url=normalize_google_folder_url(folder_url_raw),
        google_folder_id=google_folder_id,
        notes=_optional_text(raw.get("notes")) or "",
        active=_boolean(raw.get("active"), required=True),
        expected_folder_id=expected,
        clinical_content=_boolean(raw.get("clinical_content")),
        processing_enabled=_boolean(raw.get("processing_enabled")),
    )


def _same_registration(
    proposed: SourceManifestRow,
    current: Mapping[str, Any],
) -> bool:
    values = proposed.registration_values()
    return all(
        (
            str(current.get("source_name") or "").strip()
            == values["source_name"],
            str(current.get("account_name") or "").strip()
            == values["account_name"],
            str(current.get("folder_url") or "").strip()
            == values["folder_url"],
            str(current.get("notes") or "") == values["notes"],
            current.get("active") is values["active"],
        )
    )


def _boolean(value: str | None, *, required: bool = False) -> bool | None:
    normalized = (value or "").strip().lower()
    if not normalized and not required:
        return None
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError("Boolean values must be true or false")


def _required_text(value: str | None, message: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(message)
    return normalized


def _optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _print_validation(
    rows: list[SourceManifestRow],
    rejected: list[RejectedManifestRow],
) -> None:
    print(f"CSV rows accepted: {len(rows)}")
    print(f"CSV rows rejected: {len(rejected)}")
    for row in rows:
        print(f"Row {row.row_number}: VALID")
    for row in rejected:
        print(f"Row {row.row_number}: REJECTED ({row.reason})")
    print("Supabase connection occurred: no")
    print("Google Drive connection occurred: no")


def _print_plan(
    plan: list[OnboardingPlanItem],
    rejected: list[RejectedManifestRow],
) -> None:
    for item in plan:
        print(f"Row {item.row.row_number}: {item.action}")
    for row in rejected:
        print(f"Row {row.row_number}: REJECTED ({row.reason})")


if __name__ == "__main__":
    raise SystemExit(main())
