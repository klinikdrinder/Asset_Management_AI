KDI SEMANTIC SEARCH V3
PHASE 24 BENCHMARK FRAMEWORK — ABSOLUTE FINAL

STATUS:
PASS

IMPLEMENTATION VERSION:
kdi_semantic_benchmark_runner_v1

BENCHMARK VERSION:
kdi_semantic_benchmark_v1

PREVIOUS EXECUTION BLOCKER:
The original live sequential process was stopped before finalization because both local query encoders were cold-started repeatedly per query, making execution unnecessarily prolonged; no completed-case checkpoint was flushed, so the interrupted process produced no resumable run artifact. The first preserved repaired attempts also identified six exact integration failures: C11, C18, C32, and C33 were misclassified as context-dependent first turns (CONTEXT_NOT_AVAILABLE), while C36 and C39 attempted ordinal references against empty prior result scopes (ORDINAL_OUT_OF_RANGE).

EXECUTION FIX:
Precompute each unique query vector once per benchmark invocation; force each benchmark case's first turn through the canonical NEW_QUERY path; retain isolated run-and-case session keys for later turns; checkpoint atomically after every completed case; resume by the same benchmark_run_id while skipping completed case IDs; enforce a centralized 180000 ms per-case timeout; preserve errors and continue later cases; clear session state between runs; finalize to append-only immutable run artifacts.

CHECKPOINT/RESUME:
PASS

HISTORICAL INCOMPLETE RUN:
PRESERVED

INITIAL SUITE CASES:
40

SINGLE-TURN CASES:
35

MULTI-TURN CASES:
5

RUN A:
40 / 40

RUN A STATUS:
FINALIZED

RUN A ID:
6d91f336-d458-4115-8fd6-74fa9ea843c1

RUN B:
40 / 40

RUN B STATUS:
FINALIZED

RUN B ID:
2f4ecdac-f363-417c-8c92-51ea6d9785f4

SINGLE-TURN RUN A:
35 / 35

SINGLE-TURN RUN B:
35 / 35

MULTI-TURN RUN A:
5 / 5

MULTI-TURN RUN B:
5 / 5

DETERMINISTIC CASES COMPARED:
40 / 40

IDENTICAL CASE OUTCOMES:
40 / 40

DETERMINISTIC REPRODUCIBILITY:
100%

DIFFERING CASES:
NONE

ORDERED RESULT CAPTURE:
PASS

COUNT METADATA CAPTURE:
PASS

GROUNDING STATUS CAPTURE:
PASS

SESSION/CONVERSATION SUPPORT:
PASS

CROSS-CASE SESSION LEAKAGE:
0

CROSS-RUN SESSION LEAKAGE:
0

SPEC FINGERPRINT GUARD:
PASS

PILOT MANIFEST GUARD:
PASS

ACTUAL TIMING CAPTURE:
PASS

MEAN LATENCY:
1465.242 ms

MEDIAN LATENCY:
1222.013 ms

P95 LATENCY:
3335.598 ms

MIN LATENCY:
612.175 ms

MAX LATENCY:
3641.295 ms

ERROR CAPTURE:
PASS

HISTORICAL RUN PRESERVATION:
PASS

FINAL GOLD ANSWERS CREATED:
NO

FINAL ACCURACY CLAIMED:
NO

OPENAI API CALLS:
0

QUERY-TIME VISION CALLS:
0

QUERY-TIME OCR CALLS:
0

QUERY-TIME TRANSCRIPTION CALLS:
0

MEDIA REPROCESSED:
0

SEMANTIC DATA CHANGED:
0

ACL CHANGED:
0

TARGETED REPAIR TESTS:
13 / 13

PHASE 24:
PASS

SAFE TO START PHASE 25:
YES

REMAINING BLOCKERS:
NONE
