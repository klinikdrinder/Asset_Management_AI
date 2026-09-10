# Fix 01 — Live schema inventory

Generated 2026-09-10 from `information_schema`, `pg_catalog`, exact read-only row retrieval, migrations, and production source inspection. Project: `asset_management_ai` (`wcqqjpndlwsvatjuqnol`, PostgreSQL 17). Counts are exact where stated; no database object or row was changed.

| Object | Type | Exact rows | Purpose / keys | Production search use |
|---|---:|---:|---|---|
| `assets` | table | 881 | Authoritative assets; PK `id`; filename, MIME, master reference | YES: metadata and filename channel |
| `asset_sources` | table | 881 | Asset-to-source relationship | Indirect authorization/source integrity |
| `source_files` | table | 890 | Registered source objects, duplicate and lifecycle state | Indirect authorization |
| `asset_destinations` | table | 881 | Master destination and verification state | Result/media delivery |
| `asset_technical_metadata` | table | 881 | Dimensions, duration, codec, audio | Result metadata; not semantic candidate retrieval |
| `asset_access_control` | table | 881 | Clinical/privacy/consent/use controls; PK/FK `asset_id` | YES through authorization RPC |
| `semantic_specifications` | table | 1 | Locked semantic specification registry | Audit authority, not direct retrieval |
| `semantic_layer_definitions` | table | 18 | Current named 18-layer catalog | Audit authority |
| `semantic_layer_definition_versions` | table | 18 | Locked rich definitions | Audit authority |
| `asset_semantic_layers` | table | 15,822 | Current per-asset/layer processing/completeness; `asset_id`, `layer_id`, `active` | Readiness view, not ranking evidence |
| `asset_layer_status` | table | 15,858 | Legacy `KDI_SEMANTIC_V2` status path | NO current search; legacy |
| `semantic_analysis_runs` | table | 2,722 | Run/version/provenance | No direct retrieval |
| `semantic_assertions` | table | 20,731 | Structured asset/scene/event/keyframe facts | YES: candidates and reranking |
| `semantic_assertion_evidence` | table | 21,141 | Frame/time/source evidence for assertions | Not loaded directly by current reranker |
| `effective_semantic_assertions` | view | derived | Active assertion resolution | Code repository helper only; current candidate path queries table directly |
| `semantic_narratives` | table | 918 | Asset/scene/event narratives | Indirectly via built docs/embeddings |
| `asset_scenes` | table | 1,102 | Scene boundaries, canonical flag, semantic version | YES via scene IDs/evidence and embedding RPC |
| `asset_keyframes` | table | 1,644 | Timestamped frame evidence | YES through visual embedding results |
| `asset_events` | table | 22 | Timed/canonical action events | PARTIAL through assertion/document linkage |
| `scene_people` | table | 18 | 18 people across 10 assets; scene/person binding | NO direct production query |
| `person_appearances` | table | 18 | Appearance records for those scene people | NO direct production query |
| `people` | table | 0 | Canonical person identities | NO |
| `scene_relationships` | table | 7 | Same-scene participant relationships | NO direct production query |
| `clinical_observations` | table | 12 | Structured clinical observations | NO direct production query |
| `asset_transcript_chunks` | table | 98 | Timed speech/transcripts | YES only for explicit transcript-literal requirements; also embedded/doc-derived |
| `ocr_observations` | table | 1,213 | Timed OCR evidence | YES only for explicit OCR-literal requirements; also embedded/doc-derived |
| `search_document_builds` | table | 1,712 | Canonical asset/scene/event documents, versioned active/stale state | YES: canonical full-text and readiness |
| `search_document_concepts` | table | 833 | Normalized concepts/evidence links for canonical docs | Not directly queried by production retriever |
| `search_document_evidence` | table | 794 | Document-to-assertion/frame/transcript/OCR evidence | Not directly queried by production retriever |
| `search_document_build_runs` | table | 884 | Build lineage/version counts | Audit only |
| `asset_search_concepts_v2` | table | 270 | Normalized canonical retrieval concepts | YES: structured candidate and reranking source |
| `asset_search_documents` | table | 30 | Earlier asset-document system | LEGACY, not current production |
| `scene_search_documents` | table | 20 | Earlier scene-document system | LEGACY, not current production |
| `asset_semantic_index` | table | 20 | Original semantic index/searchable text | LEGACY, not current production |
| `asset_ai_profiles` | table | 36 | Earlier denormalized descriptions/person fields | LEGACY, not current production |
| `semantic_embeddings` | table | 7,295 | Canonical multi-representation pgvector corpus | YES through `match_kdi_semantic_search_embeddings` |
| `asset_visual_embeddings` | table | 875 | Earlier asset-level OpenCLIP vectors | LEGACY, not queried by canonical retriever |
| `asset_embeddings` | table | 20 | Earlier text/vector family | LEGACY, not queried by canonical retriever |
| `scene_embeddings` | table | 10 | Earlier scene vector family | LEGACY, not queried by canonical retriever |
| `keyframe_embeddings` | table | 10 | Earlier keyframe vector family | LEGACY, not queried by canonical retriever |
| `transcript_embeddings` | table | 0 | Earlier transcript vector family | UNUSED |
| `kdi_search_ready_assets_v1` | view | 881 | Current readiness gate: layer/doc/scene compatibility | YES, mandatory post-union filter |
| `current_asset_semantic_state` | view | derived | Consolidated semantic status | Audit/other code; not candidate retrieval |
| `search_sessions`, `search_queries`, `search_results` | tables | 0 / 0 / 1 | Search telemetry/session persistence | API writes these in normal production search; audit did not invoke API |

## Relevant live functions

| Function | Volatility / security | Classification | Current use |
|---|---|---|---|
| `match_kdi_semantic_search_embeddings(...)` | STABLE, invoker | Canonical compatible vector matcher | YES |
| `phase18_authorize_candidates_for(...)` | STABLE, invoker | ACL/privacy authorization | YES |
| `hybrid_search_assets_v3(...)` | STABLE, security definer | Previous v3 hybrid RPC | LEGACY; source code does not call it |
| `hybrid_search_assets_v2(...)` | STABLE, security definer | Previous hybrid RPC | LEGACY |
| `hybrid_search_assets(...)` | STABLE, security definer | Original hybrid RPC | LEGACY |
| `match_phase17_semantic_embeddings(...)` | STABLE, invoker | Previous matcher name | LEGACY alias/path |
| `claim_semantic_index_batch`, `complete_semantic_index_atomically` | VOLATILE | Indexing writers | Forbidden/not invoked |

## pgvector and version selection

Current production declares text compatibility as E5-small, 384 dimensions, model version `hf-main-pinned-runtime-v1`, and visual compatibility as OpenCLIP ViT-B-32, 512 dimensions, model version `laion2b_s34b_b79k`. Canonical rows are selected with `active=true`, `stale=false`, exact representation/provider/model/version/dimension compatibility inside the matcher. Historical/inactive vectors remain preserved.

## Asset relationships and ordinal

The authoritative audit universe is the 881 rows in `assets`; all 881 have an `asset_sources`, `asset_destinations`, `asset_technical_metadata`, and ACL row. The database has no authoritative ordinal column on `assets`; `fix01_asset_readiness_matrix.csv` assigns a deterministic audit-only ordinal by case-insensitive filename then asset UUID. It must not be confused with rollout-manifest ordinals.
