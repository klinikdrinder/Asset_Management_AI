from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from types import SimpleNamespace
from unittest.mock import patch

from kdi_media.semantic_pilot import PilotManifest, PilotManifestError
from kdi_media.semantic_indexing import AssetCandidate
from scripts.run_semantic_indexing import _run_dry_run


ASSET_ID = "11111111-1111-4111-8111-111111111111"


def row(**changes):
    value = {
        "asset_id": ASSET_ID,
        "filename": "IMG_0001.MP4",
        "media_type": "video",
        "extension": "mp4",
        "size_bytes": 100,
        "duration_ms": 1000,
        "selection_reason": "Representative test fixture",
        "risk_flag": "NEEDS_REVIEW",
        "approved_for_external_ai": False,
    }
    value.update(changes)
    return value


class PilotManifestTests(unittest.TestCase):
    def load(self, rows, *, tier=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            payload = {"assets": rows}
            if tier is not None:
                payload["tier"] = tier
            path.write_text(json.dumps(payload), encoding="utf-8")
            return PilotManifest.load(path)

    def test_duplicate_ids_are_deduplicated(self):
        manifest = self.load([row(), row(filename="ignored.MP4")])
        self.assertEqual(len(manifest.assets), 1)

    def test_approved_only_fails_closed(self):
        manifest = self.load([row()])
        self.assertEqual(manifest.selected_ids(approved_only=True), [])
        with self.assertRaises(PilotManifestError):
            manifest.selected_ids(approved_only=True, requested_ids=[ASSET_ID])

    def test_requested_unknown_id_is_rejected(self):
        manifest = self.load([row(approved_for_external_ai=True)])
        with self.assertRaises(PilotManifestError):
            manifest.selected_ids(
                approved_only=True,
                requested_ids=["22222222-2222-4222-8222-222222222222"],
            )

    def test_do_not_send_asset_cannot_be_approved(self):
        with self.assertRaises(PilotManifestError):
            self.load(
                [row(risk_flag="DO_NOT_SEND_EXTERNALLY", approved_for_external_ai=True)]
            )

    def test_low_risk_tier_cannot_contain_do_not_send_asset(self):
        with self.assertRaises(PilotManifestError):
            self.load([row(risk_flag="DO_NOT_SEND_EXTERNALLY")], tier="low-risk")

    def test_real_manifest_has_twenty_unapproved_assets(self):
        manifest = PilotManifest.load("data/semantic_pilot_manifest.json")
        self.assertEqual(manifest.tier, "clinical")
        self.assertEqual(len(manifest.assets), 20)
        self.assertEqual(manifest.selected_ids(approved_only=True), [])
        self.assertEqual(sum(a.media_type == "image" for a in manifest.assets), 7)
        self.assertEqual(sum(a.media_type == "video" for a in manifest.assets), 13)

    def test_low_risk_manifest_is_separate_unapproved_tier(self):
        manifest = PilotManifest.load("data/semantic_pilot_low_risk_manifest.json")
        self.assertEqual(manifest.tier, "low-risk")
        self.assertEqual(len(manifest.assets), 17)
        self.assertEqual(manifest.selected_ids(approved_only=True), [])
        self.assertTrue(all(a.risk_flag == "LOW_RISK_FOR_PILOT" for a in manifest.assets))

    def test_twenty_one_unique_assets_are_rejected(self):
        rows = [
            row(asset_id=f"00000000-0000-4000-8000-{index:012d}")
            for index in range(21)
        ]
        with self.assertRaises(PilotManifestError):
            self.load(rows)

    def test_missing_manifest_is_rejected(self):
        with self.assertRaises(PilotManifestError):
            PilotManifest.load("data/does-not-exist.json")

    def test_dry_run_is_provider_free_and_write_free(self):
        candidate = AssetCandidate(
            asset_id=ASSET_ID,
            file_name="IMG_0001.MP4",
            mime_type="video/mp4",
            file_extension="mp4",
            content_hash="abc",
            updated_at="2026-01-01T00:00:00Z",
            size_bytes=100,
            google_file_id="canonical-drive-id",
            media_category="video",
        )

        class ReadOnlyRepository:
            def fetch_candidate(self, asset_id):
                self.assertion = asset_id
                return candidate

            def __getattr__(self, name):
                raise AssertionError(f"dry-run attempted unexpected operation: {name}")

        output = io.StringIO()
        with (
            patch(
                "scripts.run_semantic_indexing.get_description_provider",
                side_effect=AssertionError("description provider called"),
            ),
            patch(
                "scripts.run_semantic_indexing.get_embedding_provider",
                side_effect=AssertionError("embedding provider called"),
            ),
            redirect_stdout(output),
        ):
            result = _run_dry_run(
                SimpleNamespace(asset_id=[ASSET_ID], limit=20), ReadOnlyRepository()
            )
        report = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(report["external_ai_calls"], 0)
        self.assertEqual(report["database_writes"], 0)
        self.assertEqual(report["semantic_inserts"], 0)
        self.assertEqual(report["embedding_inserts"], 0)


if __name__ == "__main__":
    unittest.main()
