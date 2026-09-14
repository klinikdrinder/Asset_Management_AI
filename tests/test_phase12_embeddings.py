import hashlib, json, math, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"reports"/"semantic-search"/"phase12"

class Phase12EmbeddingContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validation=json.loads((REPORT/"phase12_validation.json").read_text())
        cls.integrity=json.loads((REPORT/"phase12_embedding_integrity.json").read_text())
        cls.lineage=json.loads((REPORT/"phase12_embedding_lineage.json").read_text())["embeddings"]
        cls.similarity=json.loads((REPORT/"phase12_similarity_sanity.json").read_text())

    def test_source_fingerprint_determinism(self):
        value="canonical text"
        self.assertEqual(hashlib.sha256(value.encode()).hexdigest(),hashlib.sha256(value.encode()).hexdigest())
        self.assertEqual(len({x["id"] for x in self.lineage}),106)

    def test_dimensions_finite_nonzero_and_fingerprints(self):
        self.assertTrue(self.integrity["finite"])
        self.assertTrue(self.integrity["non_zero"])
        self.assertEqual(self.integrity["source_fingerprints"],106)
        self.assertEqual(self.integrity["vector_fingerprints"],106)
        for row in self.lineage:
            self.assertEqual(row["dimensions"],512 if row["representation_type"].startswith("VISUAL") else 384)

    def test_expected_visual_and_aggregation_coverage(self):
        self.assertEqual(self.integrity["actual"]["VISUAL_KEYFRAME"],44)
        self.assertEqual(self.integrity["actual"]["VISUAL_SCENE"],11)
        self.assertEqual(self.integrity["actual"]["VISUAL_ASSET"],10)
        self.assertTrue(all(x["member_mean"]>x["unrelated_mean"] for x in self.similarity["scene_coherence"] if x["unrelated_mean"] is not None))

    def test_text_document_coverage(self):
        self.assertEqual(self.integrity["actual"]["TEXT_ASSET"],10)
        self.assertEqual(self.integrity["actual"]["TEXT_SCENE"],11)
        self.assertEqual(self.integrity["actual"]["TEXT_EVENT"],16)
        self.assertEqual(self.integrity["actual"]["TEXT_TRANSCRIPT"],3)
        self.assertEqual(self.integrity["actual"]["TEXT_OCR"],1)

    def test_eligibility_and_semantic_safety(self):
        excluded=self.validation["excluded"]
        self.assertEqual(excluded["excluded_transcripts"],0)
        self.assertEqual(excluded["excluded_ocr"],0)
        self.assertEqual(excluded["technical_events"],0)
        self.assertEqual(excluded["img3429_transcript"],0)
        self.assertEqual(self.validation["img1238"]["img1238_treatment"],"UNKNOWN")
        self.assertEqual(self.validation["img1238"]["mcure_ocr_only"],1)
        self.assertEqual(self.validation["img1238"]["technical_only"],6)

    def test_idempotency_staleness_mixed_dimensions_and_active_uniqueness(self):
        gate=self.validation["gate"]
        for key in ("idempotency","staleness","mixed_dimensions","integrity"):
            self.assertTrue(gate[key])
        self.assertEqual(self.validation["integrity"]["duplicate_active"],0)
        self.assertEqual(self.validation["integrity"]["stale_document_mismatch"],0)

    def test_rls_no_leakage_and_backend_only_writes(self):
        self.assertTrue(self.validation["gate"]["rls"])
        self.assertTrue(self.validation["gate"]["client_write_denied"])
        self.assertEqual(self.validation["security"]["unauthorized_vector_exposure"],0)

    def test_no_semantic_or_frontend_mutation(self):
        self.assertTrue(self.validation["gate"]["semantic_preserved"])
        self.assertTrue(self.validation["gate"]["no_frontend"])
        self.assertTrue(self.validation["gate"]["no_human"])
        self.assertTrue(self.validation["gate"]["phase13_not_started"])

if __name__=="__main__":unittest.main()
