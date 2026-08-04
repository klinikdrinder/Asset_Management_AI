"""Preview canonical Step 8 decisions from a historical Step 6 JSON report.

This command is local-only.  It does not import Supabase or Google Drive
clients, connect to external services, or modify the historical report.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kdi_media.rules import (  # noqa: E402
    DecisionResult,
    FileRuleInput,
    ReasonCode,
    evaluate_file,
)
from kdi_media.step6_inventory import (  # noqa: E402
    FOLDER_CLASSIFICATION,
    INACCESSIBLE_ITEM_CLASSIFICATION,
    SUPPORTED_FILE_CLASSIFICATION,
    Step6InventoryReport,
    Step6Item,
    UNSUPPORTED_FILE_CLASSIFICATION,
    parse_step6_json,
)


@dataclass(frozen=True)
class SafeDifference:
    extension: str
    mime_type: str
    previous_classification: str
    proposed_decision: str
    reason_code: str
    accepted_for_ai_analysis: bool


@dataclass(frozen=True)
class PreviewSummary:
    total_file_records: int
    folder_items_excluded: int
    decisions: tuple[tuple[str, int], ...]
    reasons: tuple[tuple[str, int], ...]
    differences: tuple[SafeDifference, ...]

    @property
    def take_count(self) -> int:
        return dict(self.decisions).get("TAKE", 0)

    @property
    def skip_count(self) -> int:
        return dict(self.decisions).get("SKIP", 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview Step 8 decisions from a local Step 6 report."
    )
    parser.add_argument("--step6-json", required=True, type=Path)
    parser.add_argument("--expected-total", required=True, type=int)
    return parser


def evaluate_step6_item(item: Step6Item) -> DecisionResult:
    return evaluate_file(
        FileRuleInput(
            file_name=item.name,
            mime_type=item.mime_type,
            file_extension=item.file_extension,
            size_bytes=item.size,
            relative_path=item.relative_folder_path,
            accessibility_status=item.accessibility_status,
            trashed=False,
            is_missing=False,
            is_folder=item.classification == FOLDER_CLASSIFICATION,
        )
    )


def preview_report(report: Step6InventoryReport) -> PreviewSummary:
    decisions: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    differences: list[SafeDifference] = []
    folder_count = 0

    for item in report.items:
        proposed = evaluate_step6_item(item)
        if proposed.reason_code == ReasonCode.FOLDER_ITEM:
            folder_count += 1
            continue

        decisions[proposed.automatic_decision] += 1
        reasons[proposed.reason_code.value] += 1
        previous_decision = _historical_decision(item.classification)
        if previous_decision != proposed.automatic_decision:
            differences.append(
                SafeDifference(
                    extension=proposed.normalized_extension or "(missing)",
                    mime_type=proposed.normalized_mime_type or "(missing)",
                    previous_classification=item.classification,
                    proposed_decision=proposed.automatic_decision,
                    reason_code=proposed.reason_code.value,
                    accepted_for_ai_analysis=(
                        proposed.accepted_for_ai_analysis
                    ),
                )
            )

    return PreviewSummary(
        total_file_records=sum(decisions.values()),
        folder_items_excluded=folder_count,
        decisions=tuple(sorted(decisions.items())),
        reasons=tuple(sorted(reasons.items())),
        differences=tuple(differences),
    )


def _historical_decision(classification: str) -> str:
    if classification == SUPPORTED_FILE_CLASSIFICATION:
        return "TAKE"
    if classification == UNSUPPORTED_FILE_CLASSIFICATION:
        return "SKIP"
    if classification == INACCESSIBLE_ITEM_CLASSIFICATION:
        return "PENDING"
    if classification == FOLDER_CLASSIFICATION:
        return "PENDING"
    raise ValueError("Unknown historical classification")


def print_preview(summary: PreviewSummary) -> None:
    print("Step 8 local preview")
    print(f"Total file records: {summary.total_file_records}")
    print(f"Folder items excluded: {summary.folder_items_excluded}")
    for decision, count in summary.decisions:
        print(f"Proposed {decision}: {count}")
    print("Reason-code distribution:")
    for reason, count in summary.reasons:
        print(f"  {reason}: {count}")
    print(f"Proposed decision changes: {len(summary.differences)}")
    if summary.differences:
        print("Safe difference metadata:")
        for difference in summary.differences:
            print(
                "  "
                f"extension={difference.extension} "
                f"mime_type={difference.mime_type} "
                f"previous_classification="
                f"{difference.previous_classification} "
                f"proposed_decision={difference.proposed_decision} "
                f"reason_code={difference.reason_code} "
                f"accepted_for_ai_analysis="
                f"{str(difference.accepted_for_ai_analysis).lower()}"
            )
    print("Supabase connection occurred: no")
    print("Google Drive connection occurred: no")
    print("Database writes occurred: no")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expected_total <= 0:
        print("--expected-total must be positive", file=sys.stderr)
        return 2
    report = parse_step6_json(args.step6_json)
    summary = preview_report(report)
    if summary.total_file_records != args.expected_total:
        print(
            "Preview total did not match --expected-total",
            file=sys.stderr,
        )
        return 1
    print_preview(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
