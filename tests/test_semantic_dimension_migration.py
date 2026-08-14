from __future__ import annotations

import hashlib
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "supabase/migrations/202608070001_add_semantic_search.sql"
CORRECTIVE = ROOT / "supabase/migrations/202608110001_standardize_semantic_vectors_1024.sql"
HISTORICAL_SHA256 = "BDDB7B390B54793AA6412B4DC2FAD60CF14B1EAED879C843EB1EE8979A2021D0"


class SemanticDimensionMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.historical = HISTORICAL.read_text(encoding="utf-8")
        cls.corrective = CORRECTIVE.read_text(encoding="utf-8")
        cls.lower = cls.corrective.lower()

    def test_deployed_historical_migration_is_byte_for_byte_unchanged(self) -> None:
        self.assertEqual(hashlib.sha256(HISTORICAL.read_bytes()).hexdigest().upper(), HISTORICAL_SHA256)
        self.assertIn("public.vector(1536)", self.historical)

    def test_corrective_migration_is_transactional_and_fail_closed(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertIn("lock table public.asset_semantic_index in access exclusive mode", self.lower)
        self.assertIn("lock table public.asset_embeddings in access exclusive mode", self.lower)
        self.assertIn("semantic_count <> 0 or embedding_count <> 0", self.lower)
        self.assertIn("raise exception", self.lower)
        self.assertNotRegex(
            self.lower,
            r"(?im)^\s*(truncate\b|delete\s+from\s+public\.asset_)",
        )
        self.assertRegex(self.lower, r"commit;\s*$")

    def test_vector_column_constraint_and_query_contract_are_exactly_1024(self) -> None:
        self.assertIn("alter column embedding type public.vector(1024)", self.lower)
        self.assertIn("embedding::public.vector(1024)", self.lower)
        self.assertIn("check (embedding_dimensions = 1024)", self.lower)
        self.assertIn("query_embedding public.vector(1024) default null", self.lower)
        self.assertNotIn("public.vector(1536)", self.corrective)

    def test_rpc_security_grant_and_ranking_contract_are_preserved(self) -> None:
        self.assertRegex(self.lower, r"security definer\s+set search_path = ''\s+stable")
        self.assertIn("private.is_active_app_user() as is_authorized", self.lower)
        self.assertIn("where auth.is_authorized", self.lower)
        for weight in (
            "0.45::numeric as semantic_weight",
            "0.20::numeric as fulltext_weight",
            "0.08::numeric as treatment_weight",
            "0.07::numeric as subject_weight",
            "0.10::numeric as doctor_weight",
            "0.10::numeric as filename_weight",
        ):
            self.assertEqual(self.lower.count(weight), 1)
        self.assertIn("to authenticated", self.lower)
        self.assertNotRegex(self.lower, r"returns table\s*\([^)]*\bembedding\b")

    def test_rpc_keeps_fallback_filters_and_embedding_identity(self) -> None:
        for text in (
            "plainto_tsquery('english', b.q)",
            "si.treatment operator(public.%) b.q",
            "si.subject operator(public.%) b.q",
            "si.doctor_name operator(public.%) b.q",
            "a.file_name ilike",
            "filter_category",
            "filter_extension",
            "ae.embedding_provider = query_embedding_provider",
            "ae.embedding_model = query_embedding_model",
            "ae.embedding_version = query_embedding_version",
        ):
            self.assertIn(text, self.lower)
        self.assertTrue(re.search(r"b\.q is not null or query_embedding is not null", self.lower))


if __name__ == "__main__":
    unittest.main()
