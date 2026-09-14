# Fix 01 — Representative query diagnostic

Query: `male patient around 35 with receding hairline wearing blue shirt`

The exact production parser was executed locally without calling the production API or database writers.

| Requested concept | Parsed? | Actual result |
|---|---:|---|
| MALE | NO | Included inside unresolved phrase `male patient around 35` |
| PATIENT | NO | Same unresolved phrase |
| age around 35 | NO | `35` classified `UNCLASSIFIED`, operator `EXACT`; not a result count and not an age |
| RECEDING_HAIRLINE | NO | Included in unresolved phrase |
| BLUE | NO | Included in unresolved phrase |
| SHIRT | NO | Included in unresolved phrase |

Parser version is `kdi_query_parser_v3_1`. It emitted zero positive/negative concepts, two unresolved phrases, no hard constraints, no strong requirements, no preferences, and no retrieval text. Default result count remained 5, so 35 is not misread as requested count.

The entire sentence is passed to query encoders by the canonical orchestrator, but the deterministic reranker explicitly rejects vector-only candidates when the plan has unresolved terms and has no grounded strong/preference/context requirements (`deterministic-reranker.ts:39-43`). Therefore this exact query should return no eligible semantic result unless a filename literal or READY-browse channel qualifies, neither of which applies here.

Age has no fuzzy range-overlap behavior for this query because it is not recognized as age. BLUE receives no navy/dark-blue/light-blue expansion, and receding hairline receives no canonical/related concept expansion. No SQL AND/all-of filter is produced. There is consequently no missing-attribute elimination here; the earlier failure occurs at interpretation/grounding.

The architecture can award same-scene and same-event coherence, but has no same-person binding requirement. If these concepts were parsed later, it could combine male from Person A with clothing/hair facts from Person B in the same scene. It can also combine facts across scenes at the asset level, with only a coherence bonus rather than a binding invariant.

Problem codes: `QUERY_PARSER_DEFECT`, `AGE_MATCHING_DEFECT`, `ONTOLOGY_GAP`, `PERSON_BINDING_MISSING`, `HARD_FILTER_OVERCONSTRAINT` (vector-only unresolved candidates are made ineligible), and `PRODUCTION_RETRIEVAL_DISCONNECTED` for structured people/appearance tables.
