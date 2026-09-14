# KDI AI Search V3 — Phase 2 Pilot Audit

## Outcome

Phase 2 passed as a read-only audit: 10 frozen pilots × 18 locked layers = 180 evaluations. No media was opened or analyzed, no database write or migration was executed, and no production code was changed.

- Specification: `semantic_index_v1` (`LOCKED`)
- Fingerprint: `ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c`
- Pilot manifest: `kdi_semantic_pilot_v1`
- Composition verified: 8 videos, 2 images

## Layer-to-data-source map

| # | Locked layer | Existing sources | Search-doc only? | Structured? | Versioned? |
|---:|---|---|---|---|---|
| 1 | Asset Identity & Provenance | assets; asset_sources; source_files; asset_destinations; asset_technical_metadata | No | Yes | Unversioned identity records |
| 2 | Global Asset Understanding | asset_ai_profiles; asset_search_documents | Possible | Partial | Partial/legacy |
| 3 | Temporal / Scene Structure | asset_scenes; asset_keyframes; scene_search_documents | No | Partial | Partial/legacy |
| 4 | People & Roles | scene_people; asset_ai_profiles | No | Partial | Partial/legacy |
| 5 | Person Appearance | person_appearances; scene_people; asset_ai_profiles | No | Partial | Partial/legacy |
| 6 | Anatomy | scene_anatomy; anatomy_terms; asset_ai_profiles; search documents | No | Partial | Partial/legacy |
| 7 | Treatment / Procedure | scene_treatments; treatments; asset_ai_profiles; search documents | Possible | Partial | Partial/legacy |
| 8 | Actions & Events | scene_actions; actions; search documents | Possible | Partial | Partial/legacy |
| 9 | Relationships | scene_relationships; relationship_types; search documents | No | Partial | Partial/legacy |
| 10 | Clinical Visual Observations | clinical_observations; clinical_observation_definitions; search documents | Possible | Partial | Partial/legacy |
| 11 | Environment | scene_environment; locations; asset_ai_profiles; search documents | No | Partial | Partial/legacy |
| 12 | Cinematography | scene_cinematography; asset_technical_metadata; search documents | No | Partial | Partial/legacy |
| 13 | Composition | scene_composition; person counts; search documents | No | Partial | Partial/legacy |
| 14 | Speech / Transcript / Audio | asset_transcript_chunks; transcript_embeddings; asset_ai_profiles | No | Partial | Partial/legacy |
| 15 | OCR / Visible Text | ocr_observations; search documents | Possible | Partial | Partial/legacy |
| 16 | Marketing & Content Usage | marketing_annotations; asset_access_control; asset_ai_profiles | No | Partial | Partial/legacy |
| 17 | Semantic Narrative | scene_narratives; asset_ai_profiles; asset/scene search documents | Possible | Partial | Partial/legacy |
| 18 | Search & Embeddings | asset/scene search documents; visual/text/scene/keyframe/transcript embeddings | No | Partial | Partial/legacy |

## Cross-pilot matrix

Legend: C complete; P partial; M missing; N/A not applicable; S search-doc only; L legacy-only; X conflict; U unverified.

| Layer | IMG_0531.MP4 | IMG_1238.MP4 | IMG_3429.MP4 | IMG_9871.MOV | DSC03753.JPG | DSC08097.JPG | IMG_0493.MP4 | IMG_1148.MP4 | IMG_2963.MP4 | IMG_1160.MP4 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 Asset Identity & Provenance | C | C | C | C | C | C | C | C | C | C |
| 2 Global Asset Understanding | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U |
| 3 Temporal / Scene Structure | P+U | P+U | P+U | P+U | N/A+L | N/A+L | P+U | P+U | P+U | P+U |
| 4 People & Roles | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U |
| 5 Person Appearance | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U |
| 6 Anatomy | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U |
| 7 Treatment / Procedure | M | M | M | M | S+U+X | S+U+X | M | M | P+U | M |
| 8 Actions & Events | P+U | P+U | P+U | S+U | P+U+X | P+U+X | P+U | P+U | P+U | P+U |
| 9 Relationships | P+U | P+U | P+U | M | M | M | P+U | P+U | P+U | P+U |
| 10 Clinical Visual Observations | M | M | M | M | P+U | S+U | M | M | M | M |
| 11 Environment | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U |
| 12 Cinematography | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U |
| 13 Composition | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U |
| 14 Speech / Transcript / Audio | M | M | M | M | N/A | N/A | M | M | M | M |
| 15 OCR / Visible Text | M | M | M | M | S+U+X | S+U+X | M | M | M | M |
| 16 Marketing & Content Usage | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U |
| 17 Semantic Narrative | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U |
| 18 Search & Embeddings | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U | P+U |

## Per-asset gap analysis

### IMG_0531.MP4

Asset ID: `7f72217d-3839-4920-86b4-ccc33e9e3d95`; media: video.

- COMPLETE: 1
- PARTIAL: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- MISSING: 7, 10, 14, 15
- NOT_APPLICABLE: none
- SEARCH_DOC_ONLY: none
- LEGACY_ONLY: none
- CONFLICT: none
- UNVERIFIED: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.
- Overall readiness: LOW
- Major future work: COMPLETE, REBUILD, RETAIN_AND_VERIFY

### IMG_1238.MP4

Asset ID: `babae120-9372-42ad-b535-02a3276ea2be`; media: video.

- COMPLETE: 1
- PARTIAL: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- MISSING: 7, 10, 14, 15
- NOT_APPLICABLE: none
- SEARCH_DOC_ONLY: none
- LEGACY_ONLY: none
- CONFLICT: none
- UNVERIFIED: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.
- Overall readiness: LOW
- Major future work: COMPLETE, REBUILD, RETAIN_AND_VERIFY

### IMG_3429.MP4

Asset ID: `c86344e9-5b32-4d86-9205-67952d508651`; media: video.

- COMPLETE: 1
- PARTIAL: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- MISSING: 7, 10, 14, 15
- NOT_APPLICABLE: none
- SEARCH_DOC_ONLY: none
- LEGACY_ONLY: none
- CONFLICT: none
- UNVERIFIED: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.
- Overall readiness: LOW
- Major future work: COMPLETE, REBUILD, RETAIN_AND_VERIFY

### IMG_9871.MOV

Asset ID: `444da390-0117-4380-8c87-d7c32f2903ff`; media: video.

- COMPLETE: 1
- PARTIAL: 2, 3, 4, 5, 6, 11, 12, 13, 16, 17, 18
- MISSING: 7, 9, 10, 14, 15
- NOT_APPLICABLE: none
- SEARCH_DOC_ONLY: 8
- LEGACY_ONLY: none
- CONFLICT: none
- UNVERIFIED: 2, 3, 4, 5, 6, 8, 11, 12, 13, 16, 17, 18
- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.
- Overall readiness: LOW
- Major future work: COMPLETE, NORMALIZE, REBUILD, RETAIN_AND_VERIFY

### DSC03753.JPG

Asset ID: `37838d30-a0ce-4f90-8cc3-c986db0aaa65`; media: image.

- COMPLETE: 1
- PARTIAL: 2, 4, 5, 6, 8, 10, 11, 12, 13, 16, 17, 18
- MISSING: 9
- NOT_APPLICABLE: 3, 14
- SEARCH_DOC_ONLY: 7, 15
- LEGACY_ONLY: 3
- CONFLICT: 7, 8, 15
- UNVERIFIED: 2, 4, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18
- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.
- Overall readiness: PARTIAL
- Major future work: COMPLETE, NORMALIZE, RETAIN_AND_VERIFY

### DSC08097.JPG

Asset ID: `6215ad8b-12be-4a8e-bc49-f6b3dcf55c21`; media: image.

- COMPLETE: 1
- PARTIAL: 2, 4, 5, 6, 8, 11, 12, 13, 16, 17, 18
- MISSING: 9
- NOT_APPLICABLE: 3, 14
- SEARCH_DOC_ONLY: 7, 10, 15
- LEGACY_ONLY: 3
- CONFLICT: 7, 8, 15
- UNVERIFIED: 2, 4, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18
- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.
- Overall readiness: PARTIAL
- Major future work: COMPLETE, NORMALIZE, RETAIN_AND_VERIFY

### IMG_0493.MP4

Asset ID: `64712c6a-c02c-46e9-9f73-16786109468b`; media: video.

- COMPLETE: 1
- PARTIAL: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- MISSING: 7, 10, 14, 15
- NOT_APPLICABLE: none
- SEARCH_DOC_ONLY: none
- LEGACY_ONLY: none
- CONFLICT: none
- UNVERIFIED: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.
- Overall readiness: LOW
- Major future work: COMPLETE, REBUILD, RETAIN_AND_VERIFY

### IMG_1148.MP4

Asset ID: `47611c6d-7923-42a4-87b6-c2a416a90f5c`; media: video.

- COMPLETE: 1
- PARTIAL: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- MISSING: 7, 10, 14, 15
- NOT_APPLICABLE: none
- SEARCH_DOC_ONLY: none
- LEGACY_ONLY: none
- CONFLICT: none
- UNVERIFIED: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.
- Overall readiness: LOW
- Major future work: COMPLETE, REBUILD, RETAIN_AND_VERIFY

### IMG_2963.MP4

Asset ID: `bfae6c51-5d71-47ae-a3e1-6d07092b8896`; media: video.

- COMPLETE: 1
- PARTIAL: 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 16, 17, 18
- MISSING: 10, 14, 15
- NOT_APPLICABLE: none
- SEARCH_DOC_ONLY: none
- LEGACY_ONLY: none
- CONFLICT: none
- UNVERIFIED: 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 16, 17, 18
- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.
- Overall readiness: LOW
- Major future work: COMPLETE, REBUILD, RETAIN_AND_VERIFY

### IMG_1160.MP4

Asset ID: `753eb5f3-82c7-4148-a226-d5b960fd8619`; media: video.

- COMPLETE: 1
- PARTIAL: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- MISSING: 7, 10, 14, 15
- NOT_APPLICABLE: none
- SEARCH_DOC_ONLY: none
- LEGACY_ONLY: none
- CONFLICT: none
- UNVERIFIED: 2, 3, 4, 5, 6, 8, 9, 11, 12, 13, 16, 17, 18
- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.
- Overall readiness: LOW
- Major future work: COMPLETE, REBUILD, RETAIN_AND_VERIFY

## Layer completeness summary

- Layer 1 — Asset Identity & Provenance: complete 10; partial 0; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 0.
- Layer 2 — Global Asset Understanding: complete 0; partial 10; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 10.
- Layer 3 — Temporal / Scene Structure: complete 0; partial 8; missing 0; N/A 2; legacy only 2; search-doc only 0; conflict 0; unverified 8.
- Layer 4 — People & Roles: complete 0; partial 10; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 10.
- Layer 5 — Person Appearance: complete 0; partial 10; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 10.
- Layer 6 — Anatomy: complete 0; partial 10; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 10.
- Layer 7 — Treatment / Procedure: complete 0; partial 1; missing 7; N/A 0; legacy only 0; search-doc only 2; conflict 2; unverified 3.
- Layer 8 — Actions & Events: complete 0; partial 9; missing 0; N/A 0; legacy only 0; search-doc only 1; conflict 2; unverified 10.
- Layer 9 — Relationships: complete 0; partial 7; missing 3; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 7.
- Layer 10 — Clinical Visual Observations: complete 0; partial 1; missing 8; N/A 0; legacy only 0; search-doc only 1; conflict 0; unverified 2.
- Layer 11 — Environment: complete 0; partial 10; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 10.
- Layer 12 — Cinematography: complete 0; partial 10; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 10.
- Layer 13 — Composition: complete 0; partial 10; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 10.
- Layer 14 — Speech / Transcript / Audio: complete 0; partial 0; missing 8; N/A 2; legacy only 0; search-doc only 0; conflict 0; unverified 0.
- Layer 15 — OCR / Visible Text: complete 0; partial 0; missing 8; N/A 0; legacy only 0; search-doc only 2; conflict 2; unverified 2.
- Layer 16 — Marketing & Content Usage: complete 0; partial 10; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 10.
- Layer 17 — Semantic Narrative: complete 0; partial 10; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 10.
- Layer 18 — Search & Embeddings: complete 0; partial 10; missing 0; N/A 0; legacy only 0; search-doc only 0; conflict 0; unverified 10.

## Search and temporal coverage

Per pilot: visual embeddings 1; text embeddings 0; asset search documents 1; scene search documents 1; scene embeddings 1; keyframe embeddings 1; transcript embeddings 0; OCR embeddings 0.

Totals across pilots: visual 10; text 0; asset documents 10; scene documents 10; scene embeddings 10; keyframe embeddings 10; transcript embeddings 0; OCR embeddings 0.

All 8 videos have one real linked scene with valid timestamps, one keyframe, one scene document, one scene embedding, and action rows in 7/8 videos. These are whole-asset summaries, not full-timeline segmentation or separately timed event coverage.

Transcript coverage is zero for text, chunks, timestamps, speakers, scene links, and embeddings. OCR observation coverage is zero for both images and all videos; the two image search documents alone claim that no text is visible.

## Structured vs search-document coverage

Anatomy, actions, roles, environment, cinematography, composition, marketing and narratives generally occur in both structured rows and search documents. Structured facts not fully exposed include detailed appearance attributes and the twelve DSC03753 clinical observations. Search-document-only coverage includes image negative treatment/OCR claims and IMG_9871 turning/self-view action language. The two rich image documents have empty top-level action arrays while nested rich actions and structured action rows are populated.

## Version and provenance

Analysis runs identify provider/model/model version, `kdi-ai-search-v3-job6-v1`, and ontology `job2-v1`. Embeddings identify provider/model/version/dimensions and fingerprints. Normalized semantic rows usually have confidence, provenance, and run IDs; image Job 9 backfill rows often lack run IDs. None is indexed under `semantic_index_v1`. Evidence references and human-review fields are inconsistent; semantic human review is absent.

## Legacy findings

All assets have 18 `asset_layer_status` rows using legacy `KDI_SEMANTIC_V2` layer codes. Those rows are not authoritative for this audit. The two images use `kdi-rich-semantic-v2` documents and Job 9 backfilled zero-duration scene/keyframe representations; their legacy OCR and treatment layers can be marked COMPLETE with evidence_count=0. Video documents remain `job6-v1`. No profile, document, assertion, or embedding is labeled `semantic_index_v1`.

## Conflicts

- DSC03753.JPG: SEARCH_DOCUMENT_INTERNAL_ACTION_MISMATCH — [] versus ['POSING_FOR_CAMERA']. Future action: NORMALIZE and rebuild the search document from canonical structured facts.
- DSC08097.JPG: SEARCH_DOCUMENT_INTERNAL_ACTION_MISMATCH — [] versus ['POSING_FOR_CAMERA', 'LOOKING_AT_CAMERA']. Future action: NORMALIZE and rebuild the search document from canonical structured facts.
- DSC03753.JPG: LEGACY_COMPLETENESS_WITH_ZERO_EVIDENCE — TREATMENT=COMPLETE and OCR=COMPLETE with evidence_count=0 versus SEARCH_DOC_ONLY; no structured treatment/OCR assertion. Future action: Do not trust legacy completeness; normalize explicit FALSE/UNKNOWN states.
- DSC08097.JPG: LEGACY_COMPLETENESS_WITH_ZERO_EVIDENCE — TREATMENT=COMPLETE and OCR=COMPLETE with evidence_count=0 versus SEARCH_DOC_ONLY; no structured treatment/OCR assertion. Future action: Do not trust legacy completeness; normalize explicit FALSE/UNKNOWN states.

## Retain/rebuild plan

- RETAIN: 10
- RETAIN_AND_VERIFY: 118
- NORMALIZE: 6
- COMPLETE: 26
- REBUILD: 16
- REGENERATE_LATER: 0
- NOT_APPLICABLE: 4

Highest-priority later work: full-timeline video segmentation/events; explicit four-state assertions; transcript and OCR determination; evidence/human-review normalization; treatment/clinical normalization; rebuild search documents from canonical facts; regenerate dependent embeddings only after source facts are approved.

## Schema gaps

The live model lacks uniform OBSERVED/FALSE/UNKNOWN/NOT_APPLICABLE state storage, universal evidence references, universal confidence and human-review fields, a dedicated semantic_index_v1 field, separately modeled short events, OCR negative-result assertions, and a clean mapping from the legacy catalog to the locked layers. Phase 2 did not fix these gaps.

## Preservation

All before/after counts and the authorization digest are identical. See `phase2_pilot_layer_audit.json` for the exact baseline. No migrations or production writes occurred.
