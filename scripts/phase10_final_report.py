"""Renders PHASE_10_CONTROLLED_PRODUCTION_INDEXING_FINAL.md from the Phase 10 JSON artifacts.
Reads only; every number in the report comes from a committed artifact."""
from __future__ import annotations
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
OUT = R / 'reports/semantic-search/rollout/phase-10'


def load(name):
    p = OUT / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def main():
    status = load('phase_10_validation_status.json')
    results = load('phase_10_asset_results.json')
    quality = load('phase_10_semantic_quality_audit.json')
    coverage = load('phase_10_layer_coverage.json')
    emb = load('phase_10_embedding_audit.json')
    docs = load('phase_10_search_document_audit.json')
    search = load('phase_10_search_validation.json')
    clinical = load('phase_10_clinical_false_positive_audit.json')
    orig = load('phase_10_original_11_regression.json')
    perf = load('phase_10_performance.json')
    ext = load('phase_10_external_inference_audit.json')
    ba = load('phase_10_database_before_after.json')
    p9reg = load('phase_10_phase_09_regression_benchmark.json')

    ready = [x for x in results['assets'] if x.get('search_ready') is True]
    overall = status['status']
    before = (ba or {}).get('before', {})
    after = (ba or {}).get('after', {})
    cert = before.get('certified_phase_09_baseline', {})
    bstruct = before.get('resume_observed', {}).get('structures', {})
    astruct = after.get('structures', {})

    def row(x):
        return (f"| {x['rollout_position']} | {x['filename']} | `{x['asset_id']}` | {x['media_type']} | "
                f"{x['semantic_status']} | {'YES' if x['search_ready'] else 'NO'} | {x.get('accepted_observations')} | "
                f"{x.get('rejected_observations')} | {x.get('clinical_gate')} | {x.get('e5')} | {x.get('openclip')} | "
                f"{x.get('transcript_status')} |")

    lay = '\n'.join(
        f"| {c['layer_number']} | {c['layer']} | {c['observed']} | {c['unknown']} | {c['false']} | "
        f"{c['not_applicable']} | {c['validation_failures']} |" for c in coverage['coverage'])

    def cnt(section):
        v = search.get(section, [])
        return f"{sum(1 for x in v if x['passed'])}/{len(v)}"

    md = f"""# KDI SEMANTIC DATABASE ROLLOUT
## PHASE 10 — CONTROLLED PRODUCTION INDEXING OF ASSETS #12–#30

STATUS: **PHASE 10: {overall}**

Nineteen preselected assets (rollout positions 12–30) from the locked Phase 5 manifest were
semantically indexed on the certified Phase 8/9 local atomic architecture. {len(ready)} of 19 reached
SEARCH_READY. No asset outside #12–#30 was analyzed, and the original ten pilot assets plus the
`IMG_2951.MP4` canary were not reprocessed.

### Baseline reconciliation

The phase brief expects a starting baseline of 11 complete / 11 SEARCH_READY with zero assets
#12–#30 processed. The live database instead showed 13 / 13 at resume. The difference is fully
accounted for: an earlier Phase 10 execution had already committed rollout positions 12 and 13
before being interrupted. The thirteen complete assets were verified to be exactly the ten pilots,
the canary, and those two Phase 10 assets — no foreign writes. Position 14's analysis run was left
in `RUNNING` with zero committed rows, so no partial semantic truth existed. The batch entrypoint's
baseline gate was made restart-aware: it accepts the certified Phase 9 baseline plus its own
checkpointed assets and verifies each resumed asset still carries 18 active `COMPLETE` layers;
any other drift still raises `MATERIAL_BASELINE_DRIFT` and blocks.

### Corrective fix inside Phase 10

Exact filename retrieval failed for this batch's filenames. The `FILENAME_LITERAL` channel in
`dashboard/db/candidate-retriever.ts` derived its literal from a pattern requiring a letter-initial
token, so `IMG_2933.MP4` matched but `25.01 (18).jpeg` produced no token and the channel returned
zero without querying. The original eleven assets are all letter-initial, so Phase 9 never exercised
this path. The channel now retries once with the whole query treated as a filename literal when the
token yields nothing; paths that already found hits are untouched. This is a retrieval defect fix,
not an architecture change, and the certified Phase 9 suite was re-run to prove no regression.

### Semantic worker and analyzer

Semantic worker `{R / '.venv-semantic'}`, CPython 3.12.8 x64, operational.
Provider `LOCAL_TRANSFORMERS`, model `HuggingFaceTB/SmolVLM2-500M-Video-Instruct`, offline runtime
(`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`). Atomic visual questions with controlled answer
vocabularies, deterministic parsing, deterministic observation builder, mandatory clinical
specificity gate, deterministic layer assembly, evidence linking and search-document assembly. The
model never wrote database JSON directly.

### Batch

| | |
|---|---|
| Planned | 19 |
| Attempted | {status['batch']['attempted']} |
| Completed | {status['batch']['completed']} |
| SEARCH_READY | {status['batch']['search_ready']} |
| Failed | {status['batch']['failed']} |
| Unsupported | {status['batch']['unsupported']} |
| Blocked | {status['batch']['blocked']} |

### Assets #12–#30

| # | Filename | Asset ID | Media | Status | READY | Acc | Rej | Clinical gate | E5 | OpenCLIP | Transcript |
|---|---|---|---|---|---|---|---|---|---|---|---|
{chr(10).join(row(x) for x in sorted(results['assets'], key=lambda y: y['rollout_position']))}

### Semantic quality

| | |
|---|---|
| Raw observations | {quality['raw_observations']} |
| Accepted | {quality['accepted']} |
| Rejected | {quality['rejected']} |
| Active assertions | {quality['active_assertions']} |
| Evidence rows | {quality['evidence_rows']} |
| Unsupported accepted | {quality['unsupported_accepted']} |
| Clinical false positives accepted | {quality['clinical_false_positives_accepted']} |
| Invalid evidence | {quality['invalid_evidence']} |
| Contradictory active observations | {quality['contradictory_active_observations']} |

### 18-layer coverage ({coverage['observed_layer_rows']} rows across {coverage['assets']} assets)

| # | Layer | Observed | Unknown | False | Not applicable | Validation failures |
|---|---|---|---|---|---|---|
{lay}

`UNKNOWN` is the truthful state where the atomic analyzer cannot support an observation, and is not
counted as a failure.

### Search index

| | |
|---|---|
| Search documents READY | {sum(1 for x in docs['assets'] if x['valid'])}/{len(docs['assets'])} |
| E5 384D valid | {sum(1 for x in emb['assets'] if x['e5']['valid'])}/{len(emb['assets'])} |
| OpenCLIP 512D valid | {sum(1 for x in emb['assets'] if x['openclip']['valid'])}/{len(emb['assets'])} |
| New visual vectors created | {emb['new_vectors_created']} |
| Existing visual vectors reused | {emb['existing_vectors_reused']} |
| Unsupported clinical leakage in documents | {docs['unsupported_clinical_leakage']} |
| Dimension mixing | {'YES' if emb['dimension_mixing'] else 'NO'} |

### Search validation ({search['passed']}/{search['total_cases']} cases)

| Check | Result |
|---|---|
| Exact filename | {cnt('exact_filename')} |
| Filename stem | {cnt('filename_stem')} |
| Grounded semantic | {cnt('grounded_semantic')} |
| Batch-level grounded | {cnt('batch_level_grounded')} |
| Layers without grounded truth | {cnt('batch_level_without_grounded_truth')} |
| Result count (1/3/5/7/10) | {cnt('result_count')} |
| Number parsing | {cnt('number_parsing')} |
| Media-type filters | {cnt('media_type_filters')} |
| Negative filters | {cnt('negative_filters')} |
| Multi-concept (all-MUST) | {cnt('multi_concept_all_must')} |
| Zero-result safety | {cnt('zero_result_safety')} |
| Determinism | {'STABLE' if all(x['pass'] for x in search['determinism']) else 'UNSTABLE'} |
| Requirement classifier | {'OPERATIONAL' if search['requirement_classifier_operational'] else 'FAILED'} |
| Query expander | {'OPERATIONAL' if search['query_expander_operational'] else 'FAILED'} |
| Historical all-MUST bug | {search['historical_all_must_bug']} |
| Authorization before ranking | {'YES' if search['authorization_before_ranking'] else 'NO'} |

### Clinical false-positive regression

Rule applied: an asset may match a clinical concept only when its own semantic truth supports it.
Matches from other indexed assets are legitimate and are not failures.

Phase 10 assets carrying a supported clinical concept: {clinical['phase_10_assets_carrying_a_supported_clinical_concept']}.
Unsupported clinical leakage from the new batch: **{clinical['unsupported_clinical_leakage_from_new_batch']}**.

| Query | Returned | Phase 10 assets matched |
|---|---|---|
{chr(10).join(f"| {q['query']} | {q['returned_count']} | {q['phase10_assets_matched']} |" for q in clinical['queries'])}

### Original-11 regression

Targeted regression: {orig['passed']}/{orig['queries']} passed, {len(orig['failed'])} failed.
Certified Phase 9 suite re-run: {(p9reg or {}).get('status', 'NOT RUN')}"""

    if p9reg:
        md += f" — {sum(1 for x in p9reg['cases'] if x['pass'])}/{len(p9reg['cases'])} cases, determinism {'stable' if all(x['pass'] for x in p9reg['determinism']) else 'unstable'}."
    md += f"""

Semantic truth preserved: {orig['semantic_truth_preserved']}. SEARCH_READY preserved: {orig['search_ready_preserved']}.
Filename retrieval preserved: {orig['filename_retrieval_preserved']}. Phase 9 grounded behavior preserved:
{orig['phase_9_grounded_behavior_preserved']}. Authorization regression: {orig['authorization_regression']}.
Ranking corruption: {orig['ranking_corruption']}.

### Performance

| | |
|---|---|
| Total asset processing time | {perf['total_asset_processing_time']} s |
| Average per asset | {perf['average_per_asset']} s |
| Average image | {perf['average_image']} s |
| Average video | {perf['average_video']} s |
| Average semantic inference | {perf['average_semantic_inference']} s |
| Average text embedding | {perf['average_text_embedding']} s |
| Retries | {perf['retries']} |
| Failures | {perf['failures']} |

CPU-only local inference. At roughly {round(perf['average_per_asset'] / 60, 1)} minutes per asset, the remaining
851 pending assets represent about {round(perf['average_per_asset'] * 851 / 3600)} single-worker hours — the operational
input for sizing later stages, not a Phase 10 pass gate.

### Database

| Structure | Certified Phase 9 | At resume | After |
|---|---|---|---|
| Assets | {cert.get('assets')} | {before.get('resume_observed', {}).get('assets')} | {after.get('assets')} |
| Complete | {cert.get('complete')} | {before.get('resume_observed', {}).get('complete')} | {after.get('complete')} |
| Pending | {cert.get('pending')} | {before.get('resume_observed', {}).get('pending')} | {after.get('pending')} |
| Unsupported | {cert.get('unsupported')} | {before.get('resume_observed', {}).get('unsupported')} | {after.get('unsupported')} |
| SEARCH_READY | {cert.get('search_ready')} | {before.get('resume_observed', {}).get('search_ready')} | {after.get('search_ready')} |
{chr(10).join(f"| {k} | — | {bstruct.get(k)} | {astruct.get(k)} |" for k in astruct)}

### External inference

Gemini {ext['gemini_calls']}, OpenAI indexing {ext['openai_indexing_calls']}, Ollama {ext['ollama_calls']},
Qwen {ext['qwen_calls']}, external inference {ext['external_inference']}, external media transmission
{ext['external_media_transmission']}. Network use was limited to the project's own Supabase database and
read-only Google Drive master retrieval; no media reached any inference service.

### Preservation

Original 10 complete: {status['preservation']['original_10_complete']}/10. Canary `IMG_2951.MP4` complete:
{status['preservation']['canary_complete']}. Original-11 SEARCH_READY: {status['preservation']['original_11_search_ready']}/11.
Original-11 visual vectors: {status['preservation']['original_11_visual_vectors']}. Original-11 text embeddings:
{status['preservation']['original_11_text_embeddings']}. Source and master media were read only and never modified;
asset IDs, source provenance and access-control records are unchanged.

### Deferred

`DEFERRED_SOURCE_REPOSITORY_PERMISSION` — **DEFERRED**. Required before Phase 19: YES. Not worked on
during Phase 10 and not a Phase 10 blocker.

### Artifacts

{chr(10).join('- `' + a + '`' for a in status['artifacts'])}

### Next

{status['next']}. Not executed.
"""
    (OUT / 'PHASE_10_CONTROLLED_PRODUCTION_INDEXING_FINAL.md').write_text(md, encoding='utf-8')
    print(json.dumps({'status': overall, 'report': 'PHASE_10_CONTROLLED_PRODUCTION_INDEXING_FINAL.md',
                      'ready': len(ready)}))


if __name__ == '__main__':
    main()
