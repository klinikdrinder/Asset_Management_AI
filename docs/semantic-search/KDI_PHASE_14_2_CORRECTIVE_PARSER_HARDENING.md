# KDI Phase 14.2 — Corrective Parser Hardening

## Outcome

The real AI Search runtime now invokes the canonical v1.2 query interpreter before its legacy retrieval adapter. The corrective parser passed its targeted regression suite, but the frozen V3 validation holdout failed two protected negation cases. Phase 14.2 is therefore **BLOCKED**, and the BLIND split was not run.

No parser or configuration changes were made after validation began.

## Runtime path

`dashboard/app/api/search/v3/route.ts` → `interpretQuery` in `dashboard/db/query-interpreter.ts` → deterministic extraction → local ontology interpretation → normalization/validation → canonical query plan. The existing `interpretV3Query` call remains only as a compatibility adapter for retrieval code and was not exercised by this benchmark.

## Frozen versions

- Query parser: `kdi_query_parser_v1_2`
- Deterministic parser: `kdi_deterministic_query_parser_v1_2`
- Semantic interpreter: `kdi_semantic_query_interpreter_v1_2`
- Schema: `kdi_query_schema_v1`
- Configuration: `kdi_query_parser_config_v1_2`
- Configuration fingerprint: `f33c2e20d09509356632f5738e95ce2a26d2b6a0a78f38572c31224328fa5203`
- Parser source fingerprint: `df19f786ed42a0f7acfb37a6b82bb64f785594e937efbfe260eff39aa25442fb`
- V3 benchmark fingerprint: `d050c25812dbac79063f20e17e48301b2df5a30c6970c74a00deeb405cb1a815`

## Architectural corrections

The parser now creates typed numeric occurrences before populating plan slots, uses a centralized comparison-operator contract with explicit inclusivity, and requires temporal grammar for years. Semantic interpretation uses clauses and chunks, exact aliases before conservative phrase-level typo recovery, occurrence-level polarity, and a single contradiction enum. Arbitrary token-level fuzzy promotion was removed. Unknown compound phrases remain unresolved unless a grammatically independent known chunk exists.

The canonical contradiction types are `MEDIA_TYPE_CONFLICT`, `CONCEPT_POLARITY_CONFLICT`, `COUNT_CONFLICT`, and `EXTENSION_MEDIA_CONFLICT`.

## Acceptance protocol

V3 contains 150 frozen queries: DEV 90, VALIDATION 30, and BLIND 30. The repository exposes the expected labels, so the final sets are accurately described as frozen holdouts rather than cryptographically blind. Validation ran once against the frozen parser candidate. It failed, so BLIND was not run and no repairs or relabeling followed.

Validation failures:

1. `QP14V3-044`, “Leave out every syringe”: `INJECTING` was not preserved as a negative action.
2. `QP14V3-049`, “doktor tetapi tiada pesakit”: `PATIENT` was emitted positively instead of negatively.

Both are classified as critical `NEGATION` failures. A future correction requires a new parser candidate and a newly independent acceptance set.

## Boundaries

No media retrieval, ranking, reranking, frontend work, Phase 15 work, or human review occurred. Benchmark queries were not persisted to production search history. The local deterministic production provider was smoke-tested separately; external calls and cost were zero.
