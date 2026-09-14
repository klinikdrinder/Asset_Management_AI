# KDI Phase 15 Requirement Classification

Phase 15 implements `kdi_requirement_classifier_v1`, a deterministic policy consumer of the immutable Phase 14 query plan. It produces a separate, deep-frozen requirement plan with response controls, hard constraints, hard exclusions, strong requirements, preferences, negative preferences, context, unresolved items, and conflicts. Every occurrence retains source spans, polarity, surface markers, reason codes, parser provenance, and classifier provenance.

The policy prevents inferred semantic concepts and requested counts from becoming hard asset filters. Explicit negative preferences remain soft, while explicit exclusions remain hard. Conflicts and unresolved phrases are preserved without silent resolution or ontology fabrication.

The engineering gate passed 3,200 generated cases. The independently authored 180-case benchmark passed DEV 120/120, validation 30/30, blind 30/30, and reproducibility 180/180. Phase 14 parser source and its final benchmark fingerprint remained unchanged. No retrieval, ranking, frontend, ontology-expansion, human-review, semantic-data, or embedding work occurred.
