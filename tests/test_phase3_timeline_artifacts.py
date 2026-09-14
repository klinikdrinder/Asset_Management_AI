import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "reports" / "semantic-search" / "phase3"
EXPECTED_SPEC_FINGERPRINT = "ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"


def _manifests():
    summary = json.loads((REPORT_ROOT / "video_timeline_summary.json").read_text(encoding="utf-8"))
    return [
        json.loads((REPORT_ROOT / f"{item['asset_id']}_timeline.json").read_text(encoding="utf-8"))
        for item in summary["videos"]
    ]


def test_all_frozen_video_shadow_manifests_are_complete():
    manifests = _manifests()
    assert len(manifests) == 8
    assert len({item["asset_id"] for item in manifests}) == 8
    assert all(item["status"] == "COMPLETED" for item in manifests)
    assert all(item["semantic_spec_fingerprint"] == EXPECTED_SPEC_FINGERPRINT for item in manifests)
    assert all(item["frame_analysis"]["every_frame_participated"] for item in manifests)
    assert all(item["frame_analysis"]["timeline_coverage_percent"] == 100.0 for item in manifests)
    assert all(item["frame_analysis"]["decode_failures"] == 0 for item in manifests)
    assert all(item["idempotency"]["verified"] for item in manifests)


def test_scene_event_and_keyframe_references_are_valid():
    for item in _manifests():
        frames = item["frame_analysis"]["frames_processed"]
        scenes = item["scene_candidates"]
        assert scenes[0]["start_frame"] == 0
        assert scenes[-1]["end_frame"] == frames - 1
        for left, right in zip(scenes, scenes[1:]):
            assert left["end_frame"] + 1 == right["start_frame"]
        scene_ids = {scene["scene_id"] for scene in scenes}
        event_ids = {event["event_id"] for event in item["event_candidates"]}
        for event in item["event_candidates"]:
            assert event["scene_id"] in scene_ids
            assert event["start_frame"] <= event["peak_frame"] <= event["end_frame"]
        for keyframe in item["keyframe_candidates"]:
            assert keyframe["scene_id"] in scene_ids
            assert 0 <= keyframe["frame_number"] < frames
            assert keyframe["event_id"] is None or keyframe["event_id"] in event_ids


def test_summary_and_comparison_export_agree():
    summary = json.loads((REPORT_ROOT / "video_timeline_summary.json").read_text(encoding="utf-8"))
    assert summary["video_count"] == 8
    assert summary["completed"] == 8
    assert summary["idempotency_verified"] == 8
    assert summary["totals"] == {
        "frames_processed": 3824,
        "scenes": 11,
        "events": 22,
        "keyframes": 44,
        "redundant_removed": 432,
        "wall_clock_seconds": summary["totals"]["wall_clock_seconds"],
    }
    with (REPORT_ROOT / "video_timeline_comparison.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 8
    assert all(int(row["old_production_scenes"]) == 1 for row in rows)
    assert all(int(row["old_production_keyframes"]) == 1 for row in rows)
    assert all(int(row["new_event_candidates"]) >= 0 for row in rows)
