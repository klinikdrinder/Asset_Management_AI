# KDI AI Search V3 — Phase 8 Evidence-Grounded Narratives

## Status

Phase 8 is **PASS** in shadow mode. The authority remains `semantic_index_v1` with fingerprint `ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c`.

## Generator

- Generator: `kdi_narrative_generator_v1`
- Configuration: `kdi_narrative_generator_config_v1`
- Configuration fingerprint: `a84a43f5124843e404126e84f32911d0d361df67e60961759a24635fcbaa57ca`
- Method: deterministic local evidence templates, temperature 0
- External payload transmission: none
- Template fallback: enabled and used
- Narrative embeddings: pending a later phase

The generator consumes a canonical evidence bundle per asset containing accepted structured facts, Phase 3 scenes/events, accepted Phase 6 transcript evidence, accepted Phase 7 OCR evidence, conflicts, unknowns, and review items. Legacy search-document prose is not authoritative.

## Coverage

- Assets: 10/10
- Asset narratives: 10
- Short semantic summaries: 10
- Search summaries: 10
- Search-safe narratives: 10
- Video scenes represented: 11/11
- Accepted scene narratives: 10
- Review-required unknown scene narratives: 1
- Semantic event narratives: 16/16
- Technical-only events left unlabeled: 6
- Images with fabricated scene/event narratives: 0

IMG_1238.MP4 retains `REVIEW_NEEDED` for possible under-segmentation. It has one conservative scene narrative and six technical-only, non-search-significant event records. No scene split was changed.

## Evidence safety

Thirty-eight claim records were generated. Thirty-seven are accepted factual claims and all thirty-seven have evidence. The remaining claim is the explicitly unknown IMG_1238 scene statement and is not accepted as search truth.

- Evidence coverage for accepted claims: 100%
- Unsupported claims: 0
- Unsupported high-confidence claims: 0
- Visual accepted claims: 36
- OCR accepted claims: 1
- Transcript claims used: 0
- Metadata claims: 0
- Multimodal claims: 0

Three transcript chunks were technically accepted in Phase 6, but they add no necessary reliable narrative fact and were not forced into prose. The repetitive IMG_3429 candidate and every review/excluded transcript remain absent.

The accepted `M-CURE` OCR observation is rendered only as: “Brief visible branding reads M-CURE.” It is not treated as a treatment. Rejected and review-only OCR strings are absent.

## Phase 5 reconciliation

- UNCHANGED: 9
- REFINED: 1 (`IMG_1238.MP4`, adding the explicitly OCR-derived branding sentence)
- CORRECTED: 0
- REJECTED: 0

Phase 5 source files were not modified.

## Search acceptance

Nine search-safe narratives are accepted. IMG_1238 remains review-required because the scene segmentation warning is unresolved, not because its supported visible facts are rejected.

No unknown treatment, anatomy, action, or role was promoted. No exact age, biometric identity, diagnosis, outcome, or marketing claim was introduced.

## Validation and preservation

Thirteen targeted tests pass, including strong evidence retention, unknown-treatment safety, OCR-only and transcript-only modality handling, conflict rejection, conservative unknown scenes, evidence integrity, timestamp integrity, image non-temporal handling, idempotency, and provider fallback.

All production counts remained identical, including 881 assets, 875 visual embeddings, 20 text embeddings, 301 scenes, 301 keyframes, zero production transcript chunks, zero OCR observations, and 16 existing live scene narratives.

No production narrative, semantic, search-document, or embedding rows were written. No migration ran. Phase 9 was not started.
