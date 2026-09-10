# KDI Phase 14.4 — Final Parser and Evaluator Correction

The production parser is version `kdi_query_parser_v1_4`, using query schema `kdi_query_schema_v1_1`. The schema increment records all explicit requested-count occurrences and leaves incompatible multiple counts unresolved with `COUNT_CONFLICT`.

The benchmark evaluator is independently versioned as `kdi_query_parser_evaluator_v2`. It treats the canonical query plan as authoritative, normalizes structured year/timestamp/duration objects, and defines false result count only as promotion of a non-result numeric occurrence.

V5 is a frozen English-only 150-case benchmark. DEV passed 90/90. Validation passed 29/30 but failed the protected exclusion query “Leave any syringe scenes out”; BLIND was therefore not run. No parser, evaluator, configuration, or benchmark changes followed validation. Phase 14.4 is BLOCKED.

No retrieval, ranking, frontend, Phase 15, or human-review work occurred.
