# KDI AI Search V3 — Job 1 Final Report

## 1. Git checkpoint

- Starting branch: `main`.
- Starting/current commit: `ae469af979826b3dbff02147347c22f66b076751`.
- Starting state: `main` was 18 commits ahead of `origin/main`.
- Safety branch created: `ai-search-v3-job1-safety`.
- Preserved pre-existing user changes: five modified deployment/runtime scripts/tests and one untracked invitation-cleanup script. None was discarded, reset, overwritten, or included as Job 1 work.
- Nothing was pushed.

## 2. Supabase project verified

`asset_management_ai` / `wcqqjpndlwsvatjuqnol`, region `ap-southeast-1`, status `ACTIVE_HEALTHY`, PostgreSQL `17.6.1.147`.

## 3. Production data safety

All database operations were catalog reads, aggregate reads, advisor reads, or privilege checks. No SQL mutation, migration application, index rebuild, embedding operation, media operation, Auth mutation, Drive operation, deployment, or frontend change occurred. The live login endpoint remained reachable with HTTP 200.

## 4. Exact live row counts

| Object | Count |
|---|---:|
| assets | 881 |
| source_files | 890 |
| asset_sources | 881 |
| asset_destinations | 881 |
| asset_visual_embeddings | 875 |
| asset_semantic_index | 20 |
| asset_embeddings | 20 |
| asset_ai_profiles | 10 |
| asset_people / video_segments / transcript_chunks / search_concepts / metadata_assertions | 0 each |

## 5. Core relationship integrity

Assets without sources: 0. Assets without destinations: 0. Orphan source links: 0. Orphan destinations: 0. Duplicate canonical content-hash groups: 0. Missing canonical hashes: 0.

## 6. Embedding integrity

The 875 visual records are all `open_clip / ViT-B-32 / laion2b_s34b_b79k / 512`. Null vectors: 0. Wrong declared/vector dimensions: 0. Duplicate asset/model/version combinations: 0. Orphan asset references: 0. No embedding was changed or regenerated.

## 7. Legacy-column findings

All 881 rows fully populate and exactly agree across `original_file_name/file_name`, `file_size_bytes/size_bytes`, and `checksum_sha256/content_hash`. Current code makes `file_name`, `size_bytes`, and `content_hash` the safest V3 authorities. The master Google fields and asset upload/verification timestamps are empty; destination state belongs in `asset_destinations`.

## 8. Status duplication

`assets.upload_status=PENDING` for all 881 while all 881 destinations are VERIFIED. Therefore asset upload status cannot be final-readiness authority. Source discovery belongs to `source_files`; copy/verification to `asset_destinations`; visual work to `asset_visual_index_jobs`; semantic work to `asset_semantic_index`; final readiness should be derived.

## 9. Duplicate indexes

Exact/functionally duplicate groups were independently found on `asset_sources`, `scan_runs`, `source_files`, and `source_folders`, plus a uniqueness-sensitive overlap on `asset_destinations`. No index was removed.

## 10. Missing indexes

Several FK leading columns lack covering indexes, mainly admin/user-audit and source-history relations. These are review candidates, not automatic additions. No ANN vector index currently exists.

## 11. RLS findings

All 26 public tables have RLS enabled. Ten intentionally server/service-only tables have no policies. A **critical privilege gap** was confirmed: `anon` and `authenticated` both have `TRUNCATE` on `asset_ai_profiles`, `asset_people`, `asset_video_segments`, `asset_transcript_chunks`, `asset_search_concepts`, and `asset_metadata_assertions`. RLS does not protect TRUNCATE. No exploit was attempted and no grant was changed.

## 12. SECURITY DEFINER findings

Search V1/V2 are authenticated-only, have empty search paths, and call active-user authorization. `queue_new_asset_visual_index()` and `rls_auto_enable()` are default-PUBLIC-executable definers; this is a second security blocker. No grant was changed.

## 13. Current Search V2

V2 reads assets, semantic metadata, visual/text embeddings, verified destinations, and active source relationships. It weights visual 65%, text embedding 15%, max(full-text/structured) 15%, and filename 5%, with category/extension filters and bounded pagination. It does not use AI profiles, people, segments, transcripts, concepts, metadata assertions, scenes, keyframes, OCR, ACL rows, or telemetry.

## 14. Risks before Job 2

1. Critical destructive `TRUNCATE` grants to browser roles on six AI tables.
2. Default PUBLIC execute on two SECURITY DEFINER trigger/event-trigger routines.
3. Asset-level status conflicts with verified destination truth.
4. Duplicate indexes require constraint-aware review.
5. Extension placement and leaked-password protection advisor warnings remain.
6. One scan run is currently RUNNING; Job 1 did not alter it.

## 15. Proposed authoritative fields

`assets.file_name`, `assets.size_bytes`, `assets.content_hash`; `asset_destinations` for destination identity, upload, and verification; per-process job/index tables for AI status.

## 16. Proposed V3 groups

Controlled knowledge, asset intelligence, video intelligence, audio/text, ACL, AI traceability, scoped embeddings, search documents, and search telemetry are planned in the migration plan only. No table was created.

## 17. Files changed during Job 1

- All files in `reports/ai-search-v3/`.
- `supabase/migrations/202608190001_ai_search_v3_job1_cleanup_draft.sql` (comments only; not applied).

The six pre-existing dirty files are not Job 1 changes.

## 18. Tests

- TypeScript typecheck: PASS.
- Dashboard unit/auth/search/security suite: PASS, 240 tests total (238 + 2 client).
- Python tests with `PYTHONPATH=src`: PASS, 625 tests + 74 subtests.
- Initial broad Python collection without `PYTHONPATH`: NOT RUN to completion; collection failed because `kdi_media` was not on the import path. Corrected safe invocation passed.
- Production build: NOT RUN because it could disturb the protected live `.next`.
- Destructive database verification scripts: NOT RUN.
- Live reachability: PASS, login HTTP 200.

## 19. Intentionally not changed

No data/schema/grants/policies/indexes/functions/statuses/embeddings, frontend, media, Google Drive content, production task/server/runtime, deployment, or secrets. V1/V2 behavior is unchanged. No Job 2 object or processing began.

## 20. Job 2 recommendation

**NOT READY.** First approve and apply a narrow security migration revoking the six destructive browser-role table grants and unnecessary PUBLIC execute on the two definers, then verify effective privileges, RPC accessibility, advisors, search/auth tests, and exact counts. Stop after Job 1 pending owner review.

