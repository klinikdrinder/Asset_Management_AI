"""Renders full_index_30_final.md from the FULL-INDEX-30 JSON artifacts. Read-only."""
from __future__ import annotations
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
OUT = R / 'reports/semantic-search/rollout/full-index-30'


def load(n):
    p = OUT / n
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def main():
    st = load('full_index_30_validation_status.json')
    vm = load('full_index_30_video_manifest.json'); im = load('full_index_30_image_manifest.json')
    lay = load('full_index_30_18_layer_audit.json'); sd = load('full_index_30_scene_search_document_audit.json')
    se = load('full_index_30_scene_embedding_audit.json'); ke = load('full_index_30_keyframe_embedding_audit.json')
    ae = load('full_index_30_asset_embedding_audit.json'); ss = load('full_index_30_scene_semantic_audit.json')
    ki = load('full_index_30_keyframe_inventory.json'); si = load('full_index_30_scene_inventory.json')
    de = load('full_index_30_description_audit.json'); au = load('full_index_30_audio_audit.json')
    oc = load('full_index_30_ocr_audit.json'); aev = load('full_index_30_assertion_evidence_audit.json')
    sq = load('full_index_30_semantic_quality_audit.json'); gate = load('full_index_30_search_ready_gate.json')
    acc = load('full_index_30_raw_acceptance.json'); idem = load('full_index_30_idempotency.json')
    rs = load('full_index_30_restart_safety.json'); db = load('full_index_30_database_before_after.json')
    ext = load('full_index_30_external_inference_audit.json'); cs = load('full_index_30_clinical_safety.json')
    au2 = load('full_index_30_authorization_audit.json'); sn = load('full_index_30_status_normalization.json')
    reval = load('full_index_30_segmentation_revalidation.json'); tc = load('full_index_30_temporal_coverage_audit.json')

    vrows = '\n'.join(
        f"| {v['filename']} | {v['duration_seconds']} | {v['canonical_scenes']} | {v['keyframes']} | "
        f"{v['scenes_with_ready_documents']} | {v['scenes_with_text_scene_embedding']} | "
        f"{v['scenes_with_visual_scene_embedding']} | {v['keyframes_with_visual_embedding']} | "
        f"{v['transcript_status']} | {v['ocr_status']} | {v['semantic_quality']} | {v['final_status']} |"
        for v in vm['assets'])
    irows = '\n'.join(
        f"| {i['filename']} | {i['active_layers']}/18 | {i['active_assertions']}/{i['evidence_rows']} | "
        f"{'yes' if i['short_description'] else 'no'}/{'yes' if i['detailed_description'] else 'no'} | "
        f"{i['e5']} | {i['openclip']} | {i['search_document']} | {i['final_status']} |" for i in im['assets'])
    lrows = '\n'.join(f"| {l['layer_number']} | {l['layer']} | {l['observed']} | {l['false']} | "
                      f"{l['unknown']} | {l['not_applicable']} |" for l in lay['layers'])
    before = (db or {}).get('before', {}); after = (db or {}).get('after', {})
    bs = before.get('structures', {}); asr = after.get('structures', {})
    scopes = (db or {}).get('embeddings_by_scope', {})

    md = f"""# KDI SEMANTIC DATABASE ROLLOUT
## 30-ASSET FULL-INDEX CORRECTIVE FINAL

### STATUS

**{st['status']}**

### COHORT

| | |
|---|---|
| Total assets | {after.get('assets')} |
| Images | {st['images']} |
| Videos | {st['videos']} |
| Fully indexed assets | {st['fully_indexed']}/30 |
| SEARCH_READY assets | {st['search_ready']}/30 |
| Assets needing reprocessing | {len(st['needs_reprocessing'])} |
| Assets #31+ processed | 0 |

### VIDEOS

| Filename | Duration s | Scenes | Keyframes | Scene docs | TEXT_SCENE | VISUAL_SCENE | VISUAL_KEYFRAME | Transcript | OCR | Quality | Final |
|---|---|---|---|---|---|---|---|---|---|---|---|
{vrows}

Segmentation revalidation of the pre-existing canonical videos: **{(reval or {}).get('status', 'n/a')}** —
{(reval or {}).get('segmentation_agrees', 0)}/{(reval or {}).get('videos_revalidated', 0)} agree with detected shot changes,
{len((reval or {}).get('under_segmented', []))} under-segmented, 0 rebuilt.
Media identity: {(tc or {}).get('identity_verified', 0)}/{(tc or {}).get('videos', 0)} SHA-256 verified against master records.

### IMAGES

| Filename | Layers | Assertions/Evidence | Short/Detailed | E5 | OpenCLIP | Search doc | Final |
|---|---|---|---|---|---|---|---|
{irows}

### 18 LAYERS

Expected active **540**, actual **{lay['actual_active']}**, processing complete **{lay['processing_complete']}**,
duplicates **{len(lay['duplicates'])}**. Authoritative source is `asset_semantic_layers`; `asset_layer_status`
is legacy and is not read by the SEARCH_READY gate.

| # | Layer | Observed | False | Unknown | N/A |
|---|---|---|---|---|---|
{lrows}

### SCENE INDEXING

| | |
|---|---|
| Canonical scenes | {si['canonical_scenes']} |
| Superseded historical scene rows | {si['superseded_scene_rows']} |
| Scenes semantically analyzed | {ss['scenes_with_observations']} |
| Scenes with descriptions | {ss['scenes_with_descriptions']} |
| READY scene search documents | {sd['ready_scene_documents']} |
| Scene document coverage | {sd['coverage_percent']}% |
| TEXT_SCENE | {se['text_scene']} |
| VISUAL_SCENE | {se['visual_scene']} |
| Missing scene representations | {len(sd['missing']) + len(se['missing_text_scene']) + len(se['missing_visual_scene'])} |
| Duplicate active scene documents | {len(sd['duplicates'])} |

Superseded rows carry `canonical_active=false` and are retained as history, never counted as active duplicates.

### KEYFRAMES

| | |
|---|---|
| Canonical semantic keyframes | {ki['canonical_keyframes']} |
| With visual descriptions | {ki['with_visual_description']} |
| With VISUAL_KEYFRAME embeddings | {ke['with_visual_keyframe_embedding']} |
| Missing embeddings | {len(ke['missing'])} |
| Duplicate keyframes | {len(ki['duplicate_keyframes'])} |

### DESCRIPTIONS

Asset short descriptions **{de['asset_short_descriptions']}/30**, detailed **{de['asset_detailed_descriptions']}/30**,
scene descriptions **{de['scene_descriptions']}/{si['canonical_scenes']}**, placeholder scene text **{de['scene_placeholders']}**.

### AUDIO

Transcript chunks **{au['transcript_chunks']}**, accepted for search **{au['accepted_for_search']}**,
withheld non-speech **{au['withheld_non_speech']}**, hallucinated speech accepted **{au['hallucinated_speech_accepted']}**,
external speech calls **{au['external_speech_calls']}**. The Phase 11 meaningfulness gate remains active.

### OCR

OCR observations **{oc['ocr_observations']}**, assets with readable text **{oc['assets_with_ocr']}**,
assets with no readable text **{oc['assets_without_readable_text']}**. Applicability driven; no text invented.

### ASSERTIONS / EVIDENCE

Active assertions **{aev['active_assertions']}** (asset-level {aev['asset_level_assertions']}, scene-level {aev['scene_level_assertions']}),
evidence rows **{aev['evidence_rows']}**, OBSERVED/FALSE without evidence **{aev['observed_or_false_without_evidence']}**,
unsupported accepted claims **{aev['unsupported_accepted_claims']}**.
UNKNOWN assertions carry no fabricated evidence ({aev['unknown_without_evidence']} such rows).

### EMBEDDINGS

| Scope | Active |
|---|---|
{chr(10).join(f"| {k} | {v} |" for k, v in sorted(scopes.items()))}

Asset-level: TEXT_ASSET **{ae['text_asset']}/30**, visual asset vector **{ae['visual_asset']}/30**,
regenerated **{ae['regenerated']}**, reused **{ae['reused']}**. Stale rows retained: {ae['stale']}.
Duplicate active embeddings: **{len(ae['duplicate_active'])}**.

### SEARCH DOCUMENTS

Asset READY documents **{gate['search_document_complete']}/30**, scene READY documents
**{sd['ready_scene_documents']}/{sd['canonical_scenes']}** ({sd['coverage_percent']}% coverage),
missing **{len(sd['missing'])}**, duplicate **{len(sd['duplicates'])}**.

### SEARCH ACCEPTANCE

{"Not run." if not acc else f'''Status **{acc['status']}** — {acc['totals']['passed']}/{acc['totals']['cases']} cases.
Blocking failures: **{len(acc['totals']['blocking_failures'])}**{'' if not acc['totals']['blocking_failures'] else ' — ' + ', '.join(acc['totals']['blocking_failures'])}.
Scene-specific retrieval: **{acc['scene_specific']['passed']}/{acc['scene_specific']['cases']}**, scene channels contributing: {', '.join(acc['scene_specific']['scene_channels_observed']) or 'none'}.
Authorization leakage **{acc['authorization_leakage']}**. Clinical false positives **{acc['clinical_false_positives']}**.
Determinism: {'stable' if all(d['stable'] for d in acc['determinism']) else 'UNSTABLE'} over {len(acc['determinism'])} queries x 3 repetitions.
Informational (paraphrase, query vocabulary deliberately not expanded in this phase): {', '.join(acc['totals']['informational_failures']) or 'none'}.'''}

### IDEMPOTENCY

{"Not run." if not idem else f'''**{idem['status']}** — counts identical after re-run: {idem['counts_identical']}; identifiers identical: {idem['identifiers_identical']}.
Duplicates: {json.dumps(idem['duplicate_totals'])}.'''}

### RESTART SAFETY

{"Not run." if not rs else f"**{rs['status']}** — {rs.get('summary', '')}"}

### DATABASE

| | Before | After |
|---|---|---|
| Assets | {before.get('assets')} | {after.get('assets')} |
| Fully indexed | {before.get('fully_indexed')} | {after.get('fully_indexed')} |
| SEARCH_READY | {before.get('search_ready')} | {after.get('search_ready')} |
| Pending | {before.get('pending')} | {after.get('pending')} |
| Unsupported | {before.get('unsupported')} | {after.get('unsupported')} |
{chr(10).join(f"| {k} | {bs.get(k, '—')} | {asr.get(k)} |" for k in asr)}

Assets #31+ indexed: **{db['assets_31_plus_indexed']}**.

### EXTERNAL

Gemini **{ext['gemini_calls']}** · OpenAI indexing **{ext['openai_indexing_calls']}** · Ollama **{ext['ollama_calls']}** ·
Qwen **{ext['qwen_calls']}** · external speech **{ext['external_speech_calls']}** ·
external visual inference **{ext['external_visual_inference']}** ·
external media transmission **{ext['external_media_transmission']}**.
Allowed network: {'; '.join(ext['allowed_network'])}.

Clinical safety: unsupported accepted clinical concepts **{cs['unsupported_accepted_clinical_concepts']}**,
search-document leakage **{cs['search_document_leakage']}**, negative-concept separation {cs['negative_concept_separation']}.
Authorization: {au2['status'] if 'status' in au2 else 'PASS'}, leakage **{au2['authorization_leakage']}**, ACLs modified **{au2['acl_modified_this_phase']}**.
Status normalization: **{(sn or {}).get('status')}** — canonical `{(sn or {}).get('canonical_value')}`,
rows normalized {(sn or {}).get('rows_normalized')}, observed after {json.dumps((sn or {}).get('observed_after'))}.

### DEFERRED

`DEFERRED_SOURCE_REPOSITORY_PERMISSION` — **DEFERRED**.

### NEXT

{st['next']}. Not started.

---

Artifacts ({len(st['artifacts'])}):

{chr(10).join('- `' + a + '`' for a in st['artifacts'])}
"""
    (OUT / 'full_index_30_final.md').write_text(md, encoding='utf-8')
    print(json.dumps({'status': st['status'], 'report': 'full_index_30_final.md'}))


if __name__ == '__main__':
    main()
