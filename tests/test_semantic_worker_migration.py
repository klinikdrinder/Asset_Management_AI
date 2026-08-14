from pathlib import Path
import unittest


class AtomicSemanticCompletionMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (Path(__file__).parents[1] / "supabase/migrations/202608130001_atomic_semantic_completion.sql").read_text(encoding="utf-8").lower()

    def test_completion_is_one_transaction_and_claim_guarded(self):
        self.assertIn("begin;", self.sql); self.assertIn("commit;", self.sql)
        self.assertIn("indexing_status = 'processing'", self.sql)
        self.assertIn("claim_owner = requested_claim_owner", self.sql)
        self.assertIn("indexing_status = 'indexed'", self.sql)

    def test_embedding_is_exactly_1024_and_written_before_success(self):
        self.assertIn("jsonb_array_length", self.sql)
        self.assertIn("public.vector(1024)", self.sql)
        self.assertIn("insert into public.asset_embeddings", self.sql)

    def test_additive_and_service_role_only(self):
        self.assertNotIn("drop table", self.sql); self.assertNotIn("truncate", self.sql)
        self.assertIn("grant execute", self.sql); self.assertIn("to service_role", self.sql)

    def test_existing_claim_rpc_recovers_stale_leases_and_caps_attempts(self):
        claim_sql = (Path(__file__).parents[1] / "supabase/migrations/202608070001_add_semantic_search.sql").read_text(encoding="utf-8").lower()
        self.assertIn("for update skip locked", claim_sql)
        self.assertIn("claim_expires_at <= now()", claim_sql)
        self.assertIn("attempt_count < 5", claim_sql)

    def test_live_verifier_is_outer_transaction_rollback_safe(self):
        verifier = (Path(__file__).parents[1] / "supabase/verification/verify_atomic_semantic_completion_rollback.sql").read_text(encoding="utf-8").lower()
        self.assertIn("begin;", verifier); self.assertIn("rollback;", verifier)
        self.assertIn("atomic_success_and_rollback_verified", verifier)
        self.assertIn("forced failure left an embedding behind", verifier)
        self.assertNotIn("delete from", verifier); self.assertNotIn("truncate", verifier)


if __name__ == "__main__": unittest.main()
