# KDI SEMANTIC DATABASE ROLLOUT
## PHASE 11 — 30-ASSET COHORT HARDENING + FINAL PRODUCTION ACCEPTANCE

STATUS: **PHASE 11: PASS**

Phase 11 certifies the complete thirty-asset cohort and closes the two Phase 10 carry-forward items:
the filename-literal retrieval correction and the unresolved Layer 14 state on the audio-bearing
Phase 10 videos. No asset beyond #30 was touched.

### Phase 11 definition

No authoritative Phase 11 definition exists in the repository. `PROMPT_CONTROLLED_FALLBACK` is
recorded as the definition source. The closest repository anchor is
`docs/semantic-search/KDI_FUTURE_INDEXING_ROLLOUT_PLAN_V1.md`, Stage B:
"Stage B: validate 30 total assets (540 layer evaluations)." — consistent with this phase and not contradicted by it.
`docs/semantic-search/KDI_PHASE_11_NORMALIZED_SEARCH_DOCUMENTS.md` belongs to the separate
system-build track and does not apply.

### Carry-forward A — filename retrieval correction

30/30 exact full filenames, 30/30 stems, 60/60 case variants,
30/30 exact matches at rank 1. Number-initial, punctuation, space and parenthesis
filenames all pass. The Phase 10 correction in `dashboard/db/candidate-retriever.ts` is **certified**.

### Carry-forward B — local transcription backfill

8 audio-bearing Phase 10 videos were processed with the local
`faster-whisper-small` chain: 0 with speech, 7 without,
1 unknown. 1 transcript chunks were written,
0 accepted for search, 0 excluded on confidence and
1 held for review. Hallucination candidates accepted: **0**.
External speech calls: **0**. Speaker identity was never inferred from voice.

### Cohort integrity

30 assets, 540/540 active layer states,
445 active assertions, 402 evidence rows,
invalid evidence **0**, duplicate active truth **0**.

| # | Layer | Observed | Unknown | False | N/A |
|---|---|---|---|---|---|
| 1 | Asset Identity & Provenance | 30 | 0 | 0 | 0 |
| 2 | Global Asset Understanding | 10 | 20 | 0 | 0 |
| 3 | Temporal / Scene Structure | 28 | 0 | 0 | 2 |
| 4 | People & Roles | 25 | 0 | 5 | 0 |
| 5 | Person Appearance | 10 | 20 | 0 | 0 |
| 6 | Anatomy | 21 | 0 | 9 | 0 |
| 7 | Treatment / Procedure | 3 | 27 | 0 | 0 |
| 8 | Actions & Events | 17 | 0 | 13 | 0 |
| 9 | Relationships | 10 | 20 | 0 | 0 |
| 10 | Clinical Visual Observations | 17 | 2 | 11 | 0 |
| 11 | Environment | 7 | 4 | 19 | 0 |
| 12 | Cinematography | 10 | 20 | 0 | 0 |
| 13 | Composition | 10 | 20 | 0 | 0 |
| 14 | Speech / Transcript / Audio | 14 | 3 | 0 | 13 |
| 15 | OCR / Visible Text | 1 | 27 | 2 | 0 |
| 16 | Marketing & Content Usage | 10 | 20 | 0 | 0 |
| 17 | Semantic Narrative | 10 | 20 | 0 | 0 |
| 18 | Search & Embeddings | 30 | 0 | 0 | 0 |

### Clinical specificity

38 active clinical concepts, all traced to evidence
(38/38). Unsupported accepted: **0**.
Search-document leakage: **0**. E5 input leakage: **0**.
Phase 10 cohort assets carrying a named procedure: **0**.

### Search acceptance (189/192 cases)

| Category | Result |
|---|---|
| Filename exact | 30/30 |
| Filename stem | 30/30 |
| Filename case variants | 60/60 |
| Extension guard | 4/4 |
| Absent filename | 2/2 |
| Grounded semantic | 25/28 |
| Paraphrase | 5/5 |
| Multi-concept | 4/4 |
| Media filters | 2/2 |
| Negative filters | 2/2 |
| Result count | 5/5 |
| Count shortage honesty | 1/1 |
| Number interpretation | 4/4 |
| Clinical regression | 7/7 |
| Zero-result honesty | 5/5 |

Requirement classifier: operational.
Query expander: operational.
Historical all-MUST bug: ABSENT.
Unsupported clinical match reasons in grounded explanations: **0**.

### Search quality metrics

| Metric | Value |
|---|---|
| Exact filename success | 1.0 |
| Semantic hit rate | 0.7941 |
| Mean Recall@K | 0.781 |
| MRR | 0.7406 |
| Mean NDCG@10 | 0.9209 |
| Zero-result correctness | 5/5 |
| Requested-count correctness | 6/6 |
| Clinical false-positive rate | 0.0 |
| Authorization leakage rate | 0.0 |

Ground truth is the committed active OBSERVED assertions; relevance is binary concept membership.
No relevance judgement was invented to produce a metric.

### Ranking displacement — "visible tool"

Classification: **B_EXPECTED_INDEX_GROWTH_DISPLACEMENT**. Ranking hack introduced: **False**.
Scores modified: False. Semantic truth modified: False.
The fixed-asset top-5 assertion is superseded by a relevant-set assertion measuring recall and MRR over every asset that actually carries the concept. The historical case is retained in the Phase 9 and Phase 10 artifacts and is not deleted.

### Determinism and authorization

Determinism: PASS over 6 query shapes × 3 repetitions.
Authorization: PASS — enforcement at `authorizeCandidates() runs before reranking and result-count control` via `phase18_authorize_candidates_for`;
unauthorized candidates ranked **0**, non-SEARCH_READY returned
**0**, ACLs escalated during Phase 11 **0**.

### Restart safety

PASS. Phase 10 was genuinely interrupted three times (positions 12, 13, 14) and Phase 11's
transcription stage was interrupted twice more by schema faults. Duplicate active truth across layers,
assertions, documents and embeddings: **0**.

### Phase 10 code-change audit

Required production fixes: 4.
Test-only: 4.
Artifact-only: 3.
Hard-coded asset IDs in production code: 0.
Debug/bypass markers: 0.
External providers reachable from the search chain: 0.
Authorization weakened: False. Clinical gate bypassed:
False. Architecture drift: False.

### Capacity

| | |
|---|---|
| Phase 10 average per asset | 417.555 s |
| VLM inference share | 0.985 |
| Transcription per video | 2.683 s |
| Transcription overhead vs visual | 0.0064 |
| Pending assets | 850 |
| Estimated single-worker hours | 98.6 |
| Safe parallel workers | 2 |
| Mass rollout started | False |

Do not scale to the full library from this phase. Validate Stage C (100 assets) with at most two workers and a real claim/lease before Stage D.

### Database

| | Before (Phase 10 certified) | After |
|---|---|---|
| Assets | 881 | 881 |
| Complete | 30 | 30 |
| Pending | 850 | 850 |
| Unsupported | 1 | 1 |
| SEARCH_READY | 30 | 30 |
| asset_semantic_layers_active | — | 540 |
| asset_semantic_layers_total | — | 558 |
| semantic_assertions | 437 | 501 |
| semantic_assertion_evidence | 374 | 438 |
| asset_search_documents | 30 | 30 |
| search_document_builds | 85 | 85 |
| semantic_embeddings | 137 | 137 |
| asset_visual_embeddings | 875 | 875 |
| asset_scenes | 322 | 322 |
| asset_keyframes | 355 | 355 |
| asset_transcript_chunks | 14 | 15 |
| ocr_observations | 19 | 19 |

Assets #31+ indexed: **0**.

### External inference

Gemini 0 · OpenAI indexing 0 · Ollama 0 ·
Qwen 0 · external speech 0 · external media inference
0 · external media transmission False.
Reported network use: Supabase — the project's own database; Google Drive — authorized read-only master media retrieval.

### Deferred

`DEFERRED_SOURCE_REPOSITORY_PERMISSION` — **DEFERRED**. Required before Phase 19: **YES**.

### Artifacts

- `PHASE_11_30_ASSET_FINAL_ACCEPTANCE.md`
- `phase_11_30_asset_integrity_audit.json`
- `phase_11_authorization_audit.json`
- `phase_11_capacity_review.json`
- `phase_11_clinical_specificity_audit.json`
- `phase_11_database_before_after.json`
- `phase_11_determinism.json`
- `phase_11_embedding_changes.json`
- `phase_11_external_inference_audit.json`
- `phase_11_filename_regression.json`
- `phase_11_human_review_packet.json`
- `phase_11_locked_definition_audit.json`
- `phase_11_phase10_code_change_audit.json`
- `phase_11_ranking_displacement_analysis.json`
- `phase_11_raw_acceptance.json`
- `phase_11_restart_safety.json`
- `phase_11_search_acceptance.json`
- `phase_11_search_document_changes.json`
- `phase_11_search_quality_metrics.json`
- `phase_11_transcription_candidate_manifest.json`
- `phase_11_transcription_quality_audit.json`
- `phase_11_transcription_results.json`
- `phase_11_transcription_results.pre_meaningfulness_gate.json`
- `phase_11_transcription_run.err.log`
- `phase_11_transcription_run.log`
- `phase_11_validation_status.json`

### Next

Stage C — 100-asset validation. Not executed.
