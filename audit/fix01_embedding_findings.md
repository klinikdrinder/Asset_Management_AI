# Fix 01 — Embedding findings

|table|embedding_type|provider|model|model_version|dimension|active_rows|unique_assets|unique_scenes|duplicate_active_embeddings|stale_rows|
|---|---|---|---|---|---|---|---|---|---|---|
|semantic_embeddings|TEXT_ASSET|LOCAL|intfloat/multilingual-e5-small|None|384|0|0|0|0|1|
|semantic_embeddings|TEXT_ASSET|sentence_transformers|intfloat/multilingual-e5-small|hf-main-pinned-runtime-v1|384|877|877|0|0|10|
|semantic_embeddings|TEXT_EVENT|sentence_transformers|intfloat/multilingual-e5-small|hf-main-pinned-runtime-v1|384|16|6|7|9|0|
|semantic_embeddings|TEXT_OCR|sentence_transformers|intfloat/multilingual-e5-small|hf-main-pinned-runtime-v1|384|1|1|1|0|0|
|semantic_embeddings|TEXT_SCENE|sentence_transformers|intfloat/multilingual-e5-small|hf-main-pinned-runtime-v1|384|791|585|791|0|0|
|semantic_embeddings|TEXT_TRANSCRIPT|sentence_transformers|intfloat/multilingual-e5-small|hf-main-pinned-runtime-v1|384|3|1|1|0|0|
|semantic_embeddings|VISUAL_ASSET|open_clip|ViT-B-32|laion2b_s34b_b79k|512|857|857|0|0|0|
|semantic_embeddings|VISUAL_KEYFRAME|open_clip|ViT-B-32|laion2b_s34b_b79k|512|1333|585|791|0|0|
|semantic_embeddings|VISUAL_SCENE|open_clip|ViT-B-32|laion2b_s34b_b79k|512|791|585|791|0|0|
|asset_visual_embeddings|LEGACY_VISUAL_ASSET|open_clip|ViT-B-32|laion2b_s34b_b79k|512|875|875|0|0|UNKNOWN|
