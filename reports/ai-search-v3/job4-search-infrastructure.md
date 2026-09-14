# Job 4 search infrastructure

Job 4 adds empty, backend-controlled projections and history tables. Normalized asset/scene intelligence remains authoritative; search documents and embeddings are derived and rebuildable. No asset, scene, transcript, OCR, document, or vector processing occurred.

## Tables

| Group | Tables | Key design |
|---|---|---|
| Embeddings | `scene_embeddings`, `keyframe_embeddings`, `transcript_embeddings` | Untyped pgvector storage with per-row `embedding_dimensions` and `vector_dims()` checks; active model/version uniqueness; composite parent integrity |
| Documents | `asset_search_documents`, `scene_search_documents` | One projection per asset/scene; generated English `tsvector`; GIN indexes; build status is only `PENDING/BUILDING/READY/FAILED/STALE` |
| Conversation | `search_sessions`, `search_queries` | Existing `auth.users` identity; immutable parent-turn chain; unique sequence; default count 5; explicit counts up to a documented operational ceiling of 10,000 |
| Ranking | `search_results` | One final asset per query and one row per rank; best scene/keyframe/transcript references; normalized overall/component scores; timestamp guard |
| Feedback | `search_feedback` | Controlled feedback vocabulary and query/result/asset/scene consistency; never changes clinical truth automatically |

All new tables have RLS enabled and no PUBLIC/anon/authenticated privileges. Search and vector access is server/service controlled. The future service must enforce permission eligibility before candidate ranking and return: `user → permitted assets → retrieval → ranking → top N`. Ranking restricted assets first and hiding them afterward is prohibited.

No V1/V2 function was changed. No ANN index exists. `search_query_embeddings` is deferred until query-vector reuse is demonstrated and its lifecycle is designed.
