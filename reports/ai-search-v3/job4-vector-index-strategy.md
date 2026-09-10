# Job 4 vector index strategy

## Current decision

No HNSW or IVFFlat index is created. The new embedding tables contain zero rows, the current asset visual corpus is only 875 rows, and Job 4 performs no retrieval implementation. Exact scans filtered by embedding type, provider, model, version, active state, and dimensions are the correct measurable baseline.

The tables use unconstrained `vector` columns so 512-dimensional OpenCLIP and 1024-dimensional Qwen vectors can coexist. Every row stores and validates `embedding_dimensions = vector_dims(embedding)`. Retrieval must filter to one compatible model/version/dimension before applying a distance operator; cross-model comparisons are invalid.

## Future indexes

At sustained tens of thousands of compatible rows, benchmark exact search against partial expression HNSW indexes such as `(embedding::vector(512))` filtered to the exact visual model/version/dimension, and separately `(embedding::vector(1024))` for semantic text. Never create one ANN index over mixed dimensions.

Prefer HNSW when low latency/high recall and changing data justify its memory/build cost. Evaluate IVFFlat for very large, relatively stable corpora when lower memory is more important and representative training data exists. Introduce either only after measuring row counts, filtered recall, p95 latency, ingestion cost, and memory on production-shaped data. At hundreds of thousands of scenes/keyframes, benchmark per table and per model family; use pgvector iterative scans when selective permission/metadata filters otherwise underfill requested results.
