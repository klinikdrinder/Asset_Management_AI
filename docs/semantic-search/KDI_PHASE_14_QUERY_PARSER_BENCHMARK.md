# KDI Phase 14 — Dedicated Query-Parser Benchmark

Phase 14 freezes and evaluates `kdi_query_parser_benchmark_v1` against the Phase 13 parser. It is parser-only: no asset identifiers, expected media results, retrieval calls, ranking, frontend behavior, or human-gold changes are part of the benchmark.

## Frozen contract

- Benchmark: `kdi_query_parser_benchmark_v1`
- Evaluation: `kdi_query_parser_eval_v1`
- Cases: 150 unique queries
- Splits: DEV 90, VALIDATION 30, BLIND 30
- Parser: `kdi_query_parser_v1`
- Deterministic parser: `kdi_deterministic_query_parser_v1`
- Semantic interpreter: `kdi_semantic_query_interpreter_v1`
- Schema: `kdi_query_schema_v1`
- Configuration fingerprint: `8ee003b3d78168389d7ef653fa78c792e93c7cc140f8bf11db6531c0b4426391`
- Benchmark fingerprint: `29557f950a7cffe82cbdb8fe70b71075176da988b4ea0d9e54872678423095d9`

The JSON benchmark contains explicit parser gold, fields that must not appear, language, category, split, and notes. Gold is independent of the pilot media library.

## Evaluation policy and outcome

Development was diagnostic. The frozen candidate was then evaluated once against validation. Validation failed protected acceptance thresholds, so blind final evaluation was not run and neither parser nor benchmark was modified from blind labels.

Observed validation gaps include written-number result quantities, broader duration/range grammar, Malay/code-switched vocabulary, indirect negation, similarity paraphrases, typo handling, and ontology aliases. These are recorded as parser/provider gaps. No Phase 15 requirement-strength policy or Phase 16 expansion system was implemented.

Provider failure fixtures cover timeout, exception, malformed semantic output, and attempted writes to trusted fields. Each fixture returned a schema-valid deterministic plan without allowing trusted-field replacement.

## Reproduction

From `dashboard`:

```powershell
npx.cmd tsx --test tests\phase14-query-parser-benchmark.test.ts
npx.cmd tsx scripts\phase14-parser-benchmark.ts
```

Do not rerun validation as a tuning loop. Any corrected parser or benchmark requires an explicit later version.
