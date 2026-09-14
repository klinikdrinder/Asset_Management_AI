# KDI Phase 14 Final Acceptance

Phase 14 remains **BLOCKED** after the protected V7 validation run. The production parser candidate is `kdi_query_parser_v2`; retrieval, ranking, frontend work, human gold, and Phase 15 remain untouched.

## Gold-quality remediation

`kdi_query_gold_validator_v1` independently checks structural validity, canonical expected shape, and semantic support in the natural-language query. It does not import or call the production parser. Its contract tests reject unsupported media labels, numeric-slot leakage, polarity errors, and OCR/transcript swaps.

The immutable V6 benchmark retained fingerprint `6ad4aed2ad3653eeb8110c5ea0fe7747c25b8cc97cf8f5e2345dc31dab494ce2`. Its 180-record semantic audit found exactly two invalid records: QP14V6-042 and QP14V6-046 expected VIDEO from the generic noun “material”; the canonical expectation is ANY.

V7 contains 180 unique English cases (DEV 120, VALIDATION 30, BLIND 30). All 180 expectations passed structural, canonical-shape, and semantic-gold validation before freeze. DEV passed 120/120.

## Protected validation outcome

Validation passed every deterministic, numeric, temporal, media, extension, negation, contradiction, safety, schema, English, micro, macro, and critical-slot threshold. One semantic case failed: QP14V7-109, “Patient with implantation of grafts, for archive review.” The semantic chunker splits at `of`, preventing the approved phrase `implantation of grafts` from resolving to `IMPLANTING_GRAFTS`. Semantic accuracy was 90.909%, below the protected 95% gate.

The failure is classified as `PARSER_DEFECT / SEMANTIC_CHUNKING`. In accordance with the protected holdout policy, the parser was not changed after validation, blind was not run, and the same holdout was not reused.

## Preservation

The read-only live audit confirmed no semantic-data or embedding changes, zero benchmark queries in production search history, and 106 semantic embeddings before and after.
