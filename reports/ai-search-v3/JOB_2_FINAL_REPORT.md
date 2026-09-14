# KDI AI Search V3 — Job 2 Final Report

## Outcome

Job 2 is complete and limited to the normalized core schema, controlled ontology seed, conservative access-control backfill, provenance/derivative foundations, documentation, and tests. No Job 3 structure or processing was started.

## 1. Migration filenames

- `20260819054255_ai_search_v3_job2_core_schema.sql`
- `20260819054325_ai_search_v3_job2_ontology_seed.sql`
- `20260819054605_ai_search_v3_job2_reviewed_by_index.sql`

The third migration is a narrow advisor-driven FK index completion. The Job 1 cleanup draft was not applied.

## 2. Tables created and counts

| Table | Rows |
|---|---:|
| people | 0 |
| treatments | 12 |
| treatment_aliases | 6 |
| anatomy_terms | 25 |
| actions | 22 |
| locations | 11 |
| asset_derivatives | 0 |
| asset_access_control | 881 |
| ai_analysis_runs | 0 |

No person identity, derivative, or analysis-run row was invented.

## 3. Existing tables altered

- `asset_people.person_id uuid NULL → people.id ON DELETE SET NULL`.
- `asset_ai_profiles.primary_treatment_id uuid NULL → treatments.id ON DELETE SET NULL`.
- `asset_ai_profiles.primary_anatomy_id uuid NULL → anatomy_terms.id ON DELETE SET NULL`.
- `asset_ai_profiles.primary_location_id uuid NULL → locations.id ON DELETE SET NULL`.

Existing free-text fields and all existing rows were preserved. No automatic verified-name or free-text mapping occurred.

## 4. Ontology seed

- Treatment hierarchy: 1 root, 11 descendants, including 9 FUE workflow concepts.
- Aliases: 6 normalized English aliases; zero duplicate normalized/language groups.
- Anatomy: 3 roots and 22 descendants covering the requested scalp, face, and neck hierarchy.
- Actions: 22 controlled verbs.
- Locations: 4 generic roots and 7 clinic children.
- Duplicate code groups: zero in every ontology table.

Seed operations use stable codes and `ON CONFLICT` upserts, so replay does not duplicate records.

## 5. Access-control backfill

Exactly one conservative row exists for each of 881 assets. No clinical, consent, marketing, external-AI, or download decision was guessed. V1/V2 behavior does not depend on this table.

## 6. RLS policies and privileges

All nine new public tables have RLS enabled.

Authenticated active-app-user SELECT policies exist only on the six reference tables. The three sensitive/operational tables have no client policy or direct privilege and remain service-only pending per-asset enforcement.

All privileges were explicitly revoked from PUBLIC, anon, and authenticated before narrow SELECT grants. Live verification confirms:

- anon TRUNCATE on every new table: false.
- authenticated TRUNCATE on every new table: false.
- authenticated INSERT/UPDATE/DELETE on every new table: false.
- PUBLIC table grants: none.
- No new SECURITY DEFINER function.
- Job 1.1 table/function lockdown remains intact.

## 7. Indexes

Unique code and alias constraints supply their own indexes and were not duplicated. Purpose-built indexes cover names, hierarchy parents, alias FK, canonical references, derivative asset/type/status/run, analysis asset/time/status/type, access-control classification/review/external-AI, and reviewer FK. The post-migration FK advisor is clear. No vector index was created.

## 8. Foreign keys and delete behavior

- Hierarchy parents: RESTRICT.
- Treatment aliases: CASCADE with treatment.
- Person/ontology references from existing intelligence: SET NULL.
- Asset-dependent access, runs, and derivatives: CASCADE only when the canonical asset is deliberately deleted.
- Derivative analysis-run link and reviewer identity: SET NULL.

These choices prevent ontology edits from deleting canonical media or existing intelligence.

## 9. Timestamp model

All appropriate tables use `created_at` and `updated_at`. Existing owner-only `public.set_updated_at()` is reused; no redundant timestamp function was introduced.

## 10. Data integrity

| Existing object/check | Result |
|---|---:|
| assets | 881 |
| source_files | 890 |
| asset_sources | 881 |
| asset_destinations | 881 |
| asset_visual_embeddings | 875 |
| asset_semantic_index | 20 |
| asset_embeddings | 20 |
| asset_ai_profiles | 10 |
| orphan asset_sources | 0 |
| orphan destinations | 0 |
| invalid visual embeddings | 0 |
| duplicate canonical hashes | 0 |
| access-control rows missing | 0 |

No embedding, media, source/destination relationship, or existing intelligence row changed.

## 11. Regression tests

- TypeScript typecheck: PASS.
- Dashboard/auth/library/search/security tests: PASS — 238 server tests plus 2 client tests.
- New Job 2 schema migration tests: PASS — included in the Python total.
- Python suite: PASS — 633 tests plus 74 subtests.
- Supabase trusted-client preflight: PASS.
- V1/V2 live execute privileges and invocation: PASS.
- Login: HTTP 200.
- `/library`: expected unauthenticated HTTP 307 redirect.
- Production build: intentionally not run to protect live `.next`.

## 12. Production safety

No frontend file, production server/task/runtime, deployment, media file, Google Drive content, embedding, or AI processing was changed. Existing user behavior remains unchanged.

## 13. Unresolved issues

No Job 3 blocker. Operational guardrail: all future migrations must continue through the verified postgres-owned workflow; platform-managed `supabase_admin` defaults are not the approved V3 DDL path. INFO advisor notices for intentionally inaccessible operational tables and unused new indexes are expected.

## 14. Job 3 readiness

**READY after owner review.** Job 3 must remain separately scoped and must not be started automatically.

