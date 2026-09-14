# Job 1 Legacy Column Audit

## Result

All 881 asset rows populate both generations of the filename, size, and SHA-256 fields. Every paired value agrees; no backfill is needed before V3.

| Current field | Current usage | Completeness | Conflicts | Proposed authority | Migration risk | Recommendation |
|---|---|---:|---:|---|---|---|
| `original_file_name` | Compatibility writes in canonicalization and historical migrations/tests | 881/881 | 0 vs `file_name` | `assets.file_name` | Medium: older workers/tests intentionally dual-write | Keep; treat as a compatibility mirror and add drift monitoring later |
| `file_name` | Current UI, repository, search RPC filename scoring, semantic/visual workers, tests | 881/881 | 0 | `assets.file_name` | Low | V3 canonical technical filename |
| `file_size_bytes` | Compatibility writes and canonicalization tests | 881/881 | 0 vs `size_bytes` | `assets.size_bytes` | Medium | Keep read-compatible; stop adding new consumers |
| `size_bytes` | Current UI/repository, sync, workers, integrity tests | 881/881 | 0 | `assets.size_bytes` | Low | V3 canonical technical size |
| `checksum_sha256` | Compatibility writes and canonicalization tests | 881/881 | 0 vs `content_hash` | `assets.content_hash` | Medium | Preserve; later enforce mirror consistency before deprecation |
| `content_hash` | Canonical identity lookup, unique index, queue trigger fingerprint, workers | 881/881 | 0 | `assets.content_hash` | Low | V3 canonical SHA-256 |
| `master_google_file_id` | Historical schema only; current resolution uses destinations | 0/881 | n/a | `asset_destinations.destination_google_file_id` | Low today, high if silently repopulated | Do not populate in V3 |
| `master_google_folder_id` | Historical schema only | 0/881 | n/a | destination/location model | Low | Keep unused pending a later compatibility migration |
| `master_url` | Historical schema only | 0/881 | n/a | `asset_destinations.destination_url` | Low | Keep unused |
| `migration_status` | Legacy canonicalization and migration contracts | 881/881 | Conceptually overlaps destination status | `asset_destinations.upload_status` | High: historical jobs/tests use it | Treat as legacy/derived; never use as V3 readiness authority |
| `upload_status` | Current asset browsing fallback; all 881 are `PENDING` despite verified destinations | 881/881 | 881 conceptual conflicts with verified destinations | `asset_destinations.upload_status` for copy state | High | Do not reinterpret in place; document as legacy asset-level state |
| `uploaded_at` | Historical asset-level upload timestamp | 0/881 | Destination rows hold completion state | `asset_destinations.upload_completed_at` | Low | Destination authority |
| `last_verified_at` | Historical asset-level verification timestamp | 0/881 | Destination rows hold verification | `asset_destinations.verified_at` | Low | Destination authority |

## Code evidence

Repository-wide inspection covered application code, SQL migrations/functions, TypeScript and Python tests, scripts, and Python workers. Current consumers overwhelmingly use `file_name`, `size_bytes`, and `content_hash`. The older triplet is intentionally dual-written in `src/kdi_media/canonicalization.py` and asserted by `tests/test_step9_canonicalization.py`, so removal or renaming would break established contracts.

The current frontend/media path reads canonical fields from `assets` and verified location/state from `asset_destinations`. Search V1/V2 scores `assets.file_name`; semantic workers validate `size_bytes` and `content_hash`.

## Recommendation

Adopt `assets.file_name`, `assets.size_bytes`, and `assets.content_hash` as V3 technical authorities. Adopt `asset_destinations` as authority for master-copy location, upload completion, and verification. Job 2 should add assertions/compatibility views only after callers are enumerated; no current column should be removed, renamed, or overwritten.

