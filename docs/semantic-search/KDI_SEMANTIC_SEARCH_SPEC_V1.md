# KDI Semantic Search Specification V1

## Purpose

This document and its canonical machine-readable counterpart freeze the semantic interpretation contract for KDI Central Media Library / KDI AI Search V3. Future indexing, retrieval, ranking, benchmark, and re-indexing work must identify the exact specification it follows.

## Scope

Phase 1 defines the architecture and contracts only. It does not decode media, extract frames, create scenes or keyframes, transcribe audio, run OCR, generate descriptions or embeddings, replace semantic data, change ranking, change result counts, modify search RPCs, modify permissions, or modify the frontend.

Canonical machine configuration: `config/semantic-search/kdi_semantic_search_spec_v1.json`  
Canonical pilot manifest: `config/semantic-search/kdi_semantic_pilot_v1.json`

## Specification identity

- Specification/indexing version: `semantic_index_v1`
- Status: `LOCKED`
- Layer count: `18`
- Ontology version: `KDI_SEMANTIC_V2`
- Pilot manifest version: `kdi_semantic_pilot_v1`
- SHA-256 specification fingerprint: `ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c`

The fingerprint is calculated from UTF-8 JSON with object keys sorted lexicographically and compact comma/colon separators after omitting only `specification.specification_fingerprint`. It excludes no other field. Repeating that canonicalization over the unchanged configuration must yield the fingerprint above.

## Locked 18 layers

| # | Stable ID | Locked name |
|---:|---|---|
| 1 | `ASSET_IDENTITY_PROVENANCE` | Asset Identity & Provenance |
| 2 | `GLOBAL_ASSET_UNDERSTANDING` | Global Asset Understanding |
| 3 | `TEMPORAL_SCENE_STRUCTURE` | Temporal / Scene Structure |
| 4 | `PEOPLE_ROLES` | People & Roles |
| 5 | `PERSON_APPEARANCE` | Person Appearance |
| 6 | `ANATOMY` | Anatomy |
| 7 | `TREATMENT_PROCEDURE` | Treatment / Procedure |
| 8 | `ACTIONS_EVENTS` | Actions & Events |
| 9 | `RELATIONSHIPS` | Relationships |
| 10 | `CLINICAL_VISUAL_OBSERVATIONS` | Clinical Visual Observations |
| 11 | `ENVIRONMENT` | Environment |
| 12 | `CINEMATOGRAPHY` | Cinematography |
| 13 | `COMPOSITION` | Composition |
| 14 | `SPEECH_TRANSCRIPT_AUDIO` | Speech / Transcript / Audio |
| 15 | `OCR_VISIBLE_TEXT` | OCR / Visible Text |
| 16 | `MARKETING_CONTENT_USAGE` | Marketing & Content Usage |
| 17 | `SEMANTIC_NARRATIVE` | Semantic Narrative |
| 18 | `SEARCH_EMBEDDINGS` | Search & Embeddings |

The machine configuration is authoritative for the locked layer meanings. The names, stable IDs, meanings, numbers, and order are part of this versioned contract.

No implementation change may alter the locked 18-layer semantic architecture without explicit approval, a new specification version, and regression validation.

## Information states

- `OBSERVED`: sufficient evidence supports the value.
- `FALSE`: the concept was evaluated and evidence supports that it is absent or false.
- `UNKNOWN`: available evidence cannot determine the value reliably.
- `NOT_APPLICABLE`: the concept does not logically apply to the asset or context.

`null` is not a semantic state and must not silently represent these four meanings. For a static image, `TEMPORAL_SCENE_STRUCTURE` and `SPEECH_TRANSCRIPT_AUDIO` default to `NOT_APPLICABLE` unless a specific subfield logically applies.

## Evidence and provenance

Locked evidence types are `ASSET_LEVEL`, `SCENE_LEVEL`, `EVENT_LEVEL`, `KEYFRAME_LEVEL`, `TRANSCRIPT`, `OCR`, and `HUMAN_REVIEW`.

Locked provenance origins are `AI_MODEL`, `DETERMINISTIC_PROCESSOR`, `DATABASE_METADATA`, and `HUMAN_REVIEW`.

The assertion contract is `fact`, `value`, `state`, `confidence`, `evidence_type`, `evidence_reference`, `provenance`, `analysis_run_id`, and `human_review_status`. Phase 1 creates no evidence assertions.

## Relevance grades

| Score | Grade | Meaning |
|---:|---|---|
| 3 | `EXACT` | Strongly satisfies the important query requirements. |
| 2 | `STRONG` | Clearly relevant but may miss a secondary or preference-level condition. |
| 1 | `PARTIAL` | Related but satisfies too few conditions to be strong. |
| 0 | `IRRELEVANT` | Does not meaningfully satisfy the request. |
| -1 | `CONTRADICTORY` | Directly conflicts with an explicit query requirement. |

## Ontology version

`KDI_SEMANTIC_V2` is the existing live version identifier and is frozen for this specification. Phase 1 does not expand or mutate ontology rows. The contract requires canonical concept, canonical code, category, aliases, synonyms, status, and version, with capability for treatments, anatomy, actions, roles, environments, procedure stages, content types, marketing uses, synonyms, and negative concepts/exclusions.

Current support is distributed across `treatments`, `treatment_aliases`, `anatomy_terms`, `actions`, `locations`, people/scene roles, controlled relationship/clinical definitions, structured documents, and metadata. A single uniform concept-version column does not exist across those tables; this is later compatibility work, not grounds for a destructive Phase 1 migration.

## Pilot manifest

`kdi_semantic_pilot_v1` freezes the approved Job 5.3 set that Job 6 actually consumed. It contains exactly ten unique registered assets, current source-file links, media types, authorization status, approved replacement relationships, and live SHA-256 content fingerprints. The authoritative lineage is:

1. `reports/ai-search-v3/job5_3-final-pilot-manifest.json` — approved source.
2. `reports/ai-search-v3/job6-pilot-manifest.json` — exact consumed set.
3. `config/semantic-search/kdi_semantic_pilot_v1.json` — versioned frozen Phase 1 manifest.

Earlier 20- and 17-candidate manifests are not competing exact ten-asset approvals. The pre-replacement ten-asset profile set is historical and six blocked originals were explicitly superseded by approved replacements.

## Component version contract

| Key | Frozen value |
|---|---|
| `ontology_version` | `KDI_SEMANTIC_V2` |
| `indexing_version` | `semantic_index_v1` |
| `embedding_version` | `open_clip:ViT-B-32:laion2b_s34b_b79k\|ollama:qwen3-embedding:0.6b:v1` |
| `query_parser_version` | `UNASSIGNED` |
| `retrieval_version` | `UNASSIGNED` |
| `ranking_version` | `job8-v3.5` |
| `llm_reranker_version` | `UNASSIGNED` |
| `benchmark_version` | `UNASSIGNED` |
| `pilot_manifest_version` | `kdi_semantic_pilot_v1` |

`UNASSIGNED` means no independent formal version could be established from project evidence. It does not mean the component is necessarily absent. Existing per-record legacy versions remain preserved and are not relabeled by Phase 1.

## Current-state discovery

| Requested discovery item | Current implementation |
|---|---|
| Semantic specification files | `data/semantic_pilot_manifest.json`, `data/semantic_pilot_low_risk_manifest.json`, semantic pilot docs, Job 5–9 reports, and live `semantic_layer_catalog`; none previously represented this approved architecture end-to-end. |
| Semantic/indexing configuration | Python semantic indexing/worker code, Job 6 pipeline `kdi-ai-search-v3-job6-v1`, `asset_ai_profiles.analysis_version`, search document versions, and analysis-run version fields. |
| Ontology implementation | Normalized `treatments`, `treatment_aliases`, `anatomy_terms`, `actions`, `locations`, `people`, relationship and clinical definition tables; latest live catalog identifier `KDI_SEMANTIC_V2`. |
| Current version fields | `ai_analysis_runs.model_version/pipeline_version/ontology_version`, `asset_embeddings.embedding_version`, visual/scene/keyframe/transcript embedding `model_version`, profile `analysis_version`, search-document `document_version`, semantic-index `description_version`. |
| Current pilot manifest | Approved `job5_3-final-pilot-manifest.json`, exactly consumed by `job6-pilot-manifest.json`. |
| Search document implementation | `asset_search_documents` and `scene_search_documents`, structured JSON plus searchable text, source hash, document version, build status. |
| Embedding implementation | 875 OpenCLIP asset visual vectors at `ViT-B-32/laion2b_s34b_b79k`; 20 Ollama Qwen text vectors at `qwen3-embedding:0.6b/v1`; separate scene, keyframe, transcript, and identity embedding tables. |
| Relevant semantic tables | `asset_ai_profiles`, `asset_semantic_index`, `asset_layer_status`, `asset_metadata_assertions`, `asset_context`, scenes/keyframes and normalized intelligence tables, transcript/OCR, search documents, embedding tables, ontology tables, `ai_analysis_runs`, and `semantic_layer_catalog`. |

## Legacy specification conflict

The live `public.semantic_layer_catalog` contains 18 `KDI_SEMANTIC_V2` rows whose names/order begin with Asset / Technical Metadata, Identity, and Person Appearance and end with Audio / Transcript, OCR, and Multimodal Embeddings. That is a materially different top-level definition.

For all new work governed by `semantic_index_v1`, the JSON configuration in this phase is authoritative and the live catalog is `LEGACY_NON_AUTHORITATIVE_FOR_NEW_INDEXING`. Phase 1 deliberately does not overwrite or delete it because existing records and code may depend on it. A later explicitly approved migration must reconcile or version the database representation without changing historical semantics.

The live migration history also contains Job 9 migrations that are absent from the repository migration directory. This schema/migration drift must be reconciled before any later schema deployment.

## Database compatibility

| Requirement | Existing support | Location | Action |
|---|---|---|---|
| Indexing version | PARTIAL | analysis run `pipeline_version`, profile `analysis_version`, document versions | Preserve; later add/use a dedicated `indexing_version` contract at write time. |
| Ontology version | YES/PARTIAL | `ai_analysis_runs.ontology_version`, `semantic_layer_catalog.ontology_version` | Preserve; later align new runs to this specification and uniform concept versioning. |
| Embedding version | YES | embedding `model_version` / `embedding_version` fields | Preserve independent model identities. |
| Analysis run ID | YES | scenes, assertions, observations, embeddings, transcript/OCR and related tables | Preserve. |
| Provenance | YES/PARTIAL | JSON/text provenance on profiles and normalized intelligence tables | Later normalize origins to the contract without overwriting history. |
| Confidence | YES/PARTIAL | scenes and normalized intelligence/observation tables | Later ensure every uncertain assertion is covered. |
| Semantic state | NO/PARTIAL | scattered status/visibility fields; no uniform four-state assertion contract | Add non-destructively in a later approved phase. |
| Evidence reference | PARTIAL | clinical `evidence` JSON and structured-document evidence | Later add uniform evidence references. |
| Human review | YES/PARTIAL | review status/reviewer fields on scenes, narratives, marketing, access, and observations | Later cover every important assertion uniformly. |

No Phase 1 migration is necessary to store the frozen files safely.

## Change control

A new specification version and explicit approval are required to add, remove, or reorder a top-level layer; change a locked layer meaning; change information-state definitions; change evidence semantics; change relevance-grade semantics; or materially restructure the ontology.

A minor implementation version may cover a bug fix, performance improvement, non-semantic refactor, or logging change only when semantic behavior is unchanged. Every change requires review of the canonical JSON, regenerated fingerprint, and regression validation. Silent mutation is forbidden.

Existing records retain the versions and semantics under which they were produced. Adoption of a newer specification never silently rewrites, relabels, or deletes historical semantic data.

## Validation requirements

Automated validation must prove JSON parsing; exact 18-layer count/names/IDs/order; unique IDs; numbers 1–18; four information states; required evidence types and origins; five relevance grades; all component keys; exactly ten unique and traceable pilot assets; deterministic fingerprint reproduction; and material agreement between this document and the JSON.

Before/after live checks must confirm assets, sources, embeddings, search tables, authorization records, and pilot registrations were preserved. Normal application validation must pass. Any critical failure leaves Phase 1 failed and blocks Phase 2.

## Phase 1 status

`LOCKED`, contingent on the checked-in automated validation and final regression/preservation verification. Phase 1 introduces no database migration and does not authorize Phase 2.
