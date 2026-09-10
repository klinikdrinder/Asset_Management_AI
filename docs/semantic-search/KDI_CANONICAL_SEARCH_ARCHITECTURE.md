# KDI Canonical Semantic Search — Architecture and Legacy Deprecation

One production search authority. Everything below either belongs to it, or is explicitly not a
production search path.

## Production flow

```
Frontend
  app/media-library-page.tsx            (server-rendered library search)
  app/dev/library-preview/…             (developer tool — separate, non-production)
        │
        ▼
Canonical API              app/api/search/route.ts            POST /api/search
  (alias, no logic)        app/api/search/v3/route.ts         re-exports POST
        │
        ▼
Canonical orchestrator     db/canonical-production-retriever.ts  executeCanonicalSearch()
        │
        ├── Parser                db/query-interpreter.ts          interpretQuery()
        ├── Vocabulary registry   db/search-vocabulary-registry.ts SEARCH_VOCABULARY
        ├── Requirement model     db/requirement-classifier.ts     classifyRequirements()
        ├── Expansion             db/query-expander.ts             expandQuery()
        ├── Query encoding        db/phase17-query-encoder.ts      E5 384D + OpenCLIP 512D
        ├── Retrieval             db/candidate-retriever.ts        retrieveCandidates()
        ├── Authorization         db/candidate-authorizer.ts       authorizeCandidates()
        ├── Fusion / ranking      db/deterministic-reranker.ts     rerankAuthorizedCandidates()
        └── Count control         db/result-count-controller.ts    applyResultCount()
        │
        ▼
One ranked result list + grounded response
  db/database-grounded-search-response.ts
```

## Retrieval channels

Exact/literal: `FILENAME_LITERAL` (filename and stem; a bare media extension is never a literal),
`METADATA`, `READY_BROWSE`, `OCR_LITERAL`, `TRANSCRIPT_LITERAL`, `FULL_TEXT`.

Structured semantic facts: `STRUCTURED_CANONICAL` and `EXPANDED_STRUCTURED` over
`asset_search_concepts_v2` **and** the authoritative 18-layer observations in `semantic_assertions`.

Vector channels, retrieved independently per model family and fused afterwards — never compared
across families:

| Family | Provider | Model | Dimensions | Representations |
|---|---|---|---|---|
| Text | `sentence_transformers` | `intfloat/multilingual-e5-small` | 384 | `TEXT_ASSET`, `TEXT_SCENE`, `TEXT_EVENT`, `TEXT_TRANSCRIPT`, `TEXT_OCR` |
| Visual | `open_clip` | `ViT-B-32` (`laion2b_s34b_b79k`) | 512 | `VISUAL_ASSET`, `VISUAL_SCENE`, `VISUAL_KEYFRAME` |

`assertEmbeddingCompatibility` rejects any cross-family or wrong-dimension query vector before it
reaches the database.

## Fusion

`db/deterministic-reranker.ts` — channel-aware deterministic scoring, not list concatenation. Hard
constraints and exclusions are satisfied before similarity contributes, so clinical correctness and
MUST/MUST_NOT outrank score. Exact filename enters at `raw_score = 1`, stem at `0.98`, other
filename substring matches at `0.9`. Ties break on score then `asset_id`, so repeated queries over
unchanged data return identical ordering.

## Requirement model

`HARD_CONSTRAINT`, `HARD_EXCLUSION`, `STRONG_REQUIREMENT`, `PREFERENCE`, `NEGATIVE_PREFERENCE`,
`RESPONSE_CONTROL`, `CONTEXT`, `UNRESOLVED`, `CONFLICT` stay distinct. An inferred concept becomes a
strong requirement or preference, never an automatic mandatory filter — the historical all-MUST
zero-result failure.

## Vocabulary registry

`config/semantic-search/kdi_search_vocabulary_v1.json`, exposed by
`db/search-vocabulary-registry.ts`. 14 categories, 106 canonical concepts. It replaces the aliases
that lived inside the parser config and is a strict superset of them, verified by test.

Clinical safety rule: a named procedure is reachable only from explicit procedure wording. Generic
gloves, instrument, scalp or contact wording never resolves to `HAIR_TRANSPLANT`,
`HAIR_TRANSPLANT_FUE`, `FUE_IMPLANTATION` or `INJECTABLES`.

## Legacy deprecation table

| Component | Classification | Notes |
|---|---|---|
| `app/api/search/v3/route.ts` | MIGRATED | Alias only; re-exports the canonical `POST`. Delete once no deployed client uses the versioned URL. |
| `app/lib/media/search-v3.ts` (`interpretV3Query`, `V3_RANKING`) | KEEP_FOR_TESTING | Removed from every production path. Still used by `tests/job7-search-v3.test.ts` and the developer preview. |
| `app/lib/media/local-preview-search.ts` | STILL_REQUIRED_AS_LOW_LEVEL_COMPONENT | Developer offline preview only, behind `/api/dev/library-preview/search`, dev + loopback gated. |
| `rpc hybrid_search_assets` (v1) | DEPRECATED | No production caller. Referenced by `tests/library-search.test.ts` migration-security assertions and `scripts/phase17-rpc-test.ts`. |
| `rpc hybrid_search_assets_v2` | DEPRECATED | No production caller. Referenced by `scripts/runtime-acceptance.ts`. |
| `rpc hybrid_search_assets_v3` | STILL_REQUIRED_AS_LOW_LEVEL_COMPONENT | Serves only the developer preview tool. |
| `rpc match_phase17_semantic_embeddings` | DEPRECATED | Historical Phase 17 vector matcher; no production caller. Retained for regression harnesses. |
| `rpc match_kdi_semantic_search_embeddings` | STILL_REQUIRED_AS_LOW_LEVEL_COMPONENT | Dimension- and identity-guarded vector channel used only by the canonical retriever. |
| `rpc phase18_authorize_candidates_for` | STILL_REQUIRED_AS_LOW_LEVEL_COMPONENT | The canonical authorization gate. |
| `generateQueryEmbedding` / `generateVisualQueryEmbedding` (old `search.ts`) | DEPRECATED — removed | Unreachable: required a 1024-dimension provider no configured provider supplies, and nothing called them. The canonical encoder owns query vectors. |
| `config/…/kdi_query_parser_v1_4.json#semantic_aliases` | MIGRATED | Superseded by the vocabulary registry; retained so the superset test can prove no mapping was lost. |
| `scripts/phase09-live-benchmark.ts`, `phase10-*`, `phase11-*`, `diagnose-v3-zero-results.ts` | KEEP_FOR_TESTING | Regression and benchmark harnesses. Not production. |

## Observability

`executeCanonicalSearch` returns a `diagnostics` object describing the run it just performed:
parsed intent, requested and effective count, hard constraints, exclusions, resolved canonical
concepts, per-channel candidate counts, authorization removals, and final ranked ids. It contains no
clinical text, credentials or raw vectors. `app/lib/media/search.ts` logs it only when
`NODE_ENV=development` and `KDI_SEARCH_DEBUG=true`.
