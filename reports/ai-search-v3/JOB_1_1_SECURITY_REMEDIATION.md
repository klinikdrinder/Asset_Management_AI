# KDI AI Search V3 — Job 1.1 Security Remediation

## 1. Original privilege problem

Before remediation, both `anon` and `authenticated` had effective `TRUNCATE` on six public AI-intelligence tables: `asset_ai_profiles`, `asset_metadata_assertions`, `asset_people`, `asset_search_concepts`, `asset_transcript_chunks`, and `asset_video_segments`. RLS does not govern `TRUNCATE`.

Both `public.queue_new_asset_visual_index()` and `public.rls_auto_enable()` were SECURITY DEFINER with null ACLs, which meant PostgreSQL's built-in `PUBLIC EXECUTE` applied.

## 2. Root cause

The table privileges were direct ACL entries granted by owner `postgres`:

- `anon=Dxtm/postgres`
- `authenticated=Dxtm/postgres`

There was no role inheritance and no table grant through `PUBLIC`. The letters include `D` (TRUNCATE), `x` (REFERENCES), `t` (TRIGGER), and PostgreSQL 17 `m` (MAINTAIN). The direct entries came from the `postgres` default table privileges for schema `public`.

The functions had `proacl = null`, so their exposure came from PostgreSQL's built-in function default rather than an explicit application grant.

## 3. Exact grants changed

For the six named tables, the migration revoked `TRUNCATE` from `PUBLIC`, `anon`, and `authenticated`. It deliberately preserved:

- Existing SELECT policies/grants.
- `service_role` privileges used by backend processing.
- `postgres` owner privileges used by migrations.
- Other privileges outside this narrow destructive-access fix.

Client DELETE was false before and remains false after remediation.

## 4. Function dependency analysis

### `queue_new_asset_visual_index()`

- Owner: `postgres`.
- SECURITY DEFINER; `search_path = ''`.
- Purpose: enqueue/update an `asset_visual_index_jobs` row when an asset's content hash or MIME type changes.
- Dependency: enabled row trigger `assets_queue_visual_index` on `public.assets`.
- Repository references: definition and trigger creation in the visual-search migration; Job 1 reports/draft only.
- No direct RPC, Python, TypeScript, Next.js, worker, or test invocation exists.
- Direct trusted-role grant required: NONE. Trigger execution remains functional without caller EXECUTE.

### `rls_auto_enable()`

- Owner: `postgres`.
- SECURITY DEFINER; `search_path = pg_catalog`.
- Purpose: enable RLS automatically on newly created public tables.
- Dependency: enabled event trigger `ensure_rls` on DDL command end.
- No direct RPC or application/worker call exists.
- Direct trusted-role grant required: NONE. Event-trigger execution remains functional.

## 5. Function grants changed

For both functions, `EXECUTE` was revoked from `PUBLIC`, `anon`, and `authenticated`. Owner `postgres` retains execution. No service-role grant was added because no direct backend call was found.

Search V1/V2 grants were untouched. Post-migration checks confirm `authenticated` can still execute both hybrid-search RPCs.

## 6. Default privilege findings

The migration removed future `TRUNCATE` grants to client roles from the `postgres` owner's public-table defaults and made the `postgres` public-function default owner-only.

Afterward:

- Postgres table default ACL no longer grants `TRUNCATE` to `anon` or `authenticated`.
- Postgres function default ACL is `postgres=X/postgres`.
- Future V3 migrations are safe when applied through the verified `postgres` migration runner.
- Supabase-managed `supabase_admin` defaults remain platform-managed and broad; the project migration runner is not a member and cannot alter them. Job 2 must not create tables through a dashboard/supabase_admin-owned DDL path. This is an operational guardrail, not a blocker for the established migration workflow.

## 7. Migration

Local and remote-aligned filename:

`supabase/migrations/20260819052309_ai_search_v3_job1_1_security_remediation.sql`

Remote migration history records version `20260819052309` and name `ai_search_v3_job1_1_security_remediation`.

The review-only `202608190001_ai_search_v3_job1_cleanup_draft.sql` was not applied.

## 8. Post-migration verification

Every affected table now reports:

- anon TRUNCATE: false
- authenticated TRUNCATE: false
- anon DELETE: false
- authenticated DELETE: false
- service_role TRUNCATE: true (preserved backend ACL)
- postgres TRUNCATE: true (owner)

Both functions now report:

- PUBLIC direct EXECUTE: false
- anon effective EXECUTE: false
- authenticated effective EXECUTE: false
- service_role effective EXECUTE: false
- postgres effective EXECUTE: true

The asset trigger and RLS event trigger both still exist and are enabled. Post-change security advisors no longer report either function or any of the six tables.

## 9. Regression tests

- TypeScript typecheck: PASS.
- Dashboard unit/auth/search/security/library suite: PASS — 238 server tests plus 2 client tests.
- Supabase trusted-client preflight: PASS; service credential, project access, approved-profile lookup, and secret-exposure checks passed.
- Python suite: PASS — 625 tests plus 74 subtests.
- Live login: PASS, HTTP 200.
- Live `/library`: PASS, expected unauthenticated HTTP 307 redirect.
- Search V1/V2: PASS; authenticated execute privileges remain true and both live functions invoke without SQL errors while unauthenticated context returns zero authorized rows.
- Production build: intentionally not run to protect live `.next`.

## 10. Data-integrity verification

| Check | Result |
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
| duplicate canonical hash groups | 0 |
| invalid visual embeddings | 0 |

No application row or media object was changed.

## 11. Remaining blockers

None for Job 2, provided all Job 2 DDL is applied through the verified postgres-owned migration workflow and every new exposed table/function receives an explicit privilege and RLS review.

General duplicate-index/cleanup review remains intentionally separate and is not a Job 2 blocker.

## 12. Recommendation

**READY for Job 2 after owner review.** The two critical Job 1 blockers are remediated and verified. Stop here; do not begin Job 2 automatically.

