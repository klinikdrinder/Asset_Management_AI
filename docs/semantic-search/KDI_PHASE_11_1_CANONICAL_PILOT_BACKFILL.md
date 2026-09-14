# KDI Semantic Search Phase 11.1 — Canonical Pilot Backfill

## Outcome

Phase 11.1 imported the versioned Phase 3–9 intelligence for the exact ten frozen pilots into the Phase 10 canonical semantic database and rebuilt the normalized Phase 11 search documents. The live acceptance gate passed.

No media analysis, external AI inference, embeddings, frontend work, human decisions, or gold records were created. Imported intelligence remains AI-unreviewed or review-required.

## Source and lineage

- Contract: `semantic_index_v1`
- Ontology: `KDI_SEMANTIC_V2`
- Fingerprints: 60/60 artifact-to-live checks passed across ten pilots
- Import manifest: 711 mapped records
- Phase 5 facts reconciled: 323 total — 267 imported OBSERVED facts and 56 preserved UNKNOWN facts
- Analysis lineage: 58 phase-specific runs; processor/configuration/source fingerprints retained

The import is deterministic and idempotent. Two consecutive 1,271-statement import passes produced no row-count changes. Legacy scenes, keyframes, search documents, profiles, and embeddings remain preserved.

## Canonical result

- Layer states: 180/180
- Effective assertions: 313 (268 OBSERVED, 2 FALSE, 43 UNKNOWN)
- Search-critical OBSERVED/FALSE assertions: 172/172 evidence-backed
- Canonical scenes: 11
- Event windows: 22 (16 semantic, 6 technical-only/review-required)
- Canonical keyframes: 44
- Transcript chunks: 14 (3 search-eligible, 11 excluded/review)
- OCR observations: 19 (1 accepted, 3 review, 15 rejected)
- Narratives: 10 asset, 11 scene, 16 event
- Claims: 38 (37 accepted with evidence, 1 review-required)

IMG_1238 remains one scene with possible under-segmentation and review-required status. Its treatment is UNKNOWN, its six technical windows have no invented semantic labels, and `M-CURE` remains OCR-visible branding only.

DSC03753 and DSC08097 retain NOT_APPLICABLE temporal/audio layers, evidence-backed FALSE OCR state, UNKNOWN treatment, and unresolved Phase 9 action/treatment review issues.

## Search-document rebuild

The existing `kdi_search_document_builder_v1` produced exactly:

- 10 active asset documents
- 11 active canonical scene documents
- 16 active semantic-event documents
- 270 canonical search concepts
- 520 document-level concept/evidence lineage rows

All search-critical document concepts resolve through assertion evidence. Prior provisional documents remain stored and are stale/inactive.

## Security and preservation

RLS policies cover the canonical semantic and normalized search-document tables. A live authorized principal resolved all 37 active documents, an unauthorized principal resolved zero, and the backend/service path resolved all 37.

Protected production counts remained unchanged during the idempotency passes: assets 881, access-control rows 881, asset sources 881, destinations 881, source files 890, visual embeddings 875, legacy embeddings 20, legacy asset documents 10, legacy scene documents 10, application users 2. Semantic embeddings remain zero.

## Artifacts

The complete manifest, layer matrix, reconciliation reports, security report, search rebuild report, summary, and final validation are in `reports/semantic-search/phase11_1/`.

Phase 12 was not started.
