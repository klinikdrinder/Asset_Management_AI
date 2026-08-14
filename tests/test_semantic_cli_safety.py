from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kdi_media.semantic_indexing import AssetCandidate
from kdi_media.video_frames import FrameExtractionError
from scripts.run_semantic_indexing import _run_execute


def candidate() -> AssetCandidate:
    return AssetCandidate(
        asset_id="11111111-1111-4111-8111-111111111111",
        file_name="video.mp4",
        mime_type="video/mp4",
        file_extension="mp4",
        content_hash="a" * 64,
        updated_at="2026-01-01T00:00:00Z",
        size_bytes=100,
        google_file_id="canonical-id",
        media_category="video",
    )


class ExecutePreflightTests(unittest.TestCase):
    def args(self):
        return SimpleNamespace(
            asset_id=[candidate().asset_id], retry_failed=False, max_cost=1.0,
            limit=1, batch_size=1,
        )

    def test_missing_verified_candidate_is_rejected_before_provider(self):
        repository = SimpleNamespace(fetch_candidate=lambda _asset_id: None)
        with (
            patch("scripts.run_semantic_indexing.get_description_provider") as provider,
            self.assertRaises(SystemExit),
        ):
            _run_execute(self.args(), repository)
        provider.assert_not_called()

    def test_missing_ffmpeg_is_rejected_before_provider_or_write(self):
        repository = SimpleNamespace(fetch_candidate=lambda _asset_id: candidate())
        with (
            patch(
                "scripts.run_semantic_indexing.resolve_ffmpeg_paths",
                side_effect=FrameExtractionError("ffmpeg missing"),
            ),
            patch("scripts.run_semantic_indexing.get_description_provider") as provider,
            self.assertRaises(SystemExit),
        ):
            _run_execute(self.args(), repository)
        provider.assert_not_called()
