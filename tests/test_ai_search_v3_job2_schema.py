from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "supabase/migrations/20260819054255_ai_search_v3_job2_core_schema.sql").read_text(encoding="utf-8").lower()
SEED = (ROOT / "supabase/migrations/20260819054325_ai_search_v3_job2_ontology_seed.sql").read_text(encoding="utf-8").lower()


class Job2CoreSchemaMigrationTests(unittest.TestCase):
    def test_additive_scope_only(self):
        combined = CORE + SEED
        for pattern in (r"\bdrop\s+table\b", r"\bdrop\s+column\b", r"\btruncate\s+table\b", r"\bdelete\s+from\b"):
            self.assertIsNone(re.search(pattern, combined))
        for forbidden in ("asset_scenes", "asset_keyframes", "hybrid_search_assets_v3", "scene_embeddings"):
            self.assertNotIn(forbidden, combined)

    def test_all_required_tables_and_rls(self):
        tables = (
            "people", "treatments", "treatment_aliases", "anatomy_terms",
            "actions", "locations", "asset_derivatives",
            "asset_access_control", "ai_analysis_runs",
        )
        for table in tables:
            self.assertIn(f"create table public.{table}", CORE)
            self.assertIn(f"alter table public.{table} enable row level security", CORE)

    def test_identity_and_hierarchy_contracts(self):
        self.assertIn("code text not null unique", CORE)
        self.assertIn("parent_id uuid references public.treatments(id) on delete restrict", CORE)
        self.assertIn("parent_id uuid references public.anatomy_terms(id) on delete restrict", CORE)
        self.assertIn("parent_id uuid references public.locations(id) on delete restrict", CORE)
        self.assertIn("treatment_aliases_normalized_language_unique", CORE)

    def test_existing_table_links_are_nullable_and_safe(self):
        self.assertIn("add column person_id uuid references public.people(id) on delete set null", CORE)
        for field, table in (
            ("primary_treatment_id", "treatments"),
            ("primary_anatomy_id", "anatomy_terms"),
            ("primary_location_id", "locations"),
        ):
            self.assertIn(f"add column {field} uuid references public.{table}(id) on delete set null", CORE)

    def test_asset_relations_and_access_control(self):
        self.assertIn("asset_id uuid primary key references public.assets(id) on delete cascade", CORE)
        self.assertIn("asset_id uuid not null references public.assets(id) on delete cascade", CORE)
        self.assertIn("insert into public.asset_access_control(asset_id)", CORE)
        self.assertIn("select id from public.assets", CORE)

    def test_clients_have_read_only_or_no_direct_access(self):
        self.assertIn("from public,anon,authenticated", CORE)
        self.assertIn("grant select on table", CORE)
        self.assertNotRegex(CORE, r"grant\s+(insert|update|delete|truncate|all).*to\s+authenticated")
        for policy in (
            "people_active_app_read", "treatments_active_app_read",
            "treatment_aliases_active_app_read", "anatomy_terms_active_app_read",
            "actions_active_app_read", "locations_active_app_read",
        ):
            self.assertIn(policy, CORE)
        self.assertGreaterEqual(CORE.count("private.is_active_app_user()"), 6)

    def test_seed_is_stable_and_idempotent(self):
        for code in (
            "hair_restoration", "hair_transplant", "hair_transplant_fue",
            "fue_hairline_design", "fue_extraction", "fue_implantation",
            "scalp", "frontal_hairline", "face", "under_eye", "neck",
            "consulting", "drawing_hairline", "extracting_grafts",
            "clinic", "consultation_room", "operating_room",
        ):
            self.assertIn(f"'{code}'", SEED)
        self.assertGreaterEqual(SEED.count("on conflict(code) do update"), 8)
        self.assertIn("on conflict(normalized_alias,language) do update", SEED)

    def test_no_biometric_or_patient_identity_schema(self):
        combined = CORE + SEED
        for forbidden in ("face_embedding", "face_template", "biometric_reference", "automatic_face_match"):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
