# KDI Phase 14.3 — Final English Query Parser

The production query interpreter was upgraded to `kdi_query_parser_v1_3`. English is the primary supported language; existing multilingual behavior remains best-effort and is excluded from acceptance metrics.

The generalized correction recognizes prefix and postposed exclusion verbs, intervening universal quantifiers, and the documented injection/syringe visual-action family. It retains clause-scoped polarity, same-concept contradiction detection, conservative phrase-level fuzzy matching, donor safety, and unknown-compound safety.

V4 contains 150 fresh English cases split 90 DEV, 30 VALIDATION, and 30 BLIND. Its fingerprint is `4633c5500f26c2df9709391162f21e460a9edfa2ca1628a8448e4262e88e7ae3`. Validation ran once against the frozen candidate. Negation reached 100%, but nine cases failed other protected gates. Phase 14.3 is therefore BLOCKED and BLIND was not run. No parser, configuration, or benchmark changes followed validation.

The canonical runtime remains `dashboard/app/api/search/v3/route.ts` → `dashboard/db/query-interpreter.ts`. No retrieval, ranking, frontend, Phase 15, Phase 16, or human-review work occurred.
