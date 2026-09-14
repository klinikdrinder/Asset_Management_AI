# Job 7 pgvector retrieval

`hybrid_search_assets_v3` searches `asset_visual_embeddings`, `scene_embeddings`, and `keyframe_embeddings` using the compatible OpenCLIP text vector. Scene/keyframe evidence rolls up to a single parent-asset row.

Verified HNSW indexes:

- `asset_visual_embeddings_hnsw_512_idx`
- `scene_embeddings_hnsw_visual_512_idx`
- `keyframe_embeddings_hnsw_visual_512_idx`

Vector storage remains PostgreSQL/pgvector. No production FAISS or separate vector store was added.

