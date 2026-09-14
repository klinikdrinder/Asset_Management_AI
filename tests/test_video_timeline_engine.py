from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kdi_media.video_frames import resolve_ffmpeg_paths
from kdi_media.video_timeline import (
    PROCESSOR_VERSION,
    TimelineConfig,
    VideoTimelineProcessor,
    canonical_fingerprint,
    file_sha256,
    functional_output,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "semantic-search" / "kdi_video_timeline_v1.json"
SPEC_FINGERPRINT = "ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"


class TimelineEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffmpeg, cls.ffprobe = resolve_ffmpeg_paths(project_root=ROOT)
        cls.config = TimelineConfig.load(CONFIG_PATH)
        cls.processor = VideoTimelineProcessor(cls.config, ffmpeg_path=cls.ffmpeg, ffprobe_path=cls.ffprobe)
        cls.temp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temp.name)
        cls.fixtures = {
            "hard": cls._fixture("hard.mp4", "color=c=black:s=320x180:r=20:d=1[color0];color=c=white:s=320x180:r=20:d=1[color1];color=c=black:s=320x180:r=20:d=1[color2];[color0][color1][color2]concat=n=3:v=1:a=0"),
            "short": cls._fixture("short.mp4", "color=c=black:s=320x180:r=20:d=3,drawbox=x=120:y=50:w=80:h=80:color=white:t=fill:enable='between(t,1.1,1.65)'"),
            "gradual": cls._fixture("gradual.mp4", "color=c=black:s=320x180:r=20:d=3,fade=t=in:st=0.5:d=1.5:color=white"),
            "static": cls._fixture("static.mp4", "color=c=gray:s=320x180:r=20:d=3"),
            "motion": cls._fixture("motion.mp4", "color=c=black:s=320x180:r=20:d=3,drawbox=x='mod(t*80,240)':y=50:w=80:h=80:color=white:t=fill"),
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    @classmethod
    def _fixture(cls, name: str, graph: str) -> Path:
        path = cls.work / name
        command = [cls.ffmpeg, "-v", "error", "-f", "lavfi", "-i", graph, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(path)]
        subprocess.run(command, check=True, capture_output=True, timeout=60)
        return path

    def run_fixture(self, name: str) -> dict:
        path = self.fixtures[name]
        return self.processor.process(path, asset_id=f"fixture-{name}", filename=path.name, source_fingerprint=file_sha256(path), semantic_spec_version="semantic_index_v1", semantic_spec_fingerprint=SPEC_FINGERPRINT, pilot_manifest_version="synthetic-fixtures-v1")

    def test_configuration_fingerprint_and_version(self) -> None:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(raw["processor_version"], PROCESSOR_VERSION)
        self.assertEqual(self.config.fingerprint, canonical_fingerprint(raw))

    def test_complete_traversal_timestamps_and_partition(self) -> None:
        result = self.run_fixture("hard")
        self.assertEqual(result["status"], "COMPLETED")
        frames = result["frame_analysis"]
        self.assertEqual(frames["frames_processed"], frames["decodable_frames"])
        self.assertTrue(frames["every_frame_participated"])
        self.assertGreaterEqual(frames["timeline_coverage_percent"], 99.0)
        timestamps = [x["timestamp_seconds"] for x in frames["signals"]]
        self.assertEqual(timestamps, sorted(timestamps))
        scenes = result["scene_candidates"]
        self.assertEqual(scenes[0]["start_frame"], 0)
        self.assertEqual(scenes[-1]["end_frame"], frames["frames_processed"] - 1)
        for left, right in zip(scenes, scenes[1:]):
            self.assertEqual(left["end_frame"] + 1, right["start_frame"])
            self.assertLessEqual(left["end_time"], right["start_time"])

    def test_hard_cuts_are_detected(self) -> None:
        result = self.run_fixture("hard")
        hard = [x for x in result["boundaries"] if x["boundary_type"] == "HARD_CUT"]
        self.assertGreaterEqual(len(hard), 2)
        self.assertTrue(any(abs(x["timestamp_seconds"] - 1.0) <= 0.15 for x in hard))
        self.assertTrue(any(abs(x["timestamp_seconds"] - 2.0) <= 0.15 for x in hard))

    def test_short_event_detected_and_keyframe_retained(self) -> None:
        result = self.run_fixture("short")
        events = result["event_candidates"]
        self.assertGreaterEqual(len(events), 1)
        matching = [x for x in events if x["start_time"] <= 1.4 <= x["end_time"]]
        self.assertTrue(matching)
        self.assertTrue(any(x["event_id"] == matching[0]["event_id"] for x in result["keyframe_candidates"]))
        self.assertTrue(any(x["selection_reason"] == "EVENT_PEAK" for x in result["keyframe_candidates"]))

    def test_gradual_transition_has_soft_or_event_representation(self) -> None:
        result = self.run_fixture("gradual")
        self.assertTrue(any(x["boundary_type"] == "SOFT_TRANSITION" for x in result["boundaries"]) or result["event_candidates"])

    def test_static_video_does_not_explode(self) -> None:
        result = self.run_fixture("static")
        self.assertEqual(len(result["scene_candidates"]), 1)
        self.assertLessEqual(len(result["event_candidates"]), 1)
        self.assertNotIn("OVER_SEGMENTATION_SCENE_RATE", result["warnings"])

    def test_continuous_motion_does_not_boundary_every_frame(self) -> None:
        result = self.run_fixture("motion")
        self.assertLess(len(result["scene_candidates"]), 6)
        self.assertLess(len(result["boundaries"]), result["frame_analysis"]["frames_processed"] // 4)

    def test_adaptive_sampling_and_multi_keyframe_support(self) -> None:
        result = self.run_fixture("short")
        stable_expected = result["frame_analysis"]["frames_processed"] / (self.config["stable_sampling_interval_seconds"] * result["technical_metadata"]["fps"])
        self.assertGreater(result["adaptive_sampling"]["candidate_frame_count"], stable_expected)
        self.assertGreater(len(result["keyframe_candidates"]), len(result["scene_candidates"]))
        self.assertGreaterEqual(result["redundant_keyframes_removed"], 0)

    def test_event_and_keyframe_links_are_valid(self) -> None:
        result = self.run_fixture("short")
        scenes = {x["scene_id"]: x for x in result["scene_candidates"]}
        events = {x["event_id"]: x for x in result["event_candidates"]}
        for event in events.values():
            self.assertIn(event["scene_id"], scenes)
            self.assertLessEqual(event["start_frame"], event["peak_frame"])
            self.assertLessEqual(event["peak_frame"], event["end_frame"])
        for keyframe in result["keyframe_candidates"]:
            self.assertIn(keyframe["scene_id"], scenes)
            self.assertGreaterEqual(keyframe["frame_number"], 0)
            self.assertLess(keyframe["frame_number"], result["frame_analysis"]["frames_processed"])
            if keyframe["event_id"] is not None:
                self.assertIn(keyframe["event_id"], events)

    def test_repeat_run_is_functionally_idempotent(self) -> None:
        first = self.run_fixture("short")
        second = self.run_fixture("short")
        self.assertEqual(functional_output(first), functional_output(second))
        self.assertEqual(first["source_fingerprint"], file_sha256(self.fixtures["short"]))

    def test_corrupt_video_fails_without_raising_batch_error(self) -> None:
        corrupt = self.work / "corrupt.mp4"
        corrupt.write_bytes(b"not video")
        result = self.processor.process(corrupt, asset_id="bad", filename=corrupt.name, source_fingerprint=file_sha256(corrupt), semantic_spec_version="semantic_index_v1", semantic_spec_fingerprint=SPEC_FINGERPRINT, pilot_manifest_version="synthetic-fixtures-v1")
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("failure", result)


if __name__ == "__main__":
    unittest.main()
