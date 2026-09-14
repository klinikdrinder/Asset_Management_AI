# KDI Semantic Search Phase 12 — Multi-Representation Embeddings

## Result

Phase 12 generated 106 active, versioned retrieval representations for the exact ten frozen pilots. It did not alter canonical semantic truth, human review, gold data, frontend code, or Phase 13 query/retrieval behavior.

## Locked versions

- Bundle: `kdi_embedding_bundle_v1`
- Visual: `kdi_visual_embedding_v1`
- Text: `kdi_text_embedding_v1`
- Semantic contract: `semantic_index_v1`
- Ontology: `KDI_SEMANTIC_V2`

Visual vectors use local OpenCLIP 3.3.0, `ViT-B-32`, `laion2b_s34b_b79k`, 512 dimensions. Images are EXIF-normalized. Canonical video keyframes are decoded at their recorded timestamps. Scene vectors are the L2-normalized mean of L2-normalized member keyframe vectors; video asset vectors use the same deterministic aggregation over canonical scene vectors.

Text vectors use local sentence-transformers 5.1.0 with `intfloat/multilingual-e5-small`, 384 dimensions. This multilingual E5 model supports English/Malay retrieval and avoids external transmission. Source text is Unicode NFKC and whitespace normalized, then encoded with the model's `passage:` contract. All 41 text inputs fit within the 512-token limit; none were truncated.

The configured Ollama `qwen3-embedding:4b` service was unavailable and was not used. No external provider received media or clinical text, and no mixed-model fallback occurred.

## Representation coverage

- `VISUAL_ASSET`: 10
- `VISUAL_SCENE`: 11
- `VISUAL_KEYFRAME`: 44
- `TEXT_ASSET`: 10
- `TEXT_SCENE`: 11
- `TEXT_EVENT`: 16
- `TEXT_TRANSCRIPT`: 3
- `TEXT_OCR`: 1 (`M-CURE`, OCR-only)

The six technical-only IMG_1238 events, eleven excluded/review transcript chunks, three review OCR observations, and fifteen rejected OCR observations have no active retrieval embeddings. The excluded IMG_3429 transcript has no active embedding.

## Lineage and lifecycle

Every row records provider, model, model version, dimensions, source fingerprint, vector fingerprint, analysis run, semantic/ontology versions, embedding/bundle versions, generation time, active/stale state, review status, and source-unit linkage. Twenty analysis runs retain separate visual/text processor lineage across ten assets.

Idempotency uses deterministic row IDs plus an active-unit/version uniqueness index. Repeating generation retained exactly 106 active rows with zero duplicates. Document fingerprint mismatches are detected as stale. Model/version changes produce historical rows rather than mutating vector identity.

## Vector spaces and future Phase 17 contract

Phase 12 uses exact cosine search for the pilot. There is no global ANN index mixing incompatible spaces. At production scale, ANN indexes must be partial and restricted to one provider/model/model-version/dimension/representation family.

Phase 17 must generate:

- Visual-semantic query vector: matching OpenCLIP text encoder, 512 dimensions, compared only with the OpenCLIP visual families.
- Semantic-text query vector: multilingual E5 with `query:` prefix, 384 dimensions, compared only with the E5 text families.
- Structured filters/signals: the existing 270 relational canonical concepts, retained independently from vectors.

Phase 17 retrieval, weighting, ranking, and query interpretation were not implemented.

## Security

`semantic_embeddings` remains RLS protected through asset authorization. A live authorized synthetic session saw all 106 rows across eight families; an unauthorized session saw zero. Normal authenticated clients cannot insert, update, or delete canonical vectors. Backend/service-role access is explicitly limited to required source reads and embedding/run writes.

## Index and metric strategy

Both locked models emit normalized vectors and use cosine distance. Exact filtered search is sufficient at 106 rows. Scaling should add separate partial HNSW indexes per compatible visual/text vector space only after representative-volume measurement.

## Scope boundary

Human gold remains deferred. No frontend work occurred. Phase 13 was not started.
