# AI Search V3 Migration Plan (Planning Only)

No V3 table was created in Job 1.

## Principles

Preserve all current assets, relationships, pilot semantic data, and both embedding stores. Add new structures in reversible, small migrations; backfill only after constraints, RLS, provenance, idempotency, and rollback verification exist. Keep V1/V2 RPCs unchanged for comparison.

## Jobs 2–4 table groups

### Core / controlled knowledge

Future: `people`, `treatments`, `treatment_aliases`, `anatomy_terms`, `actions`, `locations`, `asset_derivatives`.

Define stable IDs, normalized names, alias uniqueness, provenance, lifecycle state, and service-managed writes. Do not overload free-text pilot fields.

### Asset intelligence

Preserve: `asset_ai_profiles`, `asset_people`, `asset_search_concepts`, `asset_metadata_assertions`.

Future: `clinical_observations`. Add explicit observation type, evidence, confidence, source/run, review state, and temporal/asset scope.

### Video intelligence

Future: `asset_scenes`, `asset_keyframes`, `scene_people`, `scene_treatments`, `scene_actions`, `scene_relationships`, `scene_environment`, `scene_cinematography`, `scene_composition`, `scene_narratives`, `marketing_annotations`.

Create scene boundaries before dependent annotations; enforce asset/time bounds and idempotent derivative fingerprints. Keyframes reference scenes and derivatives, never replace originals.

### Audio / text

Preserve `asset_transcript_chunks`. Future: `ocr_observations`. Standardize language, time/page/region scope, provenance, confidence, and review state.

### Security

Future: `asset_access_control`. Design deny/allow semantics, subject type, inheritance, effective dates, indexes, RLS, and an authorization test matrix before exposing any V3 RPC.

### AI traceability

Future: `ai_analysis_runs`. Record provider/model/version, prompt/schema version, input fingerprint, status, timestamps, cost/token/runtime metrics, error classification, reviewer, and outputs. Every generated observation/embedding should trace to a run.

### Embeddings

Preserve without alteration: `asset_visual_embeddings` (875 OpenCLIP 512-d) and `asset_embeddings` (20 current text vectors).

Future: `scene_embeddings`, `keyframe_embeddings`, `transcript_embeddings`. Keep model identity and dimensions explicit, enforce unique scope/provider/model/version, and design partial ANN indexes per model only after benchmarks.

### Search

Future: `asset_search_documents`, `scene_search_documents`, `search_sessions`, `search_queries`, `search_results`, `search_feedback`.

Separate document materialization from query telemetry. Store safe normalized query/evidence and access-controlled result references; define retention and privacy before collecting user behavior.

## Sequencing

1. Resolve Job 1 security blockers and approve authoritative-field/status contracts.
2. Job 2: controlled knowledge, traceability, ACL foundation, and additive constraints/RLS.
3. Job 3: scene/keyframe/transcript/OCR intelligence and derivatives.
4. Job 4: search documents, new embeddings/indexes, V3 RPC, benchmarks, telemetry.
5. Keep V1/V2 available through acceptance and rollback windows.

Each job requires pre/post exact counts, orphan checks, RLS/advisor review, transaction-safe migrations, and explicit non-regression tests.

