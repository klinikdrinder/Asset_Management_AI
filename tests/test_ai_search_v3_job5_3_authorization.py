import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "reports" / "ai-search-v3"


def manifest() -> dict:
    return json.loads((REPORTS / "job5_3-final-pilot-manifest.json").read_text(encoding="utf-8"))


def test_final_manifest_is_exactly_ten_explicit_approvals() -> None:
    data = manifest()
    assert data["purpose"] == "KDI AI Search V3 pilot indexing only"
    assert data["pilot_size"] == 10
    assert len(data["assets"]) == 10
    assert len({row["asset_id"] for row in data["assets"]}) == 10
    assert all(row["decision"] == "APPROVE" for row in data["assets"])
    assert all(row["external_ai_status"] == "ALLOWED" for row in data["assets"])


def test_authorization_traceability_is_complete() -> None:
    data = manifest()
    assert data["reviewer"] == "kdimediaautomation@gmail.com"
    assert data["reviewed_at"]
    assert all(row["reviewer"] == data["reviewer"] for row in data["assets"])
    assert all(row["reviewed_at"] == data["reviewed_at"] for row in data["assets"])
    assert all(row["decision_reason"] for row in data["assets"])


def test_blocked_originals_are_absent() -> None:
    selected = {row["file_name"] for row in manifest()["assets"]}
    blocked = {
        "DSC00365.JPG", "DSC05881.JPG", "IMG_0588.MP4",
        "IMG_0620.MP4", "IMG_0621.MP4", "IMG_1253.MP4",
    }
    assert selected.isdisjoint(blocked)


def test_service_role_repair_is_least_privilege() -> None:
    migration = (
        ROOT
        / "supabase"
        / "migrations"
        / "20260820045231_ai_search_v3_job5_3_service_role_private_usage.sql"
    ).read_text(encoding="utf-8").lower()
    assert "grant usage on schema private to service_role" in migration
    assert "to anon" not in migration
    assert "to authenticated" not in migration
    assert "grant execute" not in migration
