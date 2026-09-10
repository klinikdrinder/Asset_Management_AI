# Current Search Architecture — hybrid_search_assets and V2

## `hybrid_search_assets()` (V1)

V1 is a SECURITY DEFINER, stable SQL RPC callable by `authenticated` only. It locks `search_path` to empty and gates all results with `private.is_active_app_user()`.

It joins `assets` to indexed `asset_semantic_index`, optionally joins `asset_embeddings` by provider/model/version, requires a verified destination, and requires at least one active/non-missing/non-removed source through `asset_sources → source_files → source_folders`.

Ranking weights are 45% semantic vector cosine, 20% full-text rank, 8% treatment trigram, 7% subject trigram, 10% doctor trigram, and 10% filename substring. It supports category, extension, limit (bounded 1–100), and offset (minimum zero).

## `hybrid_search_assets_v2()`

### Inputs and bounds

- Text: `search_query`.
- Visual vector plus provider/model/version.
- Qwen/semantic vector plus provider/model/version.
- Filters: `filter_category`, `filter_extension`.
- Pagination: `result_limit` defaults 25 and is bounded 1–100; `result_offset` is bounded at zero.

### Tables read

`assets`, `asset_semantic_index`, `asset_visual_embeddings`, `asset_embeddings`, `asset_destinations`, `asset_sources`, `source_files`, and `source_folders`. It also invokes `private.is_active_app_user()`.

### Eligibility and permission

The authenticated-only SECURITY DEFINER RPC has `search_path = ''`. Every result requires an active app user, a VERIFIED destination with a non-null destination Google file ID, and at least one source that is not missing, not classified removed, and belongs to an active folder.

### Matching and scoring

- Visual cosine similarity: 65%.
- Qwen/semantic cosine similarity: 15%.
- Text/structured component: 15%, using the greater of PostgreSQL English full-text rank and the average of trigram matches on treatment, subject, and doctor.
- Filename substring: 5%.
- Final score is clamped 0–1 and returned as 0–100 percent.
- Deterministic order: final descending, asset UUID ascending.

Semantic profile data is a left join, so assets without the 20 pilot semantic rows may still rank from visual or filename evidence. Visual embeddings are matched exactly by provider/model/version. V2 returns component scores and total count.

### Filters

Extension uses case-insensitive comparison. Category supports image and video by MIME prefix; document is defined as neither image nor video. V2 does not implement V1's explicit PDF/PPTX extension/MIME classification or an explicit `other` category branch.

### Source/destination handling

Relationships are used for eligibility only. The result does not return source or destination rows/URLs.

## Not currently used by V2

V2 does **not** read `asset_ai_profiles`, `asset_people`, `asset_video_segments`, `asset_transcript_chunks`, `asset_search_concepts`, or `asset_metadata_assertions`. It also has no scenes, keyframes, OCR, ontology entities, per-asset ACL table, search documents, query/session analytics, or feedback signals.

## Current limitations relevant to V3

- Asset-level only; no timecoded scene/keyframe result.
- No controlled vocabulary or alias expansion.
- No transcript/OCR search.
- No explicit ACL relation beyond active-app-user gating.
- No explainable provenance/run trace in results.
- No ANN vector index.
- No search telemetry or feedback learning.
- Structured match is three legacy semantic fields only.

