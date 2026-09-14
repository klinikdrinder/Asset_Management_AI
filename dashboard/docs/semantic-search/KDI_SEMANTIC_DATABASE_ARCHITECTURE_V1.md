# KDI Semantic Database Architecture V1

Status: deployed and validated on 2026-08-24. Migration history is aligned at 56 repository/live migrations. Human review remains pending and Phase 10 overall remains `AWAITING_HUMAN_REVIEW`.

## Contract

The database stores the locked 18 layers in `semantic_layer_definitions` and one versioned status per asset/layer/run in `asset_semantic_layers`. Canonical semantic truth is limited to `OBSERVED`, `FALSE`, `UNKNOWN`, and `NOT_APPLICABLE`. Processing and human-review status are separate fields. The current contracts are `semantic_index_v1` and `KDI_SEMANTIC_V2`.

`semantic_analysis_runs` is the lineage root. Its replay key is asset, run type, source fingerprint, processor version, and configuration fingerprint. It carries ontology, indexing, embedding, parser, retrieval, ranking, reranker, benchmark, pilot-manifest, semantic-spec, processor, and configuration versions.

## Assertions and evidence

`semantic_assertions` is the normalized fact store. Facts can target an asset, scene, event, keyframe, anonymous person, or other non-biometric subject. Specialized domain tables remain valid sources. Flexible values use one typed scalar column or JSONB; ontology identity remains in canonical codes.

`semantic_assertion_evidence` supports asset, scene, event, keyframe, transcript, OCR, and human-review evidence. Search-critical `OBSERVED` assertions require evidence. Search-critical `FALSE` assertions require complete negative evidence, preventing absence-of-detection from becoming false truth.

## Temporal and domain model

`asset_scenes` partitions video time; `asset_events` represents multiple semantic events within a scene; `asset_keyframes` supplies visual evidence and never substitutes for video meaning. Existing normalized people, appearances, anatomy, treatment, action, relationship, clinical-observation, environment, cinematography, and composition tables remain domain sources. People are anonymous observations only: no face recognition or biometric identifiers.

Transcripts and OCR retain raw and normalized text, timing, language, confidence, provider/model/version, fingerprints, run lineage, and an independent search/review state. `semantic_narratives` distinguishes asset narrative, short summary, search summary, search-safe narrative, scene narrative, and event narrative. `narrative_claims` and `narrative_claim_evidence` retain claim-level support.

## Human review and gold

Review sessions, decisions, and revisions are separate. Decisions are `APPROVE_AS_IS`, `CORRECT`, `REJECT`, `CONFIRM_UNKNOWN`, or `NOT_APPLICABLE`. Revisions append; no human rows are seeded.

Gold sets/assets/assertions preserve source AI assertion, decision, correction, reason, revision, source fingerprint, and gold fingerprint. Signed-off sets are immutable; changes require a new revision. `effective_semantic_assertions` resolves:

1. signed human gold;
2. human-approved/corrected AI assertion;
3. current unverified AI assertion.

Legacy documents are intentionally absent from the canonical resolver, so they cannot override canonical `UNKNOWN` or another canonical state.

## Search and embeddings

`asset_search_concepts_v2` is source material only. `search_document_builds` stores future document version/fingerprint/staleness metadata; Phase 11 documents are not generated here.

`semantic_embeddings` supports asset, scene, event, transcript, OCR, and narrative scopes. Each row records provider, model, version, dimensions, fingerprints, semantic version, run, and staleness. The unconstrained `vector` value is paired with a `vector_dims(embedding)=dimensions` check, safely allowing 512-dimensional OpenCLIP and 1024-dimensional semantic/text vectors without inserting either into a conflicting fixed-dimension column. Vector indexes must be scope/model/dimension-specific and are deferred until populated workloads justify them.

## Staleness and reprocessing

- Source media change: stale all semantic outputs, documents, and embeddings.
- OCR model change: stale OCR, dependent narratives/documents, and their embeddings.
- Transcript model change: stale transcript, dependent narratives/documents, and their embeddings.
- Ontology change: stale affected normalized concepts, narratives, documents, and derived embeddings.
- Embedding model change: stale embeddings only.

Reprocessing inserts a new run and assertions, then supersedes old rows; it does not destructively rewrite history. Human gold always remains effective over later AI suggestions.

## Security and operations

All new exposed tables enable RLS. Asset-readable semantic rows delegate to the existing `private.can_user_view_asset(asset_id)` permission resolver backed by asset access control. Views are `security_invoker`. Review/gold writes require a trusted backend/service role; authorized users receive asset-filtered effective reads. There are no unrestricted client semantic writes and the service-role key must never reach the client.

The ingestion service is [semantic-repository.ts](../../db/semantic-repository.ts). It creates idempotent runs, writes status/assertions/evidence and temporal/text/narrative records, records real review decisions, resolves effective facts, and marks downstream data stale. Shadow pilot outputs remain dry-run input; no pilot semantic facts, human decisions, gold records, search documents, or embeddings were created by deployment.

## Deployment validation

The authoritative Phase 10 migration and two forward corrections are deployed. Live validation confirms 18 ordered layer definitions, 17/17 semantic tables with RLS, two `security_invoker` views, transactional relational/precedence/immutability tests, permission isolation, and a temporary-table scale test covering 1,000 assets, 18,000 layer rows, 100,000 assertions, and 100,000 evidence rows.
