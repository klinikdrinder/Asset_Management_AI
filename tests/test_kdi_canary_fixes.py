from __future__ import annotations

import unittest

from kdi_media.canonical_rows import document_row, narrative_row, scene_row
from kdi_media.canonical_rows import document_row, narrative_row, scene_row, searchable_text
from kdi_media.production_indexer import downgrade_unsupported_clinical_claims
from kdi_media.supabase_production_adapter import CanonicalSemanticPersistenceAdapter


class KdiCanaryFixRegressionTests(unittest.TestCase):
    def test_scene_row_uses_canonical_active_not_active(self):
        row = scene_row(
            asset_id="asset-1",
            run_id="run-1",
            scene=type("Scene", (), {"scene_index": 0, "start_seconds": 0.0, "end_seconds": 2.5, "keyframe_paths": []})(),
            package={"layers": [{"layer_id": "GLOBAL_ASSET_UNDERSTANDING", "state": "OBSERVED"}]},
            description="scene description",
            source_fingerprint="abc123",
        )

        self.assertIn("canonical_active", row)
        self.assertNotIn("active", row)
        self.assertFalse(row["canonical_active"])

    def test_scene_upsert_uses_canonical_scene_version_key(self):
        self.assertEqual(
            CanonicalSemanticPersistenceAdapter._conflict("asset_scenes"),
            "asset_id,scene_index,semantic_version",
        )

    def test_scene_and_keyframe_tables_do_not_receive_active(self):
        self.assertNotIn("asset_scenes", CanonicalSemanticPersistenceAdapter.ACTIVE_TABLES)
        self.assertNotIn("asset_keyframes", CanonicalSemanticPersistenceAdapter.ACTIVE_TABLES)

    def test_document_row_blocks_unsupported_procedure_leakage(self):
        with self.assertRaises(RuntimeError) as caught:
            document_row(
                document_id="doc-1",
                run_id="run-1",
                asset_id="asset-1",
                filename="IMG_1460.MP4",
                media_type="VIDEO",
                text="Procedure in the room.",
                positives=[],
                document_type="ASSET",
                source_fingerprint="abc123",
            )

        self.assertIn("SEARCH_DOCUMENT_CLINICAL_LEAKAGE", str(caught.exception))

    def test_document_row_allows_supported_grounded_procedure_claim(self):
        row = document_row(
            document_id="doc-2",
            run_id="run-2",
            asset_id="asset-2",
            filename="IMG_1460.MP4",
            media_type="VIDEO",
            text="Grounded procedure evidence describes a clinical procedure.",
            positives=[{
                "canonical_code": "TREATMENT_PROCEDURE",
                "display_text": "Grounded procedure evidence describes a clinical procedure.",
                "concept_type": "TREATMENT_PROCEDURE",
                "semantic_state": "OBSERVED",
                "confidence": 0.8,
                "origin": "AI_MODEL",
                "search_critical": True,
                "resolution_source": "UNVERIFIED_AI",
            }],
            document_type="ASSET",
            source_fingerprint="abc123",
        )

        self.assertEqual(row["status"], "READY")

    def test_unknown_procedure_is_removed_from_searchable_narrative(self):
        row = narrative_row(
            run_id="run-3",
            asset_id="asset-3",
            package={"layers": []},
            text="A procedure appears to be taking place.",
            positives=[],
        )

        self.assertNotIn("procedure", row["text"].lower())
        self.assertIn("observation", row["text"].lower())

    def test_unsupported_clinical_claim_is_downgraded_to_unknown(self):
        package = {"layers": [{"layer_id": "CLINICAL_VISUAL_OBSERVATIONS", "state": "OBSERVED"}]}
        downgrade_unsupported_clinical_claims(package, ["CLINICAL_VISUAL_OBSERVATIONS"])

        self.assertEqual(package["layers"][0]["state"], "UNKNOWN")

    def test_unknown_procedure_is_excluded_from_searchable_text(self):
        text = searchable_text(
            "IMG_1460.MP4",
            {"narrative": "A procedure appears to be taking place.", "layers": []},
            positives=[],
        )

        self.assertNotIn("procedure", text.lower())


if __name__ == "__main__":
    unittest.main()
