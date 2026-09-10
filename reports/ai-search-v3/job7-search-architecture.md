# Job 7 search architecture

V3 combines permission-prefiltered PostgreSQL structured matches, controlled ontology evidence, PostgreSQL lexical retrieval, and pgvector cosine similarity over existing 512-dimensional OpenCLIP asset/scene/keyframe vectors. The backend creates the query vector with the existing `ViT-B-32 / laion2b_s34b_b79k` text encoder. Dedicated text embeddings remain deferred.

The ranking interface keeps visual, lexical, structured, filename, scene, and keyframe signals separate so a future text-embedding signal can be added without replacing V3. No Ollama or external vector database was introduced.

