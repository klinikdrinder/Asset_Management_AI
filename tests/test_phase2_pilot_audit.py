import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reports" / "semantic-search" / "phase2_pilot_layer_audit.json"
MATRIX = ROOT / "reports" / "semantic-search" / "phase2_pilot_layer_matrix.csv"
CONFLICTS = ROOT / "reports" / "semantic-search" / "phase2_semantic_conflicts.json"
MANIFEST = ROOT / "config" / "semantic-search" / "kdi_semantic_pilot_v1.json"


class Phase2PilotAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_locked_inputs_and_exact_coverage(self):
        self.assertEqual(self.audit["specification_version"], "semantic_index_v1")
        self.assertEqual(self.audit["specification_fingerprint"], "ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c")
        self.assertEqual(self.audit["pilot_manifest_version"], "kdi_semantic_pilot_v1")
        self.assertEqual((self.audit["pilot_count"], self.audit["layer_count"], self.audit["evaluation_count"]), (10, 18, 180))

    def test_only_frozen_pilots_and_every_layer(self):
        expected = {x["asset_id"] for x in self.manifest["assets"]}
        actual = {x["asset_id"] for x in self.audit["evaluations"]}
        self.assertEqual(actual, expected)
        for asset_id in expected:
            rows = [x for x in self.audit["evaluations"] if x["asset_id"] == asset_id]
            self.assertEqual([x["layer_number"] for x in rows], list(range(1, 19)))

    def test_every_evaluation_has_required_audit_fields(self):
        required = {"applicability", "completeness_status", "existing_source", "existing_records", "structured_data", "search_doc_coverage", "embedding_coverage", "confidence_present", "evidence_reference", "human_review", "version_status", "conflict", "notes", "future_action"}
        for row in self.audit["evaluations"]:
            self.assertTrue(required.issubset(row))
            self.assertIn(row["applicability"], {"APPLICABLE", "NOT_APPLICABLE", "UNCERTAIN"})
            self.assertTrue(row["existing_source"] and row["existing_records"] and row["notes"] and row["future_action"])

    def test_preservation_snapshot_is_identical(self):
        self.assertEqual(self.audit["baseline"], self.audit["post_audit"])

    def test_matrix_and_conflicts_parse(self):
        with MATRIX.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 18)
        conflicts = json.loads(CONFLICTS.read_text(encoding="utf-8"))
        self.assertEqual(conflicts["conflict_count"], len(conflicts["conflicts"]))
        self.assertGreater(conflicts["conflict_count"], 0)


if __name__ == "__main__":
    unittest.main()
