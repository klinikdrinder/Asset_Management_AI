from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from kdi_media.video_frames import (
    FrameExtractionError,
    FfmpegFrameExtractor,
    limit_transcript,
    resolve_media_executable,
)


class LimitTranscriptTests(unittest.TestCase):
    def test_none_returns_none(self) -> None:
        self.assertIsNone(limit_transcript(None))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(limit_transcript(""))

    def test_whitespace_only_returns_none(self) -> None:
        self.assertIsNone(limit_transcript("   \n\t  "))

    def test_short_text_is_returned_normalized(self) -> None:
        self.assertEqual(limit_transcript("  hello   world  "), "hello world")

    def test_long_text_is_truncated_to_max_chars(self) -> None:
        text = "word " * 1000
        result = limit_transcript(text, max_chars=50)
        assert result is not None
        self.assertLessEqual(len(result), 50)

    def test_default_max_chars_is_reasonable_for_prompt_context(self) -> None:
        text = "x" * 10000
        result = limit_transcript(text)
        assert result is not None
        self.assertLessEqual(len(result), 2000)


class EvenlySpacedTimestampsTests(unittest.TestCase):
    """Pure-logic tests only - no ffmpeg/ffprobe subprocess is invoked."""

    def test_zero_duration_returns_single_timestamp(self) -> None:
        self.assertEqual(FfmpegFrameExtractor._evenly_spaced_timestamps(0.0, 6), [0.0])

    def test_single_frame_request_returns_midpoint(self) -> None:
        timestamps = FfmpegFrameExtractor._evenly_spaced_timestamps(100.0, 1)
        self.assertEqual(len(timestamps), 1)
        self.assertGreater(timestamps[0], 0.0)
        self.assertLess(timestamps[0], 100.0)

    def test_multiple_frames_are_evenly_spaced_and_avoid_edges(self) -> None:
        duration = 60.0
        timestamps = FfmpegFrameExtractor._evenly_spaced_timestamps(duration, 6)
        self.assertEqual(len(timestamps), 6)
        # Representative sampling avoids the very first/last instants.
        self.assertGreater(timestamps[0], 0.0)
        self.assertLess(timestamps[-1], duration)
        # Monotonically increasing.
        self.assertEqual(timestamps, sorted(timestamps))

    def test_frame_count_matches_requested_max_frames(self) -> None:
        for max_frames in (1, 3, 6, 10):
            timestamps = FfmpegFrameExtractor._evenly_spaced_timestamps(120.0, max_frames)
            self.assertEqual(len(timestamps), max_frames)


class FfmpegFrameExtractorValidationTests(unittest.TestCase):
    def test_max_frames_below_one_is_rejected(self) -> None:
        extractor = FfmpegFrameExtractor()
        with self.assertRaises(ValueError):
            extractor.extract_frames(b"not-a-real-video", max_frames=0)

    def test_frame_command_caps_pixel_dimensions(self) -> None:
        extractor = FfmpegFrameExtractor()
        with patch("kdi_media.video_frames.subprocess.run") as run:
            extractor._extract_single_frame(Path("input.mp4"), 1.5, Path("frame.jpg"))
        command = run.call_args.args[0]
        self.assertIn("scale=1600:1600:force_original_aspect_ratio=decrease", command)

    def test_invalid_video_is_rejected_and_temporary_directory_is_cleaned(self) -> None:
        extractor = FfmpegFrameExtractor()
        observed: list[Path] = []
        original_probe = extractor._probe_duration

        def probe(path: Path) -> float:
            observed.append(path.parent)
            return original_probe(path)

        with patch.object(extractor, "_probe_duration", side_effect=probe):
            with self.assertRaises(FrameExtractionError):
                extractor.extract_frames(b"corrupt-video", max_frames=6)
        self.assertTrue(observed)
        self.assertFalse(observed[0].exists())

    def test_nonzero_or_timeout_producing_zero_frames_is_rejected(self) -> None:
        extractor = FfmpegFrameExtractor(ffmpeg_path="C:/path with spaces/ffmpeg.exe", ffprobe_path="probe")
        with (
            patch.object(extractor, "_probe_duration", return_value=10.0),
            patch.object(extractor, "_extract_single_frame", return_value=None),
            self.assertRaises(FrameExtractionError),
        ):
            extractor.extract_frames(b"video", max_frames=6)

    def test_subprocess_timeout_is_bounded_and_rejected(self) -> None:
        extractor = FfmpegFrameExtractor(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
        with (
            patch.object(extractor, "_probe_duration", return_value=1.0),
            patch(
                "kdi_media.video_frames.subprocess.run",
                side_effect=subprocess.TimeoutExpired("ffmpeg", 30),
            ),
            self.assertRaises(FrameExtractionError),
        ):
            extractor.extract_frames(b"video", max_frames=1)


class ExecutableResolverTests(unittest.TestCase):
    def test_project_local_executable_precedes_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="kdi path with spaces ") as tmp:
            executable = Path(tmp) / ".tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"fixture")
            with patch("kdi_media.video_frames.shutil.which", return_value="C:/system/ffmpeg.exe"):
                resolved = resolve_media_executable(
                    "ffmpeg", environment_name="KDI_FFMPEG_PATH", project_root=Path(tmp)
                )
            self.assertEqual(Path(resolved), executable.resolve())

    def test_explicit_missing_path_fails_without_fallback(self) -> None:
        with (
            patch.dict("os.environ", {"KDI_FFMPEG_PATH": "C:/missing/ffmpeg.exe"}),
            patch("kdi_media.video_frames.shutil.which", return_value="C:/system/ffmpeg.exe"),
            self.assertRaises(FrameExtractionError),
        ):
            resolve_media_executable("ffmpeg", environment_name="KDI_FFMPEG_PATH")

    def test_missing_ffprobe_reports_exact_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "kdi_media.video_frames.shutil.which", return_value=None
        ), self.assertRaisesRegex(FrameExtractionError, "ffprobe executable"):
            resolve_media_executable(
                "ffprobe", environment_name="KDI_FFPROBE_PATH", project_root=Path(tmp)
            )


if __name__ == "__main__":
    unittest.main()
