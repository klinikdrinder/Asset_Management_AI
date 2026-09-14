# KDI SEMANTIC DATABASE ROLLOUT
## PHASE 7 POST-CANARY FINAL

STATUS: **PHASE 7: PASS**

### CANARY

`IMG_2951.MP4`  
Asset ID: `a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd`

One scene and one keyframe were processed locally. The canary remains COMPLETE and SEARCH_READY.

### CANONICAL LAYERS

- Active layers: **18/18**; IDs and numbers are canonical and unique.
- Layer 17: `SEMANTIC_NARRATIVE` / Semantic Narrative
- Layer 18: `SEARCH_EMBEDDINGS` / Search & Embeddings
- Legacy active layers: **0**

The live database catalog and locked migration define these labels. The earlier “Safety / Consent” and “Evidence & Notes” wording was report/spec interpretation drift, not a database defect. `LAYER_DATABASE_STATE=CORRECT`; report-label drift is resolved without rewriting semantic truth.

### STATE SEMANTICS

Fifteen layers are UNKNOWN and were audited as evaluated-but-indeterminate. Identity, temporal structure, and search-embedding layers are OBSERVED. No UNKNOWN was converted to a positive fact, no fabricated facts were added, and no NOT_ANALYZED correction was required because the deployed enum has no separate NOT_ANALYZED value. COMPLETE denotes completed processing, not semantic certainty.

### GROUNDING CORRECTION

The initial run produced four low-confidence `SURGERY` assertions/evidence links. The audit classified that token as unsupported model/text leakage (C), deactivated the four assertions, preserved all four evidence records and lineage, marked the prior narrative stale, and rebuilt the profile, search document, and canary E5 input from grounded content only.

- Historical assertions: 4; current active assertions: 0
- Evidence preserved and valid: **4/4**
- Unsupported description claims: **0**
- Unsupported narrative claims: **0**

### SEARCH

`IMG_2951` returns the canary with grounded filename/identity support. `surgery`, `procedure`, `treatment`, and `unsupported_nonexistent_concept` return no result. The former `surgery` result came from unsupported model assertion/description/narrative text and E5 payload; it has been removed from current searchable truth. No metadata-only or embedding-only clinical claim is presented as fact.

### ANALYZER

- Provider: `LOCAL_TRANSFORMERS`
- Model: `HuggingFaceTB/SmolVLM2-500M-Video-Instruct`
- Structured observation quality: PASS
- Evidence precision: PASS after correction
- Semantic mapping coverage: PASS for available observations
- Suitable to continue rollout: **YES**

### IDEMPOTENCY

Second execution: `ALREADY_COMPLETE_SKIP`; duplicates: **0**.

### DATABASE (BEFORE -> AFTER)

| Metric | Before | After |
|---|---:|---:|
| Assets | 881 | 881 |
| Complete | 10 | 11 |
| Pending | 870 | 869 |
| Unsupported | 1 | 1 |
| SEARCH_READY | 10 | 11 |

Original 10 pilot data is unchanged. The canary has one valid current 18-layer set; superseded assertions/evidence remain auditable.

### EXTERNAL CALLS

Gemini: **0**; OpenAI indexing: **0**; Ollama/Qwen: **0**; external media inference/transmission: **0**.

### DEFERRED

`DEFERRED_SOURCE_REPOSITORY_PERMISSION` remains **DEFERRED**, does not block this audit, and remains mandatory before Phase 19.

### NEXT

**PHASE 8 — CANARY SEMANTIC VALIDATION**

Phase 8 has not started. Assets #12–#30 were not processed.
