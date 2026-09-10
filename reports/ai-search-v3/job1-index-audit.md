# Job 1 Index Audit

No index was changed or removed. Usage statistics were not treated as removal evidence.

## Exact or effectively exact duplicates — REVIEW BEFORE REMOVAL

- `asset_sources`: `asset_sources_asset_id_idx` / `idx_asset_sources_asset`; `asset_sources_relationship_type_idx` / `idx_asset_sources_relationship`; `asset_sources_asset_source_unique` / `uq_asset_sources_asset_source`; and overlapping/duplicate source-file indexes `asset_sources_source_file_unique`, `uq_asset_sources_source_file`, `idx_asset_sources_source_file`.
- `scan_runs`: `idx_scan_runs_sync_run` / `scan_runs_sync_run_id_idx`.
- `source_files`: `idx_source_files_google_file_id` / `source_files_google_file_id_idx`; `source_files_folder_google_file_unique` / `uq_source_files_folder_google_file`.
- `source_folders`: `source_folders_google_folder_id_key` / `source_folders_google_folder_id_unique`.
- `asset_destinations`: the partial indexes `asset_destinations_google_file_id_idx` and `asset_destinations_google_file_id_unique` share keys/predicate, but uniqueness semantics differ; classify as functionally redundant candidate, not an automatic duplicate.

The Supabase performance advisor independently confirms the duplicate groups above except the uniqueness-semantic cases.

## KEEP

- Primary-key and unique identity indexes.
- `assets_content_hash_unique`: canonical deduplication.
- `assets_file_name_trgm_idx`: filename `ILIKE` search.
- `asset_semantic_index_search_vector_idx`: GIN full-text search.
- Status/claim/retry indexes supporting workers.
- All current relationship and authorization lookup indexes until query plans and production workload are sampled.

## Vector indexes

No HNSW or IVFFlat vector index is currently present. Both search RPCs calculate cosine distance over small sets using joins/model predicates. KEEP current scalar identity/model indexes. A vector ANN index is a FUTURE V3 INDEX only after query shape, dimensions, partial model predicate, recall, and scale are fixed.

## Search/text indexes

- GIN: `asset_semantic_index_search_vector_idx`.
- Trigram GIN: `assets_file_name_trgm_idx`.
- Supporting structured indexes exist on semantic content type/status and AI-profile/search-concept fields.

## Indexes used by current hybrid search

The functions predicate/join on asset IDs, semantic status, embedding model identity, verified destination asset ID/state, source-link asset/source IDs, folder activity, extension/category, search vector, and filename. Relevant PK/FK/scalar, GIN full-text, and trigram indexes are retained. Vector distance is not ANN-indexed.

## MISSING RECOMMENDED INDEX — review workload first

Uncovered FK leading columns include:

- Admin/auth: `admin_auth_audit.admin_account_id`, `admin_sessions.admin_account_id`.
- User management: `app_users.created_by`, `app_users.invited_by`, `approved_app_users.created_by`, `user_invitations.invited_by`, audit actor/target IDs.
- Source lifecycle: `source_files.duplicate_of_source_file_id`, `first_seen_scan_run_id`, `last_seen_scan_run_id`.
- Control: `synchronization_locks.owner_run_id`.

These are candidates for referential-action and join performance, not mandatory solely because a linter reports them.

## FUTURE V3 INDEX

Defer search-document, scene/keyframe, transcript, ACL, and ANN index designs to the migrations that introduce those objects. Do not pre-create them in Job 1.

