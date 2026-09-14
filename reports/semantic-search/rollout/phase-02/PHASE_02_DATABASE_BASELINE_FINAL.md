# KDI SEMANTIC DATABASE ROLLOUT — PHASE 2 FINAL

STATUS: PASS

## Frozen specification

- Semantic spec: semantic_index_v1
- Locked 18-layer spec: kdi_semantic_18_layer_v1
- Ontology: KDI_SEMANTIC_V2
- Evidence: phase10_semantic_assertion_evidence_v1
- Search document: kdi_search_document_v1
- Pipeline: kdi_automatic_indexing_pipeline_v1
- Phase 1 freeze fingerprint: ba43dab744dedfd590e81be5c8ec5ec8ab7c0bda79f8aca16c0b24d198294888

## Baseline

- Baseline fingerprint: 22ef81db0394b3f0efb4164b741017faad248cedccee92bb30a5118528623faa
- Canonical assets / unique IDs / unique hashes: 881 / 881 / 881
- Images / videos / documents / unsupported: 293 / 585 / 2 / 1
- Semantic complete / pending / SEARCH_READY: 10 / 870 / 10
- Unexpected SEARCH_READY: 0

## Semantic and search data

Read-only counts are recorded in phase_02_semantic_counts.json. Key counts: profiles 16, semantic layers 180, assertions 333, evidence 270, scenes 312, keyframes 345, events 22, narratives 37, narrative claims 38, asset search documents 10, scene search documents 10, analysis runs 58, ACL rows 881. No writes occurred.

Embeddings: OpenCLIP ViT-B-32 / laion2b_s34b_b79k at 512 dimensions (875 visual rows), multilingual-e5-small at 384 dimensions (41 canonical pilot text rows), and 20 historical 1024-dimensional Ollama text rows. Pending visual embedding coverage is 865 with / 5 without. This is the reconfirmed P1 lineage ambiguity; vectors were not regenerated.

## Completed ten-asset audit

10/10 audited and compatible with the frozen contract/readiness baseline. Invalid COMPLETE: 0. Invalid SEARCH_READY: 0. Per-asset matrix is in phase_02_completed_10_audit.json.

## Integrity and safety

Missing hashes: 0. Missing provenance: 0. Duplicate canonical assets/hashes: 0. Orphan semantic/search/embedding rows: 0 in the available read-only audits. ACL coverage: 881/881; no ACL weakening. Consent auto-approvals: 0. Pending assets remain operationally pending and are not UNKNOWN or COMPLETE.

OpenAI calls: 0. Media-analysis calls: 0. New semantic facts, evidence, descriptions, narratives, search documents, embeddings, and SEARCH_READY assets: 0. Production database mutations: 0.

## Drift reconfirmation

P0: 0. P1: 2. P2: 1. P3: 0. P1-A is the legacy semantic-layer catalog mismatch; P1-B is mixed historical embedding lineage. Both are measured and deferred without mutation. P2 is non-uniform legacy state/evidence fields.

## Artifacts

- PHASE_02_DATABASE_BASELINE_FINAL.md
- phase_02_database_baseline.json
- phase_02_asset_inventory.json
- phase_02_semantic_counts.json
- phase_02_completed_10_audit.json
- phase_02_search_document_audit.json
- phase_02_embedding_audit.json
- phase_02_provenance_audit.json
- phase_02_acl_consent_audit.json
- phase_02_orphan_duplicate_audit.json
- phase_02_drift_reconfirmation.json
- phase_02_validation_status.json

Next phase: safe to begin Phase 3 read-only planning/finalization. Do not begin media indexing automatically.
