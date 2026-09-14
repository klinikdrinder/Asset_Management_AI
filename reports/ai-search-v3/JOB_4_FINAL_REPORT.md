# KDI AI Search V3 — Job 4 final report

## Outcome

Three additive migrations were created, safety-scanned, applied, and verified. Nine new tables remain empty. Mixed 512-d/1024-d vectors, rebuildable full-text projections, conversational context, explainable final-asset rankings, and feedback are structurally supported. Query embedding caching is deliberately deferred. V1/V2 definitions retain their pre-Job hashes.

The post-DDL performance advisor identified eleven composite FKs without fully covering indexes; `20260819063232_ai_search_v3_job4_fk_covering_indexes.sql` added only those indexes. The security advisor's Job 4 notices are informational `RLS enabled, no policy` results, intentional because these tables are backend-only.

## Safety and integrity

No DROP, DELETE, TRUNCATE, existing embedding mutation, ANN index, AI/media processing, frontend change, or production deployment occurred. Composite FKs and owner-only SECURITY INVOKER validation triggers enforce scene/keyframe/transcript/result scope. All new functions have `search_path=''` and no PUBLIC/anon/authenticated/service-role direct EXECUTE. All new tables have RLS and no client privileges.

Permission filtering must occur before ranking and top-N selection. Search projections are derived data and never override normalized semantic, clinical, access-control, or ontology truth.

## Verification

Rollback-only live tests accepted valid 512-d visual and 1024-d semantic vectors and rejected dimension metadata errors, duplicate active model versions, cross-asset parent mismatches, invalid ranks/scores/timestamps, duplicate ranks/assets, invalid feedback, and cross-scope links. Generated full-text vectors matched expected terms. Conversational defaults, explicit counts, parent context, unique sequences, and NEXT_RESULTS offsets passed. No synthetic row persisted.

Existing counts remain: assets 881; source files 890; asset sources 881; destinations 881; visual embeddings 875; semantic index 20; text embeddings 20; AI profiles 10; access control 881; treatments 12; aliases 6; anatomy 25; actions 22; locations 11. Deep-intelligence and new Job 4 production rows remain zero.

Tests: TypeScript PASS; dashboard unit/auth/search/security PASS 240/240; Python PASS 640 plus 74 subtests; transactional database PASS; login HTTP 200; library protected HTTP 307. No build command touched `.next`.

Job 5 is ready from the schema perspective. It must implement permission-first retrieval and remain separately approved. Job 5 was not started.
