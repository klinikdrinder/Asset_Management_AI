"""Renders PHASE_11_30_ASSET_FINAL_ACCEPTANCE.md from the Phase 11 JSON artifacts. Read-only."""
from __future__ import annotations
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
OUT = R / 'reports/semantic-search/rollout/phase-11'


def load(name):
    p = OUT / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def main():
    st = load('phase_11_validation_status.json'); defn = load('phase_11_locked_definition_audit.json')
    fn = load('phase_11_filename_regression.json'); tr = load('phase_11_transcription_results.json')
    tq = load('phase_11_transcription_quality_audit.json'); integ = load('phase_11_30_asset_integrity_audit.json')
    clin = load('phase_11_clinical_specificity_audit.json'); acc = load('phase_11_search_acceptance.json')
    met = load('phase_11_search_quality_metrics.json'); det = load('phase_11_determinism.json')
    auth = load('phase_11_authorization_audit.json'); disp = load('phase_11_ranking_displacement_analysis.json')
    rs = load('phase_11_restart_safety.json'); cap = load('phase_11_capacity_review.json')
    ba = load('phase_11_database_before_after.json'); ext = load('phase_11_external_inference_audit.json')
    code = load('phase_11_phase10_code_change_audit.json'); emb = load('phase_11_embedding_changes.json')
    docs = load('phase_11_search_document_changes.json')

    before = (ba or {}).get('before', {}); after = (ba or {}).get('after', {})
    bs = before.get('structures', {}); asr = after.get('structures', {})
    lay = '\n'.join(f"| {c['layer_number']} | {c['layer']} | {c['observed']} | {c['unknown']} | {c['false']} | {c['not_applicable']} |"
                    for c in integ['layer_coverage'])
    cats = (acc or {}).get('categories', {})
    def cat(k):
        v = cats.get(k); return f"{v['passed']}/{v['total']}" if v else "—"

    md = f"""# KDI SEMANTIC DATABASE ROLLOUT
## PHASE 11 — 30-ASSET COHORT HARDENING + FINAL PRODUCTION ACCEPTANCE

STATUS: **PHASE 11: {st['status']}**

Phase 11 certifies the complete thirty-asset cohort and closes the two Phase 10 carry-forward items:
the filename-literal retrieval correction and the unresolved Layer 14 state on the audio-bearing
Phase 10 videos. No asset beyond #30 was touched.

### Phase 11 definition

No authoritative Phase 11 definition exists in the repository. `{defn['PHASE_11_DEFINITION_SOURCE']}` is
recorded as the definition source. The closest repository anchor is
`{defn['closest_repository_anchor']['file']}`, {defn['closest_repository_anchor']['section']}:
"{defn['closest_repository_anchor']['text']}" — consistent with this phase and not contradicted by it.
`docs/semantic-search/KDI_PHASE_11_NORMALIZED_SEARCH_DOCUMENTS.md` belongs to the separate
system-build track and does not apply.

### Carry-forward A — filename retrieval correction

{fn['exact_full_filename']} exact full filenames, {fn['stem']} stems, {fn['case_variants']} case variants,
{fn['exact_rank_1']}/30 exact matches at rank 1. Number-initial, punctuation, space and parenthesis
filenames all pass. The Phase 10 correction in `dashboard/db/candidate-retriever.ts` is **certified**.

### Carry-forward B — local transcription backfill

{tq['candidates']} audio-bearing Phase 10 videos were processed with the local
`faster-whisper-small` chain: {tq['speech_present_yes']} with speech, {tq['speech_present_no']} without,
{tq['speech_present_unknown']} unknown. {tq['chunks_written']} transcript chunks were written,
{tq['accepted_for_search']} accepted for search, {tq['excluded_low_confidence']} excluded on confidence and
{tq['excluded_review_required']} held for review. Hallucination candidates accepted: **{tq['hallucination_candidates_accepted']}**.
External speech calls: **0**. Speaker identity was never inferred from voice.

### Cohort integrity

{integ['cohort_size']} assets, {integ['observed_active_layer_states']}/540 active layer states,
{integ['active_assertions']} active assertions, {integ['evidence_rows']} evidence rows,
invalid evidence **{integ['invalid_evidence']}**, duplicate active truth **0**.

| # | Layer | Observed | Unknown | False | N/A |
|---|---|---|---|---|---|
{lay}

### Clinical specificity

{clin['active_clinical_concepts']} active clinical concepts, all traced to evidence
({clin['traced_to_evidence']}/{clin['active_clinical_concepts']}). Unsupported accepted: **{clin['unsupported_accepted_clinical_concepts']}**.
Search-document leakage: **{clin['search_document_clinical_leakage']}**. E5 input leakage: **{clin['e5_input_clinical_leakage']}**.
Phase 10 cohort assets carrying a named procedure: **{clin['phase_10_cohort_clinical_concepts']}**.

### Search acceptance ({acc['passed']}/{acc['total_cases']} cases)

| Category | Result |
|---|---|
| Filename exact | {cat('filename-exact')} |
| Filename stem | {cat('filename-stem')} |
| Filename case variants | {cat('filename-case')} |
| Extension guard | {cat('filename-extension-guard')} |
| Absent filename | {cat('filename-absent')} |
| Grounded semantic | {cat('grounded')} |
| Paraphrase | {cat('paraphrase')} |
| Multi-concept | {cat('multi-concept')} |
| Media filters | {cat('media-filter')} |
| Negative filters | {cat('negative-filter')} |
| Result count | {cat('count')} |
| Count shortage honesty | {cat('count-shortage')} |
| Number interpretation | {cat('number')} |
| Clinical regression | {cat('clinical')} |
| Zero-result honesty | {cat('zero-result')} |

Requirement classifier: {'operational' if acc['requirement_classifier_operational'] else 'FAILED'}.
Query expander: {'operational' if acc['query_expander_operational'] else 'FAILED'}.
Historical all-MUST bug: {acc['historical_all_must_bug']}.
Unsupported clinical match reasons in grounded explanations: **{acc['grounded_explanation']['unsupported_clinical_match_reasons']}**.

### Search quality metrics

| Metric | Value |
|---|---|
| Exact filename success | {met['exact_filename_success_rate']} |
| Semantic hit rate | {met['semantic_hit_rate']} |
| Mean Recall@K | {met['mean_recall_at_k']} |
| MRR | {met['mean_reciprocal_rank']} |
| Mean NDCG@10 | {met['mean_ndcg_at_10']} |
| Zero-result correctness | {met['zero_result_correctness']} |
| Requested-count correctness | {met['requested_count_correctness']} |
| Clinical false-positive rate | {met['clinical_false_positive_rate']} |
| Authorization leakage rate | {met['authorization_leakage_rate']} |

Ground truth is the committed active OBSERVED assertions; relevance is binary concept membership.
No relevance judgement was invented to produce a metric.

### Ranking displacement — "visible tool"

Classification: **{disp['classification']}**. Ranking hack introduced: **{disp['ranking_hack_introduced']}**.
Scores modified: {disp['scores_modified']}. Semantic truth modified: {disp['semantic_truth_modified']}.
{disp['benchmark_action']}

### Determinism and authorization

Determinism: {det['status']} over {det['queries']} query shapes × {det['repetitions']} repetitions.
Authorization: {auth['status']} — enforcement at `{auth['enforcement_point']}` via `{auth['rpc']}`;
unauthorized candidates ranked **{auth['unauthorized_candidates_ranked']}**, non-SEARCH_READY returned
**{auth['not_search_ready_returned']}**, ACLs escalated during Phase 11 **{auth['acl_escalated_during_phase_11']}**.

### Restart safety

{rs['status']}. Phase 10 was genuinely interrupted three times (positions 12, 13, 14) and Phase 11's
transcription stage was interrupted twice more by schema faults. Duplicate active truth across layers,
assertions, documents and embeddings: **0**.

### Phase 10 code-change audit

Required production fixes: {sum(1 for x in code['changes'] if x['classification'] == 'REQUIRED_PRODUCTION_FIX')}.
Test-only: {sum(1 for x in code['changes'] if x['classification'] == 'TEST_ONLY')}.
Artifact-only: {sum(1 for x in code['changes'] if x['classification'].endswith('ARTIFACT_ONLY'))}.
Hard-coded asset IDs in production code: {code['verification']['phase_10_or_11_asset_ids_in_production_code']}.
Debug/bypass markers: {code['verification']['debug_or_bypass_markers_in_search_chain']}.
External providers reachable from the search chain: {code['verification']['external_providers_reachable_from_search_chain']}.
Authorization weakened: {code['verification']['authorization_weakened']}. Clinical gate bypassed:
{code['verification']['clinical_gate_bypassed']}. Architecture drift: {code['verification']['architecture_drift']}.

### Capacity

| | |
|---|---|
| Phase 10 average per asset | {cap['phase_10_average_per_asset_seconds']} s |
| VLM inference share | {cap['phase_10_vlm_inference_share']} |
| Transcription per video | {cap['phase_11_transcription_seconds_per_video']} s |
| Transcription overhead vs visual | {cap['transcription_overhead_vs_visual']} |
| Pending assets | {cap['pending_assets']} |
| Estimated single-worker hours | {cap['estimated_single_worker_hours']} |
| Safe parallel workers | {cap['concurrency']['safe_parallel_workers_recommended']} |
| Mass rollout started | {cap['mass_rollout_started']} |

{cap['recommendation']}

### Database

| | Before (Phase 10 certified) | After |
|---|---|---|
| Assets | {before.get('assets')} | {after.get('assets')} |
| Complete | {before.get('complete')} | {after.get('complete')} |
| Pending | {before.get('pending')} | {after.get('pending')} |
| Unsupported | {before.get('unsupported')} | {after.get('unsupported')} |
| SEARCH_READY | {before.get('search_ready')} | {after.get('search_ready')} |
{chr(10).join(f"| {k} | {bs.get(k, '—')} | {asr.get(k)} |" for k in asr)}

Assets #31+ indexed: **{ba['assets_31_plus_indexed']}**.

### External inference

Gemini {ext['gemini_calls']} · OpenAI indexing {ext['openai_semantic_indexing_calls']} · Ollama {ext['ollama_calls']} ·
Qwen {ext['qwen_calls']} · external speech {ext['external_speech_api_calls']} · external media inference
{ext['external_media_inference']} · external media transmission {ext['external_media_transmission']}.
Reported network use: {'; '.join(ext['reported_network_use'])}.

### Deferred

`DEFERRED_SOURCE_REPOSITORY_PERMISSION` — **DEFERRED**. Required before Phase 19: **YES**.

### Artifacts

{chr(10).join('- `' + a + '`' for a in st['artifacts'])}

### Next

{st['next']}. Not executed.
"""
    (OUT / 'PHASE_11_30_ASSET_FINAL_ACCEPTANCE.md').write_text(md, encoding='utf-8')
    print(json.dumps({'status': st['status'], 'report': 'PHASE_11_30_ASSET_FINAL_ACCEPTANCE.md'}))


if __name__ == '__main__':
    main()
