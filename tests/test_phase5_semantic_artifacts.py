import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/semantic-search/phase5"
VALID_STATES = {"OBSERVED", "FALSE", "UNKNOWN", "NOT_APPLICABLE"}
VALID_APPLICABILITY = {"APPLICABLE", "NOT_APPLICABLE", "UNCERTAIN"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def packages():
    manifest = load(ROOT / "config/semantic-search/kdi_semantic_pilot_v1.json")
    return manifest, [load(OUT / f"{a['asset_id']}_semantic_layers.json") for a in manifest["assets"]]


def test_exact_coverage_and_locked_layers():
    manifest, values = packages()
    spec = load(ROOT / "config/semantic-search/kdi_semantic_search_spec_v1.json")
    assert len(manifest["assets"]) == len(values) == 10
    expected = [(x["number"], x["id"], x["name"]) for x in spec["layers"]]
    assert sum(len(p["layers"]) for p in values) == 180
    for package in values:
        assert [(x["layer_number"], x["layer_id"], x["layer_name"]) for x in package["layers"]] == expected
        assert package["analysis_run"]["semantic_spec_fingerprint"] == "ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"
        assert package["idempotency"]["verified"] is True


def test_states_confidence_and_evidence_contract():
    _, values = packages()
    for package in values:
        for layer in package["layers"]:
            assert layer["semantic_state"] in VALID_STATES
            assert layer["applicability"] in VALID_APPLICABILITY
            assert layer["future_work"]
            for fact in layer["structured_facts"]:
                assert fact["state"] in VALID_STATES
                if fact["state"] == "OBSERVED":
                    assert fact["evidence"]
                    assert 0 <= fact["confidence"] <= 1
                if fact["state"] == "FALSE":
                    assert fact["evidence"], "FALSE requires affirmative negative evidence"


def test_media_applicability_and_later_phase_guards():
    _, values = packages()
    for package in values:
        by_number = {x["layer_number"]: x for x in package["layers"]}
        if package["asset"]["media_type"] == "video":
            assert by_number[3]["applicability"] == "APPLICABLE"
            assert by_number[14]["processing_status"] == "PENDING_PHASE_6"
        else:
            assert by_number[3]["semantic_state"] == "NOT_APPLICABLE"
            assert by_number[14]["semantic_state"] == "NOT_APPLICABLE"
        assert by_number[15]["processing_status"] == "PENDING_PHASE_7"
        assert by_number[18]["processing_status"] == "PENDING_LATER_SEARCH_STAGE"
    summary = load(OUT / "phase5_semantic_summary.json")
    assert all(v == 0 for v in summary["forbidden_operations"].values())
    assert summary["evidence_coverage"]["unsupported_high_confidence_search_critical_facts"] == 0


def test_no_dangling_phase_evidence_references():
    _, values = packages()
    for package in values:
        aid = package["asset"]["asset_id"]
        if package["asset"]["media_type"] == "video":
            source = load(ROOT / f"reports/semantic-search/phase3/{aid}_timeline.json")
            scenes = {x["scene_id"] for x in source["scene_candidates"]}
            events = {x["event_id"] for x in source["event_candidates"]}
            keyframes = {x["keyframe_id"] for x in source["keyframe_candidates"]}
        else:
            source = load(ROOT / f"reports/semantic-search/phase4/{aid}_image_analysis.json")
            regions = {x["region_id"] for x in source["regions"]}
        assert package["analysis_run"]["source_fingerprint"] == source["source_fingerprint"]
        for layer in package["layers"]:
            for fact in layer["structured_facts"]:
                for evidence in fact.get("evidence", []):
                    if evidence.get("scene_id"): assert evidence["scene_id"] in scenes
                    if evidence.get("event_id"): assert evidence["event_id"] in events
                    if evidence.get("keyframe_id"): assert evidence["keyframe_id"] in keyframes
                    if evidence.get("region_id"): assert evidence["region_id"] in regions


def test_conflict_and_review_outputs_are_preserved():
    conflicts = load(OUT / "phase5_semantic_conflicts.json")
    queue = load(OUT / "phase5_human_review_queue.json")
    assert conflicts["conflict_count"] == 7
    assert {x["filename"] for x in conflicts["conflicts"]} >= {"DSC03753.JPG", "DSC08097.JPG", "IMG_1238.MP4"}
    assert queue["item_count"] == 22
    assert sum(x["priority"] == "P0" for x in queue["items"]) == 4
