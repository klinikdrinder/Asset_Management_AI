from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from kdi_media.semantic_pilot import LocalPilotManifest, PilotManifest, PilotManifestError
from kdi_media.semantic_indexing import AssetCandidate
from scripts.run_semantic_indexing import (
    _run_execute,
    local_ai_memory_preflight,
    select_manifest_asset_ids,
)


ASSET_ID = "11111111-1111-4111-8111-111111111111"


def write_manifest(directory: str, name: str, payload: dict) -> str:
    path = Path(directory) / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def local_row(approved: bool = False) -> dict:
    return {
        "asset_id": ASSET_ID,
        "media_type": "image",
        "approved_for_local_ai": approved,
        "approval_reason": "Reviewed for local-only pilot" if approved else None,
        "approved_by": "reviewer@example.invalid" if approved else None,
        "approval_timestamp": "2026-08-11T12:00:00Z" if approved else None,
    }


def external_row(approved: bool = False) -> dict:
    return {
        "asset_id": ASSET_ID,
        "filename": "fixture.jpg",
        "media_type": "image",
        "extension": "jpg",
        "size_bytes": 100,
        "duration_ms": None,
        "selection_reason": "Test fixture",
        "risk_flag": "NEEDS_REVIEW",
        "approved_for_external_ai": approved,
    }


class LocalApprovalTests(unittest.TestCase):
    def test_automatic_exact_twenty_manifest_is_local_only_and_disjoint_from_benchmark(self):
        manifest = LocalPilotManifest.load("data/semantic_local_automatic_pilot_20.json")
        benchmark = json.loads(Path("data/semantic_manual_benchmark_20.json").read_text(encoding="utf-8"))
        benchmark_ids = {row["asset_id"] for row in benchmark["assets"]}
        selected = manifest.selected_ids()
        self.assertEqual(manifest.tier, "clinical")
        self.assertEqual(len(selected), 20)
        self.assertEqual(len(set(selected)), 20)
        self.assertTrue(set(selected).isdisjoint(benchmark_ids))

    def test_both_false_block_both_scopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = LocalPilotManifest.load(write_manifest(
                tmp, "local.json", {"tier": "low-risk", "assets": [local_row()]}
            ))
            external = PilotManifest.load(write_manifest(
                tmp, "external.json", {"tier": "low-risk", "assets": [external_row()]}
            ))
        self.assertEqual(local.selected_ids(), [])
        self.assertEqual(external.selected_ids(approved_only=True), [])

    def test_local_true_does_not_imply_external_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = LocalPilotManifest.load(write_manifest(
                tmp, "local.json", {"tier": "low-risk", "assets": [local_row(True)]}
            ))
            external = PilotManifest.load(write_manifest(
                tmp, "external.json", {"tier": "low-risk", "assets": [external_row()]}
            ))
        self.assertEqual(local.selected_ids(), [ASSET_ID])
        self.assertEqual(external.selected_ids(approved_only=True), [])

    def test_external_true_does_not_imply_local_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = LocalPilotManifest.load(write_manifest(
                tmp, "local.json", {"tier": "low-risk", "assets": [local_row()]}
            ))
            external = PilotManifest.load(write_manifest(
                tmp, "external.json", {"tier": "low-risk", "assets": [external_row(True)]}
            ))
        self.assertEqual(local.selected_ids(), [])
        self.assertEqual(external.selected_ids(approved_only=True), [ASSET_ID])

    def test_clinical_local_approval_cannot_bypass_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(
                tmp, "local.json", {"tier": "clinical", "assets": [local_row(True)]}
            )
            args = SimpleNamespace(
                manifest=path, local_only=True, tier="clinical", execute=True,
                confirm_clinical_local_processing=False,
                confirm_clinical_external_processing=False, asset_id=None,
                approved_only=False,
            )
            with self.assertRaises(PilotManifestError):
                select_manifest_asset_ids(args)

    def test_missing_local_flag_defaults_to_blocked(self):
        value = local_row()
        del value["approved_for_local_ai"]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = LocalPilotManifest.load(write_manifest(
                tmp, "local.json", {"tier": "low-risk", "assets": [value]}
            ))
        self.assertEqual(manifest.selected_ids(), [])


class MemoryPreflightTests(unittest.TestCase):
    def test_ram_preflight_pass(self):
        self.assertTrue(local_ai_memory_preflight(
            available_mb=4096, required_mb=3072
        )["ok"])

    def test_ram_preflight_blocks(self):
        self.assertFalse(local_ai_memory_preflight(
            available_mb=512, required_mb=3072
        )["ok"])

    def test_block_occurs_before_provider_or_database_write(self):
        candidate = AssetCandidate(
            asset_id=ASSET_ID, file_name="fixture.jpg", mime_type="image/jpeg",
            file_extension="jpg", content_hash="a" * 64,
            updated_at="2026-01-01T00:00:00Z", size_bytes=100,
            google_file_id="drive-id", media_category="image",
        )
        repository = SimpleNamespace(fetch_candidate=lambda _asset_id: candidate)
        args = SimpleNamespace(
            asset_id=[ASSET_ID], retry_failed=False, max_cost=None, limit=1,
            batch_size=1, local_only=True,
        )
        output = io.StringIO()
        with (
            patch("scripts.run_semantic_indexing.local_ai_memory_preflight", return_value={
                "ok": False, "available_mb": 512, "required_mb": 3072,
            }),
            patch("scripts.run_semantic_indexing.get_description_provider") as description,
            patch("scripts.run_semantic_indexing.get_embedding_provider") as embedding,
            redirect_stdout(output),
        ):
            self.assertEqual(_run_execute(args, repository), 0)
        description.assert_not_called()
        embedding.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["database_writes"], 0)


if __name__ == "__main__":
    unittest.main()
