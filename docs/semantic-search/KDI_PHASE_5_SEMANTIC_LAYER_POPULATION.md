# KDI AI Search V3 — Phase 5 Semantic Layer Population

## Status

`PASS` — ten frozen pilot assets have canonical shadow semantic packages containing exactly 18 locked layers each (180 evaluations).

## Controls

- Authority: `semantic_index_v1`, fingerprint `ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c`.
- Analyzer: `kdi_semantic_analyzer_v1`; configuration: `kdi_semantic_analyzer_config_v1`.
- Configuration fingerprint: `65b40e1cddda8d0dd5ed2fb95e5f8bf76edf680cb751707087a6b38ab925a5b0`.
- Ontology: existing `KDI_SEMANTIC_V2`; no ad-hoc ontology concepts were added.
- Output mode: repository shadow artifacts only. Production semantic data, search documents, embeddings, permissions, and migrations were untouched.
- All ten assets had reviewed `external_ai_status=ALLOWED` before derived contact sheets were visually reviewed. View, consent, clinical, marketing, download, and external-AI controls remain separate.
- No face recognition, transcription, OCR, or embedding generation occurred.

## Evidence strategy

The eight videos use Phase 3 full-timeline scene, event, and keyframe evidence. The two images use Phase 4 full-image evidence plus retained regions. Existing Phase 2 structured facts and conflicts were reconciled but legacy search-document claims were not accepted as truth without visual support.

Observed facts carry confidence, provenance, model/provider metadata, human-review status, and resolvable evidence references. All 267 observed facts have evidence; all 44 high-confidence search-critical facts are supported. Low-confidence candidates are represented as `UNKNOWN`, not promoted to semantic truth.

## Semantic outcome

- Identity is complete for all ten assets.
- Global understanding, people/roles, appearance, anatomy, actions, relationships, environment, cinematography, composition, marketing semantics, and provisional narratives are populated conservatively where evidence supports them.
- Exact treatment remains unknown for IMG_1238, IMG_0493, IMG_1148, IMG_1160, and both images. The supported treatment contexts are injectable treatment for IMG_0531 and IMG_3429, and FUE hair-transplant implantation for IMG_2963.
- Images correctly mark Layer 3 and Layer 14 `NOT_APPLICABLE`.
- Video audio/transcript intelligence is `UNKNOWN` and `PENDING_PHASE_6`; no transcript was generated.
- OCR is `UNKNOWN` and `PENDING_PHASE_7` for every asset; unsupported legacy no-text claims were not imported.
- Layer 18 records current representations and remains pending later canonical search-document and embedding regeneration.
- IMG_1238 retains its Phase 3 under-segmentation review flag.

## Conflicts and review

Seven material conflicts remain traceable: the two image action mismatches, four zero-evidence legacy treatment/OCR completion claims, and IMG_1238 possible under-segmentation. The human-review queue contains 22 items: four P0, eight P1, ten P2, and zero P3. No conflict was silently overwritten.

## Validation

Targeted Phase 3–5 validation completed with 13 passing tests. Tests cover exact layer/evaluation counts, locked IDs, states and applicability, confidence, observed/false evidence rules, source fingerprints, non-dangling Phase 3/4 references, later-phase guards, conflict preservation, deterministic repeat output, and forbidden-operation controls.

Before/after production counts are identical and recorded in `reports/semantic-search/phase5/phase5_validation.json`.

Phase 5 stops here. Phase 6 audio intelligence has not started.
