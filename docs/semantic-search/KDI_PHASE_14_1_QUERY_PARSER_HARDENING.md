# KDI Phase 14.1 — Query Parser Hardening

Phase 14.1 upgrades the real runtime interpreter to `kdi_query_parser_v1_1` and preserves the canonical query-plan schema at `kdi_query_schema_v1`.

## Generalized changes

- Context-bound English and Malay written quantities.
- Video/image/file vocabulary including clip, footage, gambar, imej, klip, and rakaman.
- Typed age, graft, duration, and session grammar, including session ordinals.
- English and Malay scoped negation with simultaneous preference markers.
- Media and same-concept polarity conflict diagnostics.
- Unicode NFKC and safe dash/whitespace normalization while retaining original text.
- Conservative token-level edit-distance matching against canonical alias phrases.
- OCR and transcript surface-form separation.
- Malay procedure-stage and mixed-language aliases.

Aliases are parser-critical additions, not the full Phase 16 ontology expansion system. They remain listed in `kdi_query_parser_v1_1.json` for later review.

## Benchmark governance

V1 remains unchanged with logical fingerprint `29557f950a7cffe82cbdb8fe70b71075176da988b4ea0d9e54872678423095d9`. Its blind set was not used for Phase 14.1 tuning.

V2 contains 150 fresh queries with zero v1 overlap and is frozen under fingerprint `57ab86f6b4c46d491c6170f0c17bd6f9d999921ae1c89e1c2e86e0cbcacfae3c`.

V2 validation failed protected thresholds. Consequently, blind final evaluation was not run and no validation-driven repair was performed. Phase 14.1 remains blocked and Phase 15 is not started.
