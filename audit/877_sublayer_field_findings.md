# KDI 877-cohort sublayer field findings

Detailed counts are in `877_sublayer_field_coverage.csv`.

- Identity is structurally present for 877/877 through canonical asset IDs and filenames.
- Structured People exists for 10/877 assets. Exact apparent age exists for 0; age min/max and gender presentation each exist for 2.
- Structured Appearance exists for 10/877 assets, but individual hair/clothing/posture fields are populated for only 2 assets each in the current rows.
- Structured transcript text/language covers 47 assets; direct production use is limited to explicit transcript-literal queries.
- Structured OCR text covers 270 assets; direct production use is limited to explicit OCR-literal queries.
- ACL classification and internal usage state exist for 877/877 cohort assets. Consent is explicitly `UNKNOWN` for all 877, so consent cannot be called verified.
- Assertion evidence exists for every cohort asset, but the production reranker does not load `semantic_assertion_evidence`; it consumes assertion IDs, concepts, state, confidence and scene/event IDs.
- Free-text/prose-only indicators include at least 27 assets for hair density, 39 for clothing, 8 for facial hair, and 5 for posture beyond their structured-field coverage. These are materialization gaps, not proof that the prose is clinically correct.

The 1,586 rows in `877_materialization_gaps.csv` represent asset-layer gaps and therefore exceed the number of assets; one asset can have multiple gap categories.
