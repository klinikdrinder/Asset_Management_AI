# KDI Semantic Search — Phase 9 Cross-Layer Consistency

## Status

Phase 9 passes as a validation phase. It does not certify all pilot semantics as conflict-free or ready for indexing. The validator found no P0 source, provenance, temporal, or accepted-claim integrity failure, while preserving five P1 search-critical review items and fourteen P2 incompleteness items.

## Locked inputs

- Semantic specification: `semantic_index_v1`
- Specification fingerprint: `ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c`
- Pilot manifest: `kdi_semantic_pilot_v1`
- Assets validated: 10
- Locked layers represented per asset: 18

All Phase 3–8 source fingerprints, asset identifiers, and filenames agree with the frozen manifest.

## Validator

- Validator: `kdi_semantic_consistency_v1`
- Configuration: `kdi_semantic_consistency_config_v1`
- Configuration fingerprint: `d37307819e322cc0edbea679308e504d79baac738b940e4fc829f45978d76faf`
- Rule evaluations: 200 (20 rules × 10 assets)
- Implementation mode: deterministic, local, shadow-only
- Media analysis, provider calls, migrations, and production writes: none

The validator builds a per-asset graph linking assets, scenes, events, structured facts, accepted narrative claims, and evidence references. It checks identity, canonical layer structure, temporal linkage, people/roles/actions, appearance ownership, action/anatomy, treatment/action/anatomy, clinical observations, relationships, environment, cinematography/composition, global summaries, narratives, transcript, OCR, marketing semantics, and search representation.

## Asset outcomes

| Asset | Result | Material finding |
| --- | --- | --- |
| IMG_0531.MP4 | PASS_WITH_UNCERTAINTY | Canonical search representation remains pending. |
| IMG_1238.MP4 | REVIEW_REQUIRED | Possible under-segmentation remains; treatment context is unknown; search representation is pending. |
| IMG_3429.MP4 | PASS_WITH_UNCERTAINTY | Canonical search representation remains pending. |
| IMG_9871.MOV | PASS_WITH_UNCERTAINTY | Canonical search representation remains pending. |
| DSC03753.JPG | CONFLICT | Legacy action mismatch and unsupported legacy treatment completeness remain unresolved; OCR negative was independently resolved by Phase 7. |
| DSC08097.JPG | CONFLICT | Legacy action mismatch and unsupported legacy treatment completeness remain unresolved; OCR negative was independently resolved by Phase 7. |
| IMG_0493.MP4 | PASS_WITH_UNCERTAINTY | Exact treatment remains unknown; search representation is pending. |
| IMG_1148.MP4 | PASS_WITH_UNCERTAINTY | Exact treatment remains unknown; search representation is pending. |
| IMG_2963.MP4 | PASS_WITH_UNCERTAINTY | Canonical search representation remains pending. |
| IMG_1160.MP4 | PASS_WITH_UNCERTAINTY | Exact treatment remains unknown; search representation is pending. |

## Findings

The current canonical facts are mutually coherent where they are asserted. Injection actions align with lower-face/lip or neck anatomy; graft implantation aligns with scalp/recipient anatomy; cleansing aligns with facial anatomy. Unknown treatment values were not promoted merely to make action and anatomy combinations appear complete.

The two image conflicts are intentionally preserved. Their Phase 7 full-image OCR scans now support `visible_text = FALSE`, resolving only the historical OCR-with-zero-evidence defect. The separate unsupported treatment-completeness claims and search-document action mismatches remain open.

IMG_1238 retains `POSSIBLE_UNDER_SEGMENTATION` and `REVIEW_NEEDED`. Phase 9 validated its references but did not change its one technical scene or six technical event windows.

All ten assets have legacy/current search representations that are not yet reconciled into canonical `semantic_index_v1` search documents and embeddings. This is recorded as P2 incompleteness, not repaired in Phase 9.

## Severity summary

- P0 critical: 0
- P1 search-critical: 5
- P2 important: 14
- P3 low-impact: 0

The five P1 items are the IMG_1238 segmentation review and two legacy conflicts on each pilot image. The fourteen P2 items comprise ten pending canonical search representations and four unknown exact-treatment contexts.

## Production preservation

The before/after SELECT-only counts are identical: 881 assets, 875 visual embeddings, 20 text embeddings, 16 AI profiles, 10 asset search documents, 10 scene search documents, 301 scenes, 301 keyframes, 0 transcript chunks, 0 OCR observations, 16 scene narratives, 881 authorization rows, 2 users, 890 source files, 881 source links, and 881 destinations.

Phase 9 performed no migrations, production writes, media processing, transcript/OCR work, narrative generation, embedding generation, or search-document rebuild.

## Gate interpretation

Phase 9 passes because it produced a complete, deterministic, evidence-linked validation and accurately exposed unresolved conflicts. The pilot set is not ready for production indexing or Phase 10 approval without addressing or formally adjudicating the P1 review items. Phase 10 has not started.
