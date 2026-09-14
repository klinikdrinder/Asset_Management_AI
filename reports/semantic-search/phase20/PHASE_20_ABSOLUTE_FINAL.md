# KDI SEMANTIC SEARCH — PHASE 20 ABSOLUTE FINAL

STATUS: PASS  
PHASE 21 ALLOWED: YES

## LIVE BASELINE

Assets: 881  
Asset sources: 881  
ACL rows: 881  
Embeddings: 106  
Search concepts: 270  
Assertions: 333  
Evidence: 270  
Asset docs: 10  
Scene docs: 10  
App users: 2  
Pilot: 10/10

## PHASE 19 LOCK

Reranker version: `kdi_deterministic_reranker_v1`  
Stored fingerprint: `33c8d6d4271b2c7bd818c6ed3366fe1e5a64c96ced42d3c8949a566f4bbd0125`  
Recalculated fingerprint: `33c8d6d4271b2c7bd818c6ed3366fe1e5a64c96ced42d3c8949a566f4bbd0125`  
Match: PASS  
RESULT: PASS

## PHASE 20 CONFIGURATION

Implementation version: `kdi_llm_reranker_v1`  
Prompt version: `kdi_llm_reranker_prompt_v1`  
Schema version: `kdi_llm_reranker_schema_v1`  
Combiner version: `kdi_llm_combiner_v1`  
Model/provider mode: protected synthetic/local adapter benchmark; provider-agnostic production interface  
External AI processing: NOT USED  
Configuration fingerprint: `04a60bad63276b02612eaf2d74e8bea6b5334346461c704fccee4a347a6e3132`  
Candidate rerank window: 20  
Max evidence: 24 items/candidate; 240 characters/item  
Max tokens: 12,000 input; 5,000 output  
Timeout: 8,000 ms  
Retry limit: 1  
Maximum adjustment: ±6

## SECURITY / DATA POLICY

Authorized candidates only: PASS  
External-AI gate: requires remote mode, `external_ai_eligible=true`, and `consent_confirmed=true`  
Clinical data handling: no live pilot data transmitted externally  
Raw media sent: 0  
Prompt logging: prompt bodies not logged; hashes and safe audit metadata only  
Unauthorized provider exposure: 0  
RESULT: PASS

Live policy finding: the ten pilots have `external_ai_status=ALLOWED`, but consent and internal usage remain `UNKNOWN`. They were therefore not sent to a remote model. View permission and external-AI status alone were not treated as sufficient consent.

## INPUT BOUNDARY

Raw Phase 17 input: rejected/fallback with zero candidates  
Malformed authorization set: rejected/fallback with zero candidates  
Unauthorized candidate: rejected  
Unknown candidate injection: rejected  
No retrieval or database lookup exists in the Phase 20 model adapter.  
RESULT: PASS

## MODEL OUTPUT VALIDATION

Schema compliance: strict exact-key, enum, finite-number, range, and completeness checks  
Unknown asset IDs: 0 accepted  
Unknown requirement IDs: 0 accepted  
Unknown evidence refs: 0 accepted  
Duplicate candidates: rejected  
Invalid scores: rejected  
Hallucinated accepted facts: 0  
RESULT: PASS

## PROMPT-INJECTION TESTS

Cases: DEV injection families plus focused unit cases  
Instruction-following violations: 0  
Candidate injection: rejected  
Evidence injection: rejected  
Unauthorized leakage: 0  
RESULT: PASS

## BOUNDED RERANKING

Phase 19 score retained: YES  
LLM maximum adjustment: ±6 points  
Hard constraint override: 0  
Hard exclusion override: 0  
Catastrophic weak-match promotion: 0  
Ineligible candidates remain score 0 and cannot be revived.  
RESULT: PASS

## FAILURE FALLBACK

Timeout: Phase 19 order preserved  
429: Phase 19 order preserved  
500: Phase 19 order preserved  
Network failure: Phase 19 order preserved  
Invalid JSON: Phase 19 order preserved  
Schema violation: Phase 19 order preserved  
Unknown asset: Phase 19 order preserved  
Unknown evidence: Phase 19 order preserved  
Provider outage: Phase 19 order preserved  
Phase 19 fallback preserved: YES  
RESULT: PASS

## DEV

Cases: 100  
Correct: 100  
Engineering invariants: 100%  
Hallucination violations: 0  
Security violations: 0  
Fallback cases correct: 39  
RESULT: PASS

## VALIDATION

Cases: 40  
Gold independent: YES  
Pairwise accuracy: 100%  
Top-1: 100%  
Top-3: 100%  
MRR: 1.000  
nDCG@2: 1.000  
Non-regression vs Phase 19: 100%  
Hallucination rate: 0%  
Schema-valid handling rate: 100%  
RESULT: PASS

## BLIND

Cases: 40  
Fresh: YES; cryptographic runtime nonce and shuffle  
Gold hidden: YES  
Independent: YES  
Pairwise accuracy: 100%  
Top-1: 100%  
Top-3: 100%  
MRR: 1.000  
nDCG@2: 1.000  
Non-regression: 100%  
Hallucinated accepted facts: 0  
RESULT: PASS

## STABILITY

Repeated cases: 20  
Top-1 consistency: 100%  
Pairwise consistency: 100%  
Schema validity: 100%  
Evidence-ref validity: 100%  
Adjustment variance: 0 under deterministic protected provider  
Threshold: 95%  
Result: PASS

## PILOT QUERIES

`neck injection`: `IMG_3429.MP4` — PASS  
`nek injecton`: `IMG_3429.MP4` — PASS  
`doctor injecting neck`: `IMG_3429.MP4` — PASS  
`lower face injection`: `IMG_0531.MP4` — PASS  
`clinician cleansing cheek`: `IMG_1160.MP4` — PASS  
`doctor working on scalp`: `IMG_2963.MP4` — PASS  
`frontal scalp procedure`: `IMG_2963.MP4` — PASS  
`scalp treatment`: `IMG_2963.MP4` — PASS  
`clinician treating scalp`: `IMG_1238.MP4`, accepted gold set — PASS  
`front-facing portrait`: `DSC08097.JPG`, accepted gold set — PASS

## NO-MATCH

Airplane cockpit: 0  
Wedding: 0  
Football stadium: 0  
Underwater coral reef: 0  
Fabricated candidates: 0  
RESULT: PASS

## PERFORMANCE

Protected synthetic/local measurements:

5 candidates: evidence assembly 0 ms; model 0.064270 ms; validation 0.035247 ms; combine 0.012093 ms; total 0.111610 ms; input/output 240/132 tokens  
10 candidates: evidence assembly 0 ms; model 0.059970 ms; validation 0.070233 ms; combine 0.017053 ms; total 0.147257 ms; input/output 450/252 tokens  
20 candidates: evidence assembly 0 ms; model 0.094803 ms; validation 0.145647 ms; combine 0.020797 ms; total 0.261247 ms; input/output 870/492 tokens

Live remote model latency: NOT APPLICABLE — external processing was not used.  
Estimated cost: NOT APPLICABLE / 0 external cost.

## CACHE

Cache enabled: YES, bounded in-memory 256 entries  
Key includes authorization: YES  
Key includes candidate fingerprint: YES  
Key includes evidence version: YES  
Key includes prompt/model/config: YES  
A→B: PASS  
B→A: PASS  
Concurrent A/B: PASS  
Cross-user leakage: 0  
RESULT: PASS

## PHASE 17 REGRESSION

Requested count metadata: PASS  
Age number: PASS  
Inferred union: PASS  
Clinician synonyms: PASS  
Typo retrieval: PASS; `nek injecton` includes `IMG_3429.MP4`  
No-match: PASS  
Live suite: 17/17 PASS  
RESULT: PASS

## PHASE 18 REGRESSION

Unauthorized candidate: removed before Phase 20  
Parent-child: zero scene/event/keyframe/transcript/OCR/search-document leakage  
External AI separation: PASS  
Fail closed: PASS  
Leakage: 0  
Live transaction: PASS and rolled back  
RESULT: PASS

## PHASE 19 REGRESSION

Fingerprint: PASS  
Hard constraints: PASS  
Hard exclusions: PASS  
UNKNOWN: PASS  
`neck injection`: PASS  
`nek injecton`: PASS  
`lower face injection`: PASS  
Deterministic fallback: PASS  
Live pilot: 14/14 PASS; ACL restored  
RESULT: PASS

## PILOT PRESERVATION

DSC03753.JPG: PASS  
DSC08097.JPG: PASS  
IMG_0493.MP4: PASS  
IMG_0531.MP4: PASS  
IMG_1148.MP4: PASS  
IMG_1160.MP4: PASS  
IMG_1238.MP4: PASS  
IMG_2963.MP4: PASS  
IMG_3429.MP4: PASS  
IMG_9871.MOV: PASS  
Preserved: 10/10  
RESULT: PASS

## DATABASE PRESERVATION

Assets before/after: 881 / 881  
Asset sources before/after: 881 / 881  
ACL before/after: 881 / 881  
Embeddings before/after: 106 / 106  
Search concepts before/after: 270 / 270  
Assertions before/after: 333 / 333  
Evidence before/after: 270 / 270  
Asset docs before/after: 10 / 10  
Scene docs before/after: 10 / 10  
App users before/after: 2 / 2  
UNKNOWN ACL rows: 881  
ACL restoration: PASS  
Temporary users: 0  
Temporary fixtures: 0  
RESULT: PASS

## FILES CHANGED

- `config/semantic-search/kdi_llm_reranker_v1.json`
- `dashboard/db/constrained-llm-reranker.ts`
- `dashboard/tests/phase20-constrained-llm-reranker.test.ts`
- `dashboard/scripts/phase20-benchmark.ts`
- `dashboard/scripts/phase20-live-preflight.ts`
- `dashboard/scripts/phase20-live-pilot.ts`
- `reports/semantic-search/phase20/benchmark.json`
- `reports/semantic-search/phase20/live_preflight.json`
- `reports/semantic-search/phase20/live_pilot.json`
- `reports/semantic-search/phase20/closure_evidence.json`
- `reports/semantic-search/phase20/PHASE_20_ABSOLUTE_FINAL.md`

## MIGRATIONS

Phase 20: NONE

Phase 17/18 migration-history drift: deployed functionality exists, but remote migration history still lacks versions `20260826034218` and `20260826043121`. No DDL or bookkeeping repair was attempted.

## SECRETS

Secrets exposed: 0  
RESULT: PASS

## ACCEPTANCE GATES

Gate 1: PASS  
Gate 2: PASS  
Gate 3: PASS  
Gate 4: PASS  
Gate 5: PASS  
Gate 6: PASS  
Gate 7: PASS  
Gate 8: PASS  
Gate 9: PASS  
Gate 10: PASS  
Gate 11: PASS  
Gate 12: PASS  
Gate 13: PASS  
Gate 14: PASS  
Gate 15: PASS  
Gate 16: PASS  
Gate 17: PASS  
Gate 18: PASS  
Gate 19: PASS  
Gate 20: PASS  
Gate 21: PASS  
Gate 22: PASS  
Gate 23: PASS  
Gate 24: PASS  
Gate 25: PASS  
Gate 26: PASS  
Gate 27: PASS  
Gate 28: PASS  
Gate 29: PASS  
Gate 30: PASS  
Gate 31: PASS  
Gate 32: PASS  
Gate 33: PASS  
Gate 34: PASS  
Gate 35: PASS  
Gate 36: PASS  
Gate 37: PASS  
Gate 38: PASS  
Gate 39: PASS  
Gate 40: PASS  
Gate 41: PASS  
Gate 42: PASS  
Gate 43: PASS  
Gate 44: PASS  
Gate 45: PASS  
Gate 46: PASS  
Gate 47: PASS

ALL MANDATORY GATES: PASS

## FINAL DECISION

PHASE 20: PASS  
PHASE 21 ALLOWED: YES  
REMAINING BLOCKERS: NONE
