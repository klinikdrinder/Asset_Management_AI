import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "semantic-search" / "phase4"
ASSETS = {"37838d30-a0ce-4f90-8cc3-c986db0aaa65", "6215ad8b-12be-4a8e-bc49-f6b3dcf55c21"}
SPEC_FP = "ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"


def manifests():
    return [json.loads((REPORT / f"{asset_id}_image_analysis.json").read_text(encoding="utf-8")) for asset_id in sorted(ASSETS)]


def test_exactly_two_frozen_images_completed_with_provenance():
    values = manifests()
    assert {item["asset_id"] for item in values} == ASSETS
    for item in values:
        assert item["status"] == "COMPLETED"
        assert item["semantic_spec_fingerprint"] == SPEC_FP
        assert item["processor_version"] == "kdi_image_analysis_v1"
        assert item["configuration_version"] == "kdi_image_analysis_config_v1"
        assert item["analysis_run_id"] and item["source_fingerprint"]
        assert item["idempotency"]["verified"]


def test_full_image_coordinates_states_and_conflicts_are_preserved():
    for item in manifests():
        full = item["regions"][0]
        metadata = item["technical_metadata"]
        assert full["region_type"] == "FULL_IMAGE"
        assert (full["x1"], full["y1"], full["x2"], full["y2"]) == (0, 0, metadata["analysis_width"], metadata["analysis_height"])
        assert full["area_ratio"] == 1.0
        assert item["applicability"]["3"]["state"] == "NOT_APPLICABLE"
        assert item["applicability"]["14"]["state"] == "NOT_APPLICABLE"
        assert item["applicability"]["15"]["state"] == "UNKNOWN"
        assert all(not value for value in item["negative_assertion_safety"].values())
        assert len(item["inherited_conflicts"]) == 2
        assert all(conflict["status"] == "PRESERVED_FOR_LATER_REVIEW" for conflict in item["inherited_conflicts"])


def test_regions_and_debug_artifacts_are_valid():
    for item in manifests():
        width = item["technical_metadata"]["analysis_width"]; height = item["technical_metadata"]["analysis_height"]
        assert item["retained_region_count"] == len(item["regions"])
        assert item["retained_region_count"] == 3
        for region in item["regions"]:
            assert 0 <= region["x1"] < region["x2"] <= width
            assert 0 <= region["y1"] < region["y2"] <= height
            assert all(0 <= value <= 1 for value in region["normalized_coordinates"].values())
        for relative in item["debug_artifacts"].values():
            assert (ROOT / relative).is_file()


def test_summary_comparison_and_phase3_preservation():
    summary = json.loads((REPORT / "image_analysis_summary.json").read_text(encoding="utf-8"))
    assert summary["image_count"] == summary["completed"] == summary["idempotency_verified"] == 2
    assert summary["totals"]["retained_regions"] == 6
    with (REPORT / "image_representation_comparison.csv").open(newline="", encoding="utf-8-sig") as handle:
        assert len(list(csv.DictReader(handle))) == 2
    phase3 = json.loads((ROOT / "reports" / "semantic-search" / "phase3" / "phase3_validation.json").read_text(encoding="utf-8"))
    assert phase3["status"] == "PASS"
    assert phase3["configuration_fingerprint"] == "5f603465f41b03aaf59e1daeb85676cbe521bca9fbd9869ea57584da68dc4363"
