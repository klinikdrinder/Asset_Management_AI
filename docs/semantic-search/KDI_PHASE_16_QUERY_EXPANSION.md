# KDI Phase 16 — Query Expansion

Phase 16 adds a deterministic, query-side expansion layer between the immutable Phase 15 requirement plan and future retrieval. It emits a deep-frozen `ExpandedQueryPlan` with canonical, alias, morphology, compositional, hierarchy, cousin, literal, and unresolved representations.

The expansion lexicon is an explicit query overlay. It never writes semantic assertions, evidence, narratives, OCR, transcripts, scenes, events, concepts, or embeddings. Requirement strength and polarity are preserved; hard constraints and exclusions use precision-safe relations only. Response controls, conflicts, literals, and unresolved phrases are not broadened.

Versions: `kdi_query_expander_v1`, `kdi_query_expansion_policy_v1`, `kdi_query_expansion_lexicon_v1`, `kdi_query_expansion_schema_v1`.
