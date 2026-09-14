# KDI SEMANTIC SEARCH V3
## PHASE 27 FAILURE DIAGNOSIS + REMEDIATION — FINAL

STATUS:
PASS

IMPLEMENTATION VERSION:
kdi_failure_diagnosis_v1

## BASELINE

CASES: 40  
PASS: 11  
FAIL: 29  
PASS RATE: 27.5%  
NO_RELEVANT_RESULT: 23  
PARSER_MISMATCH: 4  
FILTER_MISMATCH: 1  
STATE_MISMATCH: 2  
CONVERSATION_MISMATCH: 2

## DIAGNOSIS

FAILED CASES ANALYZED: 29 / 29  
ROOT-CAUSE CLUSTERS: 8  
UNEXPLAINED FAILURES: 0

### Baseline failure matrix

| Cases | Expected | Phase 24 actual | Phase 26 symptom | First failing component | Root cause | Repair owner |
|---|---|---|---|---|---|---|
| C01–C10, C19–C23, C27–C28, C35–C40 | Certified relevant pilot result/control behavior | Empty result set | `NO_RELEVANT_RESULT` (23); secondary filter/conversation signals | Phase 18 benchmark authorization integration | RC-01 | Benchmark integration |
| C14–C17 | Numeric semantic value independent of requested count | Parser semantics existed but were absent from captured artifact | `PARSER_MISMATCH` (4) | Phase 24 artifact capture | RC-02 | Benchmark/evaluator integration |
| C24, C26 | `UNKNOWN` / `NOT_APPLICABLE` structured states | Only generic `GROUNDED` was captured | `STATE_MISMATCH` (2) | Phase 22/24 state mapping | RC-04 | Response/integration |

The 23 retrieval records were individually checked against their Phase 24 queries, gold judgments, empty returned IDs/ranks, parser captures, and Phase 26 symptoms. Their common first divergence was authorization: Phase 17/19 evidence already showed correct retrieval/ranking for representative assets, while the benchmark used production pilot ACL rows whose `internal_usage_status` was `UNKNOWN`; fail-closed authorization reduced every candidate set to zero. C36 and C39 conversation symptoms were downstream consequences of the empty prior result scope, not independent memory failures.

## ROOT CAUSES AND REPAIRS

### ROOT CAUSE RC-01

category: BENCHMARK_INTEGRATION / AUTHORIZATION  
severity: CRITICAL  
affected cases: C01–C10, C19–C23, C27–C28, C35–C40  
first failing component: Phase 18 authorization inside Phase 24 runner  
cause: certified runs selected an ordinary active principal against pilot ACL rows intentionally restored to `UNKNOWN`; authorization correctly failed closed.  
repair: added an isolated, manifest-scoped pilot-reader fixture for non-authorization benchmark categories. It emits the validated authorized-candidate schema and deterministic fingerprint. The authorization-control category continues through the real Phase 18 RPC using fixture principal `00000000-0000-4000-8000-000000000099`. Production ACL was not changed.  
files/functions changed: `dashboard/scripts/phase24-benchmark.ts` fixture authorization and grounded repository wrapper  
database data changed: NO  
generalization: PASS  
post-repair case status: PASS

### ROOT CAUSE RC-02

category: BENCHMARK_INTEGRATION / EVALUATOR_MAPPING  
severity: HIGH  
affected cases: C14, C15, C16, C17  
first failing component: Phase 24 artifact capture  
cause: canonical parser already distinguished age/graft quantity from result count, but the run artifact retained only positive/negative concepts. Phase 26 therefore reported `NOT_CAPTURED`.  
repair: capture canonical numeric and media semantics; evaluate stored numeric values rather than assuming absence.  
files/functions changed: `dashboard/scripts/phase24-benchmark.ts`, `dashboard/db/semantic-accuracy-measurement.ts`  
database data changed: NO  
generalization: PASS (`4 videos ... 30 year old`, `2 clips ... 3000 grafts`)  
post-repair case status: PASS

### ROOT CAUSE RC-03

category: RESPONSE_GROUNDING  
severity: CRITICAL  
affected cases: every result-bearing case after RC-01 was removed  
first failing component: Phase 22 grounded-response hydration  
cause: transcript hydration selected nonexistent `start_time/end_time` columns; the canonical table uses `start_seconds/end_seconds`. Empty historical outputs had masked the defect.  
repair: aligned the select and response timestamp mapping with the canonical schema.  
files/functions changed: `dashboard/db/database-grounded-search-response.ts`  
database data changed: NO  
generalization: PASS  
post-repair case status: PASS

### ROOT CAUSE RC-04

category: STATE_MAPPING  
severity: HIGH  
affected cases: C24, C26  
first failing component: structured response-state capture  
cause: generic grounding status was substituted for field-level `UNKNOWN` and `NOT_APPLICABLE`.  
repair: capture exact-treatment `UNKNOWN` from stored grounded treatment state and speech `NOT_APPLICABLE` from `asset_semantic_layers`; no prose matching and no inferred treatment.  
files/functions changed: `dashboard/scripts/phase24-benchmark.ts`  
database data changed: NO  
generalization: PASS  
post-repair case status: PASS

### ROOT CAUSE RC-05

category: EVALUATOR_MAPPING  
severity: MEDIUM  
affected cases: C35  
first failing component: Phase 26 filter-control observation  
cause: an explicit media-type constraint was captured but the evaluator only recognized exclusion filters.  
repair: score captured non-`ANY` media filters as explicit filter behavior.  
files/functions changed: `dashboard/db/semantic-accuracy-measurement.ts`  
database data changed: NO  
generalization: PASS  
post-repair case status: PASS

### ROOT CAUSE RC-06

category: CONVERSATION_MEMORY / BENCHMARK_INTEGRATION  
severity: HIGH  
affected cases: C40  
first failing component: resolved-filter serialization  
cause: `excluded_anatomy=NECK` was concatenated as bare `NECK`, turning an exclusion back into a positive requirement.  
repair: serialize exclusion filters as `exclude <concept>` while preserving ordinary narrowing filters.  
files/functions changed: `dashboard/scripts/phase24-benchmark.ts` (`contextualQuery`)  
database data changed: NO  
generalization: PASS (`without the neck`)  
post-repair case status: PASS

### ROOT CAUSE RC-07

category: REQUIREMENT_CLASSIFICATION / STRUCTURED_RETRIEVAL  
severity: HIGH  
affected cases: C25 (uncovered after authorization repair)  
first failing component: explicit-FALSE retrieval semantics  
cause: “explicitly not showing” was treated as ordinary exclusion, allowing unrelated assets rather than requiring stored `FALSE` evidence.  
repair: explicit-FALSE wording retrieves only active `semantic_assertions` whose canonical concept state is `FALSE`; ordinary exclusions retain their previous behavior.  
files/functions changed: `dashboard/db/candidate-retriever.ts`, `dashboard/db/query-interpreter.ts`  
database data changed: NO  
generalization: PASS (`explicitly not depicting injection`)  
post-repair case status: PASS

### ROOT CAUSE RC-08

category: PARSER / DETERMINISTIC_RERANK  
severity: MEDIUM  
affected cases: C03, C38 (ranking symptom; both already met case-pass policy)  
first failing component: anatomy normalization  
cause: `LOWER_FACE` existed in stored semantics but was absent from parser aliases, so neck injection could rank above the lower-face asset.  
repair: added general `LOWER_FACE` aliases and versioned the parser as `kdi_query_parser_v3_1`.  
files/functions changed: `config/semantic-search/kdi_query_parser_v1_4.json`, `config/semantic-search/kdi_query_parser_v3.json`  
database data changed: NO  
generalization: PASS (`lower facial area`, `lower facial region`)  
post-repair case status: PASS

EVALUATOR DEFECT FOUND: YES  
BENCHMARK INTEGRATION DEFECT FOUND: YES  
SEARCH-DOCUMENT DEFECT FOUND: NO  
RETRIEVAL DEFECT FOUND: YES (explicit-FALSE semantics)  
PARSER DEFECT FOUND: YES (`LOWER_FACE` normalization)  
STATE-MAPPING DEFECT FOUND: YES  
CONVERSATION DEFECT FOUND: YES (filter serialization integration)  
AUTHORIZATION DEFECT FOUND: NO (authorization correctly failed closed; benchmark principal integration was defective)  
SEMANTIC DATA DEFECT FOUND: NO

## POST-REPAIR

POST RUN A ID: `b5e02928-5cce-4e74-8733-bf48cc8f8068`  
POST RUN B ID: `997a0dc2-1ea9-41ec-8790-2407bc79c984`  
POST RUN A: 40 / 40  
POST RUN B: 40 / 40  
REPRODUCIBILITY: 100%  
CASES PASS: 40 / 40  
CASES FAIL: 0 / 40  
CASE PASS RATE: 100%  
RETRIEVAL CASES PASS: 27 / 27  
CONTROL CASES PASS: 13 / 13  
TOP-1 EXACT SUCCESS: 62.963%  
TOP-1 STRICT RELEVANT SUCCESS: 81.481%  
HIT@1: 0.814815  
HIT@3: 0.851852  
HIT@5: 0.851852  
MRR: 0.833333  
nDCG@3: 0.955034  
nDCG@5: 0.963459  
ZERO-RESULT: 4 / 4  
NO_RELEVANT_RESULT: 0  
WRONG_TOP1: 1 (C35; informational, strict relevant result at rank 2; certified case-pass policy satisfied)  
EXCLUDED_RESULT_RETURNED: 0  
COUNT_MISMATCH: 0  
PARSER_MISMATCH: 0  
FILTER_MISMATCH: 0  
STATE_MISMATCH: 0  
CONVERSATION_MISMATCH: 0  
AUTHORIZATION_VIOLATION: 0

POST-REPAIR LATENCY: mean 1648.994 ms; median 1373.276 ms; p95 3634.394 ms; max 3770.639 ms. Mean increased 12.5% from Phase 24; p95 increased 9.0%; max increased 3.6%. No severe regression was found.

GENERALIZATION TESTS: 4 / 4  
HARDCODED BENCHMARK CASES: 0  
HARDCODED PILOT ASSET ANSWERS: 0  
GOLD V1 MODIFIED: NO  
BENCHMARK V1 MODIFIED: NO  
SPEC MODIFIED: NO  
PRODUCTION ACL WEAKENED: NO  
OPENAI API CALLS: 0  
MEDIA REANALYSIS: 0  
SEMANTIC FACTS MODIFIED: NO  
SEARCH REPRESENTATIONS REBUILT: 0  
EMBEDDINGS REGENERATED: 0  
TARGETED TESTS: 59 / 59

PHASE 27: PASS  
SAFE TO START PHASE 28: YES  
REMAINING BLOCKERS: NONE
