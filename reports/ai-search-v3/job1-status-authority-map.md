# Job 1 Status Authority Map

No statuses were changed.

## Current distributions

- `assets.upload_status`: PENDING 881.
- `source_files.processing_status`: READY 881; SKIPPED 9.
- `source_files.decision`: TAKE 881; SKIP 9.
- `source_files.access_status`: PENDING 890.
- `asset_destinations.upload_status`: VERIFIED 881.
- `asset_destinations.verification_level`: DESTINATION_METADATA_VERIFIED 873; DESTINATION_SHA256_VERIFIED 8.
- `asset_visual_index_jobs.status`: INDEXED 875; NOT_APPLICABLE 6.
- `asset_semantic_index.indexing_status`: INDEXED 20.
- `migration_events.status`: SUCCESS 1,809; INFO 36.
- `scan_runs.status`: COMPLETED 21; RUNNING 1.
- `sync_runs.status`: COMPLETED 11; CANCELLED 4; FAILED 1.

The 881 asset-level PENDING values conflict conceptually with 881 verified destinations, proving that `assets.upload_status` must not represent final readiness in V3.

## Proposed V3 authority map

| Process | Authoritative table | Authoritative field(s) | Legacy / derived fields |
|---|---|---|---|
| Source discovery/access | `source_files` | `access_status`, first/last-seen and missing/removal fields | folder/scan counters |
| Hashing/canonicalization | `source_files` then `assets` | source hash fields during processing; `assets.content_hash` after canonicalization | `assets.checksum_sha256`, legacy processing status |
| Migration/copy attempt | `asset_destinations` | `upload_status`, attempts, failure, completion timestamps | `assets.migration_status`, `assets.upload_status`, `migration_events.status` as history |
| Destination verification | `asset_destinations` | `verification_level`, `verified_at`, destination ID/URL | `assets.last_verified_at`, master fields |
| Visual indexing | `asset_visual_index_jobs` | `status`, attempt/claim/error fields | presence of `asset_visual_embeddings` is output evidence, not queue authority |
| Semantic indexing | `asset_semantic_index` | `indexing_status`, claim/attempt/error fields | presence of `asset_embeddings` is output evidence |
| AI analysis | future `ai_analysis_runs`; current `asset_ai_profiles` | run status/provenance; profile is current result | do not overload semantic status |
| Final asset readiness | derived view/document, not one legacy field | canonical hash + active source + verified destination + required indexing policy | `assets.upload_status` must not be authoritative |
| Sync/run orchestration | `sync_runs`, `scan_runs` | their own run status | counters are summaries |
| Audit history | `migration_events` and audit tables | immutable event status/type/timestamp | never current-state authority |

Job 2 should define readiness derivation explicitly without rewriting existing status values.

