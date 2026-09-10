# KDI SEMANTIC SEARCH V3

## PHASE 20 REAL-MODEL CLOSURE — ABSOLUTE FINAL

STATUS:
BLOCKED_API_ACCESS

429 ROOT CAUSE:
CREDIT_BALANCE_EXHAUSTED — OpenAI reported that the API key/project exceeded its current quota and directed the account owner to check plan and billing details.

429 ERROR CODE:
insufficient_quota

429 ERROR TYPE:
insufficient_quota

RECOVERY:
One corrected tiny synthetic Luna preflight reproduced the 429 and captured the exact cause. No `Retry-After` header was present. Because this is a quota/billing failure rather than a temporary or model-specific rate limit, retries stopped immediately and Terra was not attempted.

REAL LLM EXECUTED:
NO

PROVIDER:
OpenAI

MODEL:
gpt-5.6-luna

SUCCESSFUL REAL MODEL CALLS:
0

FAILED REAL MODEL CALLS:
1 corrected diagnostic preflight in this closure; HTTP 429 before inference

SYNTHETIC CASES:
NOT_RUN — stopped after non-retryable quota diagnosis

SEMANTIC CORRECTNESS:
NOT_AVAILABLE

CONSISTENCY:
Top-1 NOT_AVAILABLE
Pairwise NOT_AVAILABLE

HALLUCINATED IDS ACCEPTED:
0

HALLUCINATED EVIDENCE ACCEPTED:
0

HARD CONSTRAINT VIOLATIONS:
0

HARD EXCLUSION VIOLATIONS:
0

PROMPT INJECTION SUCCESSES:
0

OUT-OF-BOUND ADJUSTMENTS:
0

MALFORMED RESPONSE HANDLING:
PASS — previously verified targeted suite

PHASE 19 FALLBACK:
PASS — previously verified

PHASE 19 FALLBACK DETERMINISM:
PASS — previously verified

PRODUCTION DATA SENT:
0

INPUT TOKENS:
NOT_AVAILABLE — request rejected before inference

OUTPUT TOKENS:
NOT_AVAILABLE — request rejected before inference

TOTAL TOKENS:
NOT_AVAILABLE — request rejected before inference

LATENCY:
Approximately 3.7 seconds for the corrected diagnostic command

ESTIMATED COST:
NOT_AVAILABLE

PRODUCTION DATABASE MODIFIED:
NO

TARGETED TESTS:
10 / 10 previously passed; not rerun after the definitive quota stop

PHASE 20:
BLOCKED

SAFE TO START PHASE 21:
NO

IF BLOCKED_API_ACCESS, HUMAN ACTION REQUIRED:
Add API credits or restore billing/quota for the OpenAI API project associated with the configured `OPENAI_API_KEY`, then rerun the Phase 20 real-model closure.

REMAINING BLOCKERS:
OpenAI API `insufficient_quota` prevents any genuine model inference, so the 30-case accuracy and 10×5 consistency gates cannot be executed.

SANITIZED DIAGNOSTIC:
HTTP 429; request ID `req_2427923497384e8494027df68cb6b233`; no Retry-After header; model `gpt-5.6-luna`. No API key or production data was logged or transmitted.
