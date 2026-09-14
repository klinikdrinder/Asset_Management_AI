# Fix 01 — Production search trace

## Canonical request path

1. `dashboard/app/library-search-box.tsx` and the media library UI submit the natural-language query.
2. `dashboard/app/api/search/route.ts:19` is the sole canonical POST entry point. `/api/search/v3` only re-exports it (`app/api/search/v3/route.ts:8`).
3. `route.ts:30` calls `interpretQuery`; `db/query-interpreter.ts` combines parser configs v1.4/v2/v3 and emits parser version `kdi_query_parser_v3_1`.
4. `db/canonical-production-retriever.ts:29-39` performs interpretation → requirement classification → expansion → query encoding → candidate retrieval → authorization → evidence loading → deterministic reranking.
5. `db/candidate-retriever.ts:44-63` unions filename, canonical structured, expanded structured, canonical document full-text, OCR literal, transcript literal, metadata, and compatible vector channels.
6. Vector candidates use live RPC `match_kdi_semantic_search_embeddings` (`candidate-retriever.ts:63`). Old `hybrid_search_assets*` RPCs are not called.
7. Every union candidate is restricted to `kdi_search_ready_assets_v1.search_ready=true` (`candidate-retriever.ts:79-81`).
8. `db/candidate-authorizer.ts:5` invokes `phase18_authorize_candidates_for` and removes candidates lacking discover + metadata + preview rights.
9. `db/deterministic-reranker.ts:46` loads active, non-superseded `semantic_assertions`, `asset_search_concepts_v2`, and asset metadata. Scoring is in lines 30-45.
10. `canonical-production-retriever.ts:43` applies requested-count control; `route.ts:39-46` fetches result assets and formats them.

## Data-source usage

| Data source | Production search use | Evidence |
|---|---|---|
| `search_document_builds` | YES | Full-text channel and READY browse, retriever lines 58-59 |
| `semantic_embeddings` TEXT_ASSET | YES | Compatible embedding RPC, retriever line 63; declared model in canonical retriever line 49 |
| `semantic_embeddings` visual/scene/keyframe | YES | Compatible embedding RPC and query vectors |
| `semantic_assertions` | YES | Structured candidate query lines 45-55; reranking evidence line 46 |
| `semantic_assertion_evidence` | NO direct | Reranker loads assertion IDs/confidence but not evidence table |
| `asset_search_concepts_v2` | YES | Structured candidate, expansion, exclusions, and reranking |
| `scene_people` | NO direct | No production reference in canonical retriever path |
| `person_appearances` | NO direct | No production reference in canonical retriever path |
| `asset_scenes` | PARTIAL | Scene IDs/times arrive via documents/embeddings/assertions; no independent scene fact query |
| `asset_keyframes` | PARTIAL | Keyframe-level embedding results; no direct metadata query during retrieval |
| OCR | PARTIAL | Direct only for parser-created OCR literal requirement; otherwise doc/vector-derived |
| transcripts | PARTIAL | Direct only for parser-created transcript literal requirement; otherwise doc/vector-derived |
| `asset_access_control` | YES indirectly | Authorization RPC called before ranking |
| `asset_search_documents` | NO | No canonical path reference; legacy 30-row corpus |
| `asset_semantic_index` | NO | No canonical path reference; legacy 20-row corpus |
| `asset_visual_embeddings` | NO | Canonical path uses `semantic_embeddings` matcher |
| `hybrid_search_assets_v3` | NO | Live legacy RPC exists, but canonical TypeScript does not call it |

## Ranking formula

The deterministic raw score is: structured evidence + preferences − negative-preference penalties + specificity + same-scene/same-event coherence + literal + text-vector + visual-vector − contradiction penalty. Weights are centralized in `config/semantic-search/kdi_deterministic_reranker_v1.json`: strong requirement 14, preference 5, same-scene 7, same-event 5, specificity 4, literal 7, text cap 5, visual cap 2, hard-unknown −5, conflict −10. Hard false constraints and observed hard exclusions make a candidate ineligible. Ties use normalized score, requirements satisfied, exact matches, confidence, coherence, then UUID.

There is scene coherence but no same-person coherence. Consequently structured attributes can be combined across different people in one scene; asset-level evidence can also combine across scenes unless the coherence bonus happens to favor a single scene.

## Safety note

The existing API route was not invoked because normal searches insert/update `search_sessions`, `search_queries`, and `search_results`. The audit used the parser locally and inspected database/search state with GET/SELECT only.
