# KDI SEMANTIC SEARCH V3
## PHASE 28 FINAL 10-PILOT ACCEPTANCE — FINAL

STATUS: PASS  
ACCEPTANCE VERSION: `kdi_10_pilot_acceptance_v1`

## SPEC

SPEC VERSION: `kdi_semantic_18_layer_v1`  
SPEC FINGERPRINT: PASS  
SPEC LOCK: PASS  
LAYER DEFINITIONS: 18 / 18  
POPULATED LAYER RULES: 18 / 18  
GLOBAL/FUTURE-WORKER GUARDS: PASS

## PILOT FOUNDATION

PILOT ASSETS: 10 / 10  
SEMANTIC LAYERS: 180 / 180  
COMPLETE: 180  
PARTIAL: 0  
MISSING: 0  
DUPLICATE ACTIVE LAYERS: 0  
STATE SEMANTICS: PASS (`OBSERVED` 153, `FALSE` 2, `UNKNOWN` 21, `NOT_APPLICABLE` 4)  
EVIDENCE INTEGRITY: PASS  
ORPHAN ASSERTION EVIDENCE: 0  
CROSS-ASSET EVIDENCE: 0  
MISSING SCENE REFERENCES: 0  
MISSING EVENT REFERENCES: 0  
SHORT DESCRIPTIONS: 10 / 10  
DETAILED DESCRIPTIONS: 10 / 10  
UNINTENDED EXACT DESCRIPTION DUPLICATES: 0  
NARRATIVES: 10 / 10 assets; 37 active canonical narratives  
SEARCH REPRESENTATIONS: 10 / 10 asset documents; 37 active documents; 788 concept links; 788 evidence links; 0 stale  
EMBEDDING LINEAGE: PASS; 106 active; 0 stale; 0 invalid dimensions; 0 missing source documents

## SEARCH PIPELINE

PARSER: PASS  
REQUIREMENT CLASSIFICATION: PASS  
QUERY EXPANSION: PASS  
RETRIEVAL: PASS  
AUTHORIZATION: PASS  
FAIL-CLOSED AUTHORIZATION: PASS  
DETERMINISTIC RERANK: PASS  
PHASE 20 EXTERNAL RERANK: DISABLED  
RESULT COUNT: PASS  
DATABASE-GROUNDED RESPONSE: PASS  
CONVERSATION MEMORY: PASS  
NUMERIC DISAMBIGUATION: PASS

Representative live cases passed for neck injection, typo normalization, lower-face injection, cheek cleansing, frontal hairline thinning, and underwater-coral zero result. Numeric acceptance retained age 30 and graft quantity 3000 independently from explicit result counts.

## GROUNDING / SAFETY

GROUNDING MODE: `DATABASE_REQUIRED`  
GENERATED FACT FALLBACKS: 0  
QUERY-TIME VISION: 0  
QUERY-TIME OCR: 0  
QUERY-TIME TRANSCRIPTION: 0  
MEDIA REANALYSIS: 0  
OPENAI API CALLS: 0  
CROSS-SESSION LEAKAGE: 0  
CROSS-USER LEAKAGE: 0  
PRODUCTION ACL WEAKENED: NO

The acceptance runner used the Phase 27 manifest-scoped engineering principal for ordinary benchmark categories. The authorization-control category used the isolated Phase 18 fail-closed principal. Ordinary production ACL values remained `UNKNOWN` and continued to fail closed.

## CERTIFIED GOLD

GOLD VERSION: `kdi_gold_answers_v1`  
GOLD STATUS: CERTIFIED  
CERTIFICATION: EVIDENCE_VERIFIED  
GOLD FINGERPRINT: PASS (`979389e6b045a4913f9e82b96687e46a65e789753e2598be601cb3a6d5663763`)  
FINGERPRINT RECALCULATION: MATCH  
GOLD CASES: 40 / 40  
GOLD_DETERMINATE: 40 / 40  
GOLD IMMUTABILITY: PASS  
UPDATE PROTECTION: PASS  
DELETE PROTECTION: PASS  
GOLD MODIFIED: NO

## BENCHMARK

BENCHMARK VERSION: `kdi_semantic_benchmark_v1`  
BENCHMARK CASES: 40 (35 single-turn, 5 multi-turn)  
BENCHMARK MODIFIED: NO  
PHASE 27 ARTIFACTS: PRESENT AND COMPLETE

PHASE 28 RUN A ID: `53df6bea-7ad7-4978-b30c-170b485df029`  
PHASE 28 RUN B ID: `46171469-aa04-4f79-8220-5f714b7230c9`  
RUN A: 40 / 40  
RUN B: 40 / 40  
REPRODUCIBILITY: 100%  
CASE PASS: 40 / 40  
RETRIEVAL CASES: 27 / 27  
CONTROL CASES: 13 / 13  
ZERO RESULT: 4 / 4  
TOP-1 EXACT: 62.963%  
TOP-1 STRICT RELEVANT: 81.481%  
HIT@1: 0.814815  
HIT@3: 0.851852  
HIT@5: 0.851852  
MRR: 0.833333  
nDCG@3: 0.955034  
nDCG@5: 0.963459  
NO_RELEVANT_RESULT: 0  
WRONG_TOP1: 1 (C35 informational; certified case-pass policy satisfied)  
EXCLUDED_RESULT_RETURNED: 0  
COUNT_MISMATCH: 0  
PARSER_MISMATCH: 0  
FILTER_MISMATCH: 0  
STATE_MISMATCH: 0  
CONVERSATION_MISMATCH: 0  
AUTHORIZATION_VIOLATION: 0

## PERFORMANCE

MEAN LATENCY: 1694.720 ms  
MEDIAN LATENCY: 1351.296 ms  
P95 LATENCY: 3849.146 ms  
MAX LATENCY: 4159.010 ms  
SEVERE PERFORMANCE REGRESSION: NO

Relative to Phase 24, mean increased 15.7%, median 10.6%, p95 15.4%, and maximum 14.2%. This is ordinary live-run variation, not a severe or unexplained regression.

## ANTI-HARDCODING

HARDCODED BENCHMARK ANSWERS: 0  
HARDCODED PILOT ANSWERS: 0  
TARGETED ACCEPTANCE TESTS: 94 / 94

The frozen pilot filenames remain manifest/configuration data. No query, case ID, asset UUID, filename, or expected ranking is used as a search answer.

## DATABASE PRESERVATION

Before/after counts and deterministic row hashes matched for all protected pilot structures:

| Structure | Count | Hash match |
|---|---:|---|
| assets | 10 | PASS |
| asset_semantic_layers | 180 | PASS |
| semantic_assertions | 313 | PASS |
| semantic_assertion_evidence | 270 | PASS |
| asset_ai_profiles | 10 | PASS |
| asset_scenes | 21 | PASS |
| asset_events | 22 | PASS |
| semantic_narratives | 37 | PASS |
| active search documents | 37 | PASS |
| search-document concepts | 788 | PASS |
| search-document evidence | 788 | PASS |
| semantic embeddings | 106 | PASS |
| production ACL | 10 | PASS |

SEMANTIC FACTS MODIFIED: NO  
SPEC MODIFIED: NO  
GOLD MODIFIED: NO  
BENCHMARK MODIFIED: NO  
PRODUCTION ACL MODIFIED: NO

## ANALYSIS PROVENANCE AND TECHNICAL DEBT

BLOCKING: NONE

NON-BLOCKING FOR 10-PILOT ENGINEERING ACCEPTANCE:

- Phase 20 real-model validation and production OpenAI API activation remain intentionally deferred.
- 48 legacy analysis-run records lack model/provider metadata.
- 68 legacy records have zero-duration timestamps.
- Production pilot ACL governance fields remain `UNKNOWN`; production access therefore remains fail closed.
- Phase 29 must formalize scale idempotency, retry/job orchestration, and worker throughput before any additional assets are processed.
- Phase 30 remains required before scaling beyond the frozen pilots.

Current completed runs have no impossible start/completion ordering. Legacy omissions are distinguished from current-pipeline defects.

## SCALE-READINESS CHECK

Locked spec: IDENTIFIABLE  
Versioned asset-processing contract: IDENTIFIABLE  
Semantic lineage: VERSIONED  
Search-document lineage: VERSIONED  
Embedding lineage: VERSIONED  
Benchmark/gold infrastructure: PRESENT  
Deterministic audit records: PRESENT  
Idempotency/retry/job scale hardening: PHASE 29 WORK

PHASE 20 REAL-MODEL VALIDATION: DEFERRED  
OPENAI API PRODUCTION ACTIVATION: DEFERRED  
ARE DEFERRED API ITEMS BLOCKING PHASE 28: NO

## PHASE 28

FINAL 10-PILOT ENGINEERING ACCEPTANCE: PASS  
PHASE 28: PASS  
SAFE TO START PHASE 29: YES  
SAFE TO ADD MORE ASSETS NOW: NO

IMPORTANT: Even though Phase 28 passes, no additional assets may be added until Phases 29 and 30 are complete.

REMAINING BLOCKERS: NONE
