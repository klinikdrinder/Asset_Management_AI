# KDI SEMANTIC SEARCH — 30-ASSET ROLLOUT

## PHASE 2 — 11TH-ASSET CANARY ACTIVATION FINAL

**STATUS: BLOCKED_OPENAI_QUOTA**

### Architecture

- Search backend: PostgreSQL + pgvector (PASS)
- Ollama required: NO
- Qwen required: NO
- Real media indexing capability: PARTIAL_REAL_INDEXING_PIPELINE

The implemented code has preprocessing, embedding-only visual extraction, and a schema/package builder consuming reviewed evidence. It does not contain an approved real-media semantic analyzer/provider capable of deriving and validating all 18 layers for a new asset. PostgreSQL/pgvector provide storage and retrieval; they do not visually analyze media. Phase 30 synthetic output is not accepted as canary truth.

### Implemented path

- Media preprocessing: `src/kdi_media/semantic_indexing.py` (PillowImagePreprocessor/FfmpegFrameExtractor) and `video_frames.py`.
- Visual extraction: `dashboard/visual_indexing/openclip_encoder.py` (embedding-only).
- 18-layer code: `src/kdi_media/semantic_analysis.py` package builder from reviewed evidence, not raw-media extraction.
- Transcript/OCR generation: none in the current V1 canary path.
- Description/narrative: provider abstraction and stored-evidence builders; no approved real canary provider.
- Search document: `dashboard/db/search-document-builder.ts`.
- Structured/vector storage: PostgreSQL/Supabase and pgvector.

### Canary preconditions

- Asset: IMG_2951.MP4 (`a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd`), canonical row reused: YES
- Asset/hash/source/supported format: PASS
- Existing V1 layers/docs/embeddings: 0/0/0

### Processing result

No canary job was started. Real extraction, validation, semantic staging, descriptions, narrative, search document, embeddings, pgvector write, completeness, SEARCH_READY, search probes, and idempotency were **NOT_RUN**. Layers evaluated: 0/18; missing: 18. Semantic writes: 0.

Missing components:

1. Approved real 18-layer raw-media semantic analyzer/provider.
2. End-to-end scene/event/transcript/OCR semantic extraction wiring.
3. Approved V1 provider configuration capable of producing validated 18-layer output.

### Safety and preservation

- Ollama/Qwen calls: 0; OpenAI API calls: 0; other unapproved AI calls: 0.
- Media analysis/OCR/transcription: 0; query-time media reanalysis: 0.
- Production ACL weakened/modified: NO; consent auto-approved: 0.
- Original 10, gold V1, benchmark V1, and spec V1 unchanged.
- Assets #12–#30 processed: 0.

**PHASE 2: BLOCKED_OPENAI_CREDENTIALS**  
Phase 3 and Wave 2 are not safe to start.

## Phase 2B activation check

Status: **BLOCKED_OPENAI_CREDENTIALS**

- `OPENAI_API_KEY`: MISSING (presence checked without exposing a value)
- `SEMANTIC_ANALYSIS_MODEL`: MISSING
- `EXTERNAL_AI_ENABLED`: remains disabled
- Provider/quota preflight requests: 0
- Canary semantic requests: 0
- Canary processed: NO
- Assets #12–#30 processed: 0

No OpenAI request, media preprocessing, semantic write, or production
database change was attempted. Configure the credential securely in the
runtime secret store and set a supported model centrally, then rerun the
bounded activation preflight. Do not place secrets in this report or in
Supabase.

## Phase 2A provider implementation update

The missing provider interface is now implemented as
`kdi_openai_semantic_analysis_adapter_v1` in
`dashboard/db/openai-semantic-analysis-provider.ts`, conforming to the
existing `SemanticAnalysisProvider` contract. It uses the Responses API
multimodal input shape and strict JSON Schema output, with bounded evidence
references, locked-state validation, spec/pipeline checks, and usage lineage.

Offline targeted tests: **3/3 PASS**. They verify the disabled gate blocks
before network access, valid 18-layer output is accepted, and invalid
evidence is rejected.

Activation remains blocked as **BLOCKED_OPENAI_CREDENTIALS**: no
`OPENAI_API_KEY` or `SEMANTIC_ANALYSIS_MODEL` is configured, and
`EXTERNAL_AI_ENABLED` remains false. No provider preflight, API request, or
canary processing was performed. This is an activation prerequisite, not a
search-backend change. PostgreSQL + pgvector remain unchanged.

## Phase 2B retry

The retry again found `OPENAI_API_KEY` and `SEMANTIC_ANALYSIS_MODEL`
absent from the runtime environment. The required single provider/quota
preflight was not attempted, and no canary or other rollout asset was
processed. Status remains **BLOCKED_OPENAI_CREDENTIALS**.

## One-shot Phase 2B activation

The credential was found in the approved project environment (presence only;
the secret was not exposed). `SEMANTIC_ANALYSIS_MODEL` was centrally set to
`gpt-5.6-sol`. Exactly one text-only Responses API structured-output
preflight was attempted; it returned HTTP 429. Per policy, no retry was
made. Final status is **BLOCKED_OPENAI_QUOTA**.

- Preflight requests: 1
- Canary semantic requests: 0
- Canary processed: NO
- Semantic writes: 0
- External AI after run: disabled
- Assets #12–#30 processed: 0

The canary remains unindexed. Configure available OpenAI quota/credit and
rerun the bounded preflight before enabling canary-only processing.
