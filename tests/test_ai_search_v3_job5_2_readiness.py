import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "reports" / "ai-search-v3"


def test_approval_manifest_is_exactly_ten_and_unapproved() -> None:
    data = json.loads((REPORTS / "job5_2-pilot-external-ai-approval-manifest.json").read_text(encoding="utf-8"))
    assert data["purpose"] == "KDI AI Search V3 pilot indexing only"
    assert len(data["assets"]) == 10
    assert len({row["asset_id"] for row in data["assets"]}) == 10
    assert all(row["current_status"] == "NOT_REVIEWED" for row in data["assets"])
    assert all(row["decision"] is None and row["reviewer"] is None for row in data["assets"])


def test_manifest_blocking_evidence_is_preserved() -> None:
    data = json.loads((REPORTS / "job5_2-pilot-external-ai-approval-manifest.json").read_text(encoding="utf-8"))
    blocked = {row["file_name"] for row in data["assets"] if row["blocking_evidence"]}
    assert blocked == {
        "DSC00365.JPG", "DSC05881.JPG", "IMG_0588.MP4",
        "IMG_0620.MP4", "IMG_0621.MP4", "IMG_1253.MP4",
    }
