# KDI 18-LAYER COMPLETENESS ENGINE

## 10-PILOT RE-EVALUATION — FINAL

STATUS: PASS

SPEC VERSION: kdi_semantic_18_layer_v1

SPEC FINGERPRINT: 6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7

SPEC LOCK VERIFIED: YES

PILOT ASSETS: 10/10

EXPECTED LAYER ROWS: 180

EVALUATED: 180/180

Corrected/applied evaluation batch: 5595c9da-cbb5-4395-a13c-9c25887243a2

An earlier immutable validation attempt (c16c6eb6-0eda-4b35-b218-1a17d1987e63) exposed one unlabeled PARTIAL cause before any status update. It was not applied. The corrected batch has zero unlabeled PARTIAL decisions.

## BEFORE

COMPLETE: 17

PARTIAL: 159

NOT_EVALUATED: 0

Legacy completeness value NOT_APPLICABLE: 4

## AFTER

COMPLETE: 149

PARTIAL: 31

NOT_EVALUATED: 0

## PARTIAL ROOT CAUSES

For the 159 formerly PARTIAL rows:

STATUS_BUG: 128

EXTRACTION_GAP: 21

INFRASTRUCTURE_GAP: 10

DATA_QUALITY_LIMITATION: 0

Four additional legacy NOT_APPLICABLE completeness values were normalized to COMPLETE while retaining semantic resolution NOT_APPLICABLE.

## PER-LAYER RESULT

| # | Layer | Complete | Partial | Reason |
|---:|---|---:|---:|---|
| 1 | Asset Identity & Provenance | 10 | 0 | — |
| 2 | Global Asset Understanding | 0 | 10 | Richer master description missing |
| 3 | Temporal / Scene Structure | 9 | 1 | IMG_1238 possible under-segmentation review unresolved |
| 4 | People & Roles | 10 | 0 | — |
| 5 | Person Appearance | 10 | 0 | — |
| 6 | Anatomy | 10 | 0 | — |
| 7 | Treatment / Procedure | 10 | 0 | Seven explicit UNKNOWN results are valid complete evaluations |
| 8 | Actions & Events | 10 | 0 | — |
| 9 | Relationships | 10 | 0 | — |
| 10 | Clinical Visual Observations | 10 | 0 | — |
| 11 | Environment | 10 | 0 | — |
| 12 | Cinematography | 10 | 0 | — |
| 13 | Composition | 10 | 0 | — |
| 14 | Speech / Transcript / Audio | 10 | 0 | Two still-image outcomes are semantically NOT_APPLICABLE |
| 15 | OCR / Visible Text | 10 | 0 | Explicit applicability/frame evaluation persisted |
| 16 | Marketing & Content Usage | 10 | 0 | — |
| 17 | Semantic Narrative | 0 | 10 | Genuine detailed/master description missing |
| 18 | Search & Embeddings | 0 | 10 | Locked V1 version/fingerprint lineage missing |

## STATUS BUG ANALYSIS

Why the previous 16 layers remained PARTIAL:

The phase-5 construction path initializes every layer with completeness PARTIAL (src/kdi_media/semantic_analysis.py line 85). Later phases persisted explicit outcomes and processing completion, but no deterministic post-processing path recomputed completeness from evidence. Therefore 128 of 159 old PARTIAL rows were stale insertion/default bookkeeping. The other 31 have exact gaps below.

Was PARTIAL an insertion/default bookkeeping problem? PARTLY

Evidence:

- All 180 processing statuses were COMPLETE.
- 128 former PARTIAL rows have explicit stored evaluation outcomes satisfying V1.
- Seven treatment UNKNOWN results are complete evaluations, not missing treatment classifications.
- Four semantically NOT_APPLICABLE image/modality rows now have completeness COMPLETE.
- Every remaining PARTIAL has non-empty missing requirements and a failure type.

## SELECTIVE REPROCESSING REQUIRED

For each asset below, remediate only the listed layers:

| Filename | Layer(s) and exact gap |
|---|---|
| DSC03753.JPG | GLOBAL_ASSET_UNDERSTANDING — richer master description (EXTRACTION_GAP); SEMANTIC_NARRATIVE — genuine detailed/master description (EXTRACTION_GAP); SEARCH_EMBEDDINGS — V1 version/fingerprint lineage (INFRASTRUCTURE_GAP) |
| DSC08097.JPG | GLOBAL_ASSET_UNDERSTANDING — richer master description (EXTRACTION_GAP); SEMANTIC_NARRATIVE — genuine detailed/master description (EXTRACTION_GAP); SEARCH_EMBEDDINGS — V1 version/fingerprint lineage (INFRASTRUCTURE_GAP) |
| IMG_0493.MP4 | GLOBAL_ASSET_UNDERSTANDING — richer master description (EXTRACTION_GAP); SEMANTIC_NARRATIVE — genuine detailed/master description (EXTRACTION_GAP); SEARCH_EMBEDDINGS — V1 version/fingerprint lineage (INFRASTRUCTURE_GAP) |
| IMG_0531.MP4 | GLOBAL_ASSET_UNDERSTANDING — richer master description (EXTRACTION_GAP); SEMANTIC_NARRATIVE — genuine detailed/master description (EXTRACTION_GAP); SEARCH_EMBEDDINGS — V1 version/fingerprint lineage (INFRASTRUCTURE_GAP) |
| IMG_1148.MP4 | GLOBAL_ASSET_UNDERSTANDING — richer master description (EXTRACTION_GAP); SEMANTIC_NARRATIVE — genuine detailed/master description (EXTRACTION_GAP); SEARCH_EMBEDDINGS — V1 version/fingerprint lineage (INFRASTRUCTURE_GAP) |
| IMG_1160.MP4 | GLOBAL_ASSET_UNDERSTANDING — richer master description (EXTRACTION_GAP); SEMANTIC_NARRATIVE — genuine detailed/master description (EXTRACTION_GAP); SEARCH_EMBEDDINGS — V1 version/fingerprint lineage (INFRASTRUCTURE_GAP) |
| IMG_1238.MP4 | GLOBAL_ASSET_UNDERSTANDING — richer master description (EXTRACTION_GAP); TEMPORAL_SCENE_STRUCTURE — segmentation-policy review / possible under-segmentation resolution (EXTRACTION_GAP); SEMANTIC_NARRATIVE — genuine detailed/master description (EXTRACTION_GAP); SEARCH_EMBEDDINGS — V1 version/fingerprint lineage (INFRASTRUCTURE_GAP) |
| IMG_2963.MP4 | GLOBAL_ASSET_UNDERSTANDING — richer master description (EXTRACTION_GAP); SEMANTIC_NARRATIVE — genuine detailed/master description (EXTRACTION_GAP); SEARCH_EMBEDDINGS — V1 version/fingerprint lineage (INFRASTRUCTURE_GAP) |
| IMG_3429.MP4 | GLOBAL_ASSET_UNDERSTANDING — richer master description (EXTRACTION_GAP); SEMANTIC_NARRATIVE — genuine detailed/master description (EXTRACTION_GAP); SEARCH_EMBEDDINGS — V1 version/fingerprint lineage (INFRASTRUCTURE_GAP) |
| IMG_9871.MOV | GLOBAL_ASSET_UNDERSTANDING — richer master description (EXTRACTION_GAP); SEMANTIC_NARRATIVE — genuine detailed/master description (EXTRACTION_GAP); SEARCH_EMBEDDINGS — V1 version/fingerprint lineage (INFRASTRUCTURE_GAP) |

Recommended next action: generate only grounded master descriptions/narratives; resolve the existing IMG_1238 segmentation review before any selective re-segmentation; add V1 fingerprint lineage support before rebuilding only the listed search representations.

MEDIA REPROCESSED: 0

SEMANTIC ASSERTIONS CHANGED: 0

SEMANTIC EVIDENCE CHANGED: 0

SEARCH DOCUMENTS CHANGED: 0

EMBEDDINGS CHANGED: 0

ACL CHANGED: 0

TESTS: 27 / 27 passed

DETERMINISM: PASS (dry-run/applied decision fingerprint mismatches: 0)

COMPLETENESS AUDIT PERSISTED: YES (180 corrected dry-run + 180 applied audit rows; transactional UPDATE test rejected)

COMPLETENESS ENGINE: PASS

10-PILOT SEMANTIC COMPLETENESS: BLOCKED

NEXT REQUIRED ACTION: Selective remediation of ONLY the 31 listed asset/layer combinations.

## DATABASE PRESERVATION

Before/after counts and protected hashes matched for all requested semantic, scene, transcript, OCR, narrative, search, embedding, asset, and ACL data. The protected asset_semantic_layers hash (excluding only completeness_status and updated_at) remained c38af60ab9a0f056ad6b37616c751695.

Unchanged counts: assets 10; semantic layers 180; assertions 333; assertion evidence 270; scenes 21; events 22; keyframes 54; transcript chunks 14; OCR observations 19; narratives 37; narrative claims 38; narrative claim evidence 53; search builds 55; search concepts 520; search evidence 520; embeddings 106; ACL rows 10.

## MIGRATION AND ADVISORS

Migration applied: 20260828013125_kdi_semantic_completeness_audit_v1.sql

The audit table has RLS, asset-scoped authenticated SELECT, revoked client writes, and immutable UPDATE/DELETE protection. Supabase advisors reported no new task-specific security error. Existing project-wide advisory debt remains outside this job.

SECRETS EXPOSED: 0
