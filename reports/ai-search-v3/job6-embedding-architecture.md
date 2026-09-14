# Job 6 embedding architecture

PostgreSQL/Supabase with pgvector 0.8.2 remains authoritative. No new vector database was introduced and Ollama was not installed.

- Visual generator: existing `open_clip`, `ViT-B-32`, `laion2b_s34b_b79k`, 512 dimensions.
- Visual storage: `asset_visual_embeddings`, `scene_embeddings`, `keyframe_embeddings`.
- Existing 875 asset vectors were preserved; eight pilot scene and eight pilot keyframe rows reuse their authorized asset-level vector as a scene/keyframe visual representation.
- Text generator: none currently operational and approved. Configured Ollama is unavailable/prohibited; configured OpenAI fallback returned quota exhaustion before any pilot media was sent.
- Text vectors: **DEFERRED — NO APPROVED WORKING GENERATOR**. No padding, truncation, or dimension conversion occurred.
- Text storage remains `asset_embeddings` / `transcript_embeddings` when a compatible approved generator becomes available.

Existing vector indexes are primary/unique/model/filtering indexes; the Job 4 pilot schema contains no ANN HNSW/IVFFlat index. Job 6 did not alter that architecture.
