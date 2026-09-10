# KDI SEMANTIC DATABASE ROLLOUT — PHASE 1 FINAL

STATUS: PASS

## Frozen standard

- Production standard: KDI_SEMANTIC_INDEX_V1
- Semantic spec: semantic_index_v1
- Semantic spec fingerprint: ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c
- Locked extraction spec: kdi_semantic_18_layer_v1 (6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7)
- Ontology: KDI_SEMANTIC_V2
- Evidence schema: phase10_semantic_assertion_evidence_v1
- Search document: kdi_search_document_v1
- Embedding bundle: open_clip:ViT-B-32:laion2b_s34b_b79k|ollama:qwen3-embedding:0.6b:v1
- Pipeline: kdi_automatic_indexing_pipeline_v1
- Reproducible freeze fingerprint: ba43dab744dedfd590e81be5c8ec5ec8ab7c0bda79f8aca16c0b24d198294888

## Layers and semantics

18/18 layers are explicitly frozen from the existing authoritative machine specification. The four semantic states are OBSERVED, FALSE, UNKNOWN, and NOT_APPLICABLE; PENDING_ANALYSIS/NOT_ANALYZED remain operational states and never mean UNKNOWN. Evidence is asset, scene, event, keyframe, transcript, OCR, or human-review scoped, with asset ownership and timestamp validation.

The requested alternate labels “Safety / Consent” and “Evidence & Notes” are governance/evidence concerns represented by separate authorization/consent and evidence/narrative structures; they are not silently substituted for the locked layers 17–18.

## Database and search mapping

Canonical storage is PostgreSQL/Supabase with pgvector. Layer definitions/evaluations use semantic_layer_definitions and asset_semantic_layers; runs/assertions/evidence use semantic_analysis_runs, semantic_assertions, and semantic_assertion_evidence; temporal/audio/OCR/narrative/search/embedding tables are mapped in phase_01_schema_mapping.json. SEARCH_READY requires valid 18-layer completeness, evidence, grounded representations, current lineage, embeddings, and authorization; it does not grant access or consent.

## Live preservation

- Canonical assets: 881
- Completed current V1: 10
- Pending analysis: 870
- Unsupported: 1
- Unexpected SEARCH_READY: 0
- Assets modified by Phase 1: 0
- New facts/descriptions/narratives/search documents/embeddings: 0
- Media-analysis calls: 0; OpenAI calls: 0
- ACL weakened: NO; consent auto-approved: 0
- Original 10 preserved: YES

## Compatibility and drift

Existing 10 completed assets are compatible with the current V1 readiness audit. Drift is documented, not hidden: P1 legacy catalog naming/order mismatch (preserved immutable), P1 historical embedding lineage requires explicit new-run configuration, and P2 non-uniform legacy state/evidence fields. No Phase 1 migration or semantic rewrite was performed.

## Artifacts

- phase_01_frozen_semantic_standard.json
- phase_01_schema_mapping.json
- phase_01_drift_report.json
- phase_01_validation_status.json
- config/semantic-search/kdi_semantic_search_spec_v1.json (existing authority)
- config/semantic-search/kdi_semantic_18_layer_v1.json (locked extraction authority)

Phase 2 database baseline may begin read-only after resolving/accepting the documented P1 rollout prerequisites. No Phase 2 processing was started.
