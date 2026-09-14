# KDI 18-LAYER SEMANTIC STANDARD V1 — FINAL LOCK REPORT

STATUS: PASS

SPEC VERSION: `kdi_semantic_18_layer_v1`  
SPEC FINGERPRINT: `6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7`  
SUPABASE PROJECT: `wcqqjpndlwsvatjuqnol`

## Layer definitions

LAYER DEFINITIONS: 18/18  
Descriptions populated: 18/18  
Applicability rules: 18/18  
Extraction definitions: 18/18  
Completeness definitions: 18/18  
Search rules: 18/18  
Prohibited inference rules: 18/18

## Global rules

UNKNOWN != FALSE: PASS  
NOT_APPLICABLE behavior: PASS  
No-audio fallback: PASS  
No-text fallback: PASS  
Unreadable-text fallback: PASS  
Blurry-media fallback: PASS  
Multimodal indexing fallback: PASS  
No-single-primary-field rule: PASS  
Canonical search-document assembly: PASS

## Immutability

Locked: YES  
UPDATE protection: PASS — transactional harmless update rejected with SQLSTATE 55000.  
DELETE protection: PASS — transactional delete rejected with SQLSTATE 55000.  
Future versioning supported: YES — new versions use `semantic_specifications` and `semantic_layer_definition_versions`; V1 mutation is not required.

## Fingerprint

Repository fingerprint: `6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7`  
Supabase fingerprint: `6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7`  
Recalculated fingerprint: `6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7`  
All match: YES

## Pilot preservation

| Data | Before | After | Content hash unchanged |
|---|---:|---:|---|
| Assets | 881 | 881 | YES |
| Pilot semantic layer rows | 180 | 180 | YES |
| Assertions | 333 | 333 | YES |
| Evidence | 270 | 270 | YES |
| Asset scenes | 312 | 312 | YES |
| Asset events | 22 | 22 | YES |
| Semantic narratives | 37 | 37 | YES |
| Search documents | 55 | 55 | YES |
| Embeddings | 106 | 106 | YES |
| ACL rows | 881 | 881 | YES |

Pilot reprocessed: NO  
Existing completeness statuses changed: 0  
Existing semantic facts changed: 0  
ACL rows changed: 0

RESULT: PASS

## Files changed

- `config/semantic-search/kdi_semantic_18_layer_v1.json`
- `docs/semantic-search/KDI_LOCKED_18_LAYER_SEMANTIC_STANDARD_V1.md`
- `reports/semantic-search/spec/KDI_SEMANTIC_18_LAYER_V1_LOCK_REPORT.md`
- `scripts/semantic-search/build_locked_semantic_spec_migration.py`
- `src/kdi_media/semantic_specification.py`
- `src/kdi_media/semantic_worker.py`
- `supabase/migrations/20260828011044_lock_kdi_semantic_18_layer_v1.sql`
- `tests/test_locked_semantic_specification.py`

## Migration

Exact migration filename: `20260828011044_lock_kdi_semantic_18_layer_v1.sql`  
Migration applied: YES

SECRETS EXPOSED: 0

## Final decision

18-LAYER SPEC STORED: YES  
18-LAYER SPEC LOCKED: YES  
SAFE FOR FUTURE INDEXERS TO REFERENCE: YES  
REMAINING BLOCKERS: NONE

The live worker previously used the hard-coded older identifier `semantic_index_v1`. Startup now resolves the canonical V1 row and fails closed unless both `kdi_semantic_18_layer_v1` and its exact fingerprint match before any queue claim or analysis begins. No analysis was started by this task.
