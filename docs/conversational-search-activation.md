# KDI conversational search activation boundary

## Ready without an AI API key

- Typed, URL/session-scoped conversational media-search state.
- Provider-neutral query-interpreter contract and deterministic refinement interpreter.
- Media type, doctor, treatment, subject, content type, exclusion, sort, reset, and semantic refinements.
- Existing hybrid RPC remains the single ranking engine.
- A missing query embedding uses the RPC's PostgreSQL full-text, metadata, and filename signals with `query_embedding = null`.
- Query-vector cache identity is normalized query + provider + model + version + dimensions; results are never cached.
- Development-only `/dev/library` refinement UI and interpreted-state diagnostics remain gated by `NODE_ENV=development` and `KDI_LIBRARY_DEV_BYPASS=true`.
- Existing asset fingerprinting, canonical unique assets, claim leases, retry state, provider/model/schema versions, costs, and one-vector-per-asset design are retained.

## Requires a live AI provider

- Multimodal descriptions for approved pilot assets.
- Asset and query embeddings in the configured compatible embedding space.
- Search-quality evaluation against real indexed assets.

Required server-only configuration is documented in the root `.env.example`. Never use `NEXT_PUBLIC_` for provider secrets.

## Active local production identity

- Vision: `qwen3-vl:2b` through Ollama on `http://127.0.0.1:11434`.
- Embeddings: `qwen3-embedding:0.6b`, exactly 1024 dimensions.
- Model storage: `E:\KDI_Local_AI\models` (outside the repository).
- Concurrency: one AI request at a time. Vision and embedding models run
  sequentially with `keep_alive: 0` so they are not resident together.
- OpenAI remains an explicit optional adapter and is never an automatic fallback.

## Controlled rollout

1. 20 explicitly approved assets and metadata-quality review.
2. Approximately 100 representative assets and query evaluation.
3. 500–1,000 assets for throughput, cost, retry, and latency measurement.
4. One complete Drive, then five Drives, before the remaining estate.

Do not add HNSW until real vector count and measured query latency justify a cosine index. Exact deduplication and canonical-asset linking must occur before paid AI analysis.
