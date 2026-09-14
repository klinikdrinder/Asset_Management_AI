# KDI 877-cohort complex query test

Query: `male patient around 35 with receding hairline wearing blue shirt`

The exact current parser was executed locally. The production HTTP endpoint was not invoked because it performs INSERT/UPDATE telemetry operations, which are forbidden in this audit.

| Check | Result |
|---|---|
| Male recognized | NO |
| Patient recognized | NO |
| 35 recognized as age | NO |
| 35 incorrectly recognized as result count | NO |
| Approximate age matching | NO |
| Receding hairline recognized | NO |
| Blue recognized | NO |
| Shirt recognized | NO |
| Same-person requirement | NO |
| Same-scene requirement | NO (bonus only) |
| Color synonym matching | NO for this unresolved phrase |
| Hairline ontology matching | NO for this unresolved phrase |
| Full sentence reaches encoders | YES |
| Text/visual vectors can retrieve candidates | YES, initially |
| Vector-only unresolved candidates remain eligible | NO |

Parser `kdi_query_parser_v3_1` emits two unresolved phrases, zero positive concepts, zero hard constraints, zero strong requirements, and an UNCLASSIFIED exact numeric occurrence for 35. The default result count remains 5.

The deterministic reranker rejects vector-only candidates when unresolved requirements exist without grounded strong/preference/context requirements. Therefore this query is expected to yield no eligible result. A read-only Top-10 result inspection is not available because there are no eligible results and invoking the current API would write search telemetry.

Even if parsing succeeded, no same-person invariant exists. Same-scene and same-event are scoring bonuses, so attributes could be combined across people or scenes.

Overall: **FAIL**. Primary codes: `QUERY_PARSER_DEFECT`, `AGE_MATCHING_DEFECT`, `ONTOLOGY_GAP`, `PERSON_BINDING_MISSING`, `PRODUCTION_RETRIEVAL_DISCONNECTED`.
