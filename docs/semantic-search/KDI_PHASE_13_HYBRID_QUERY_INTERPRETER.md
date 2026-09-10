# KDI Semantic Search Phase 13 — Hybrid Query Interpreter

## Scope and outcome

Phase 13 implements a backend-native query-plan compiler. Its only output is an immutable, schema-validated canonical query plan and diagnostics. It has no imports or calls for asset retrieval, vector search, full-text search, candidate generation, authorization filtering, ranking, reranking, result sufficiency, or frontend behavior.

Versions:

- Query parser: `kdi_query_parser_v1`
- Deterministic parser: `kdi_deterministic_query_parser_v1`
- Semantic interpreter: `kdi_semantic_query_interpreter_v1`
- Query schema: `kdi_query_schema_v1`
- Configuration: `kdi_query_parser_config_v1`

The configuration fingerprint is SHA-256 over canonical key-sorted configuration JSON. The query fingerprint is SHA-256 over the final normalized plan, versions, and configuration with the fingerprint slot blanked before hashing.

## Three-layer architecture

### Layer A — deterministic parser

The deterministic layer owns result quantity, media type, explicit extension, dates/years, duration, timestamp, typed numeric occurrences, surface-strength markers, preference markers, sorting, and simple language detection.

Result count is recognized only through approved quantity grammar such as `show 7 videos`, `top 5 results`, or `best 3`. A bare integer cannot become a count. Every numeric occurrence retains its own span and receives an independent type such as age, decade, graft count, sessions, year, duration, timestamp, currency, result count, or unclassified.

Requested count is distinct from the configured default and effective downstream target. Bounds are configured once: minimum 1, default 5, maximum 50. Clamping preserves the requested value and reports `CLAMPED`.

### Layer B — semantic interpreter

`SemanticQueryInterpreter` is provider-neutral. The production implementation is the local `kdi_local_ontology_interpreter` using the versioned English/Malay `kdi_semantic_lexicon_en_ms` ontology matcher. It is network-free, deterministic, privacy-preserving, and was smoke-tested end-to-end.

It proposes only allowlisted semantic fields: positive/negative/unresolved concepts, modalities, transcript/OCR phrases, and preferences. It recognizes canonical roles, appearance, anatomy, treatments, actions, environments, and procedure stages already supported by repository ontology. Typos can remain partial or unresolved without invalidating the plan.

Provider failure never causes silent vendor fallback. The parser returns a schema-valid plan with semantic status `UNAVAILABLE` and preserves the unresolved query.

### Layer C — validator and normalizer

Provider output is untrusted. Unknown fields, including count, media type, versions, fingerprints, validation state, caller identity, and authorization metadata, are rejected and diagnosed. Strong deterministic fields win. Malformed concept arrays are contained in degraded mode and never reach later search stages.

The canonical plan preserves deterministic constraints, positive concepts, negative concepts, surface markers, preferences, modality expectations, and unresolved meaning separately. It deliberately does not decide Phase 15 hard/soft requirement strength.

## Historical bug prevention

The old numeric bug came from treating an integer by position rather than grammar. Phase 13 uses approved quantity patterns plus occurrence spans, so `30-year-old`, `3000 grafts`, `2025`, `6 sessions`, `RM8,888`, `00:30`, and durations cannot become result counts.

The old zero-result failure came from flattening inferred concepts into simultaneous mandatory filters. Phase 13 emits no mandatory-filter set. Structured meaning remains separated by polarity, modality, deterministic provenance, surface strength, and preference for later Phase 15 policy.

## Retrieval-text contract for later phases

- `visual_semantic_query`: concise visual concepts only; excludes quantity, sorting, extensions, and database control language.
- `text_semantic_query`: normalized evidence-grounded semantic and literal meaning for the future multilingual E5 query encoder.
- `full_text_query`: literal OCR/transcript phrases kept separate from ontology concepts.

No vectors are generated and no search is executed in Phase 13.

## Query logging and security

The existing backend-owned `search_queries` JSON columns can store the validated plan and parser metadata, so no migration was needed. Existing grants already deny normal clients direct writes to search queries. A live authenticated-role insertion attempt was denied. Future persistence must occur only after backend parsing through the service path.

## Language and modality

Language values are `ENGLISH`, `MALAY`, `MIXED`, and `UNKNOWN`. Mixed-language input is accepted. Meaning is independent of evidence modality: `VISUAL`, `TRANSCRIPT`, `OCR`, or `ANY`. `M-CURE visible` stays an OCR literal; `doctor says no shaving` stays transcript intent. Neither becomes treatment automatically.

## Phase boundary

Phase 14 benchmarking, candidate retrieval, ranking, reranking, authorization retrieval, result-count compliance, conversational state handling, frontend changes, and human gold remain unstarted or deferred.
