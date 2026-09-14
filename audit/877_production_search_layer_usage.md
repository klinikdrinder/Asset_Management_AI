# KDI 877-cohort production search layer usage

Production trace: UI → `app/api/search/route.ts` → `interpretQuery` → requirement classifier → query expander → `executeCanonicalSearch` → `retrieveCandidates` → `match_kdi_semantic_search_embeddings` → `kdi_search_ready_assets_v1` → `phase18_authorize_candidates_for` → deterministic reranker → result controller/formatter.

| Layer | Database rows exist | Structured | Production directly/indirectly uses it | Effective support |
|---|---|---|---|---|
| Identity | YES | YES | YES: assets filename/media metadata | STRONG |
| Global | YES | Assertions/docs | YES: docs, assertions, text vectors | PARTIAL |
| Temporal | YES | Scenes/times | PARTIAL: scene IDs and scene vectors | PARTIAL |
| People | YES | Only 10 assets | PARTIAL: assertions/docs; not `scene_people` | WEAK |
| Appearance | YES | Only 10 assets | PARTIAL: assertions/docs; not `person_appearances` | WEAK |
| Anatomy | YES | Assertions + 22 scene rows | YES through canonical concepts/assertions/docs | PARTIAL |
| Treatment | YES | Very sparse | PARTIAL through concepts/assertions/docs | WEAK |
| Actions | YES | Assertions + 14 scene rows | YES through concepts/assertions/docs | PARTIAL |
| Relationships | YES | 7 scene rows | PARTIAL through assertions; no relationship-table read | WEAK |
| Clinical Visual | YES | Assertions + 12 observations | PARTIAL through assertions/docs; no observation-table read | PARTIAL |
| Environment | YES | Assertions + 10 scene rows | INDIRECT through assertions/docs/vectors | PARTIAL |
| Cinematography | YES | Assertions + 10 scene rows | INDIRECT through assertions/docs/vectors | PARTIAL |
| Composition | YES | Assertions + 10 scene rows | INDIRECT through assertions/docs/vectors | PARTIAL |
| Speech | YES | 98 chunks / 47 assets with text | PARTIAL: explicit literal plus doc/vector derivation | PARTIAL |
| OCR | YES | 1,213 rows / 270 assets | PARTIAL: explicit literal plus doc/vector derivation | PARTIAL |
| Marketing | YES | Sparse | NO effective ranking use | NONE |
| Safety / Consent | YES | ACL 877/877 | YES for authorization; consent remains UNKNOWN | PARTIAL |
| Evidence | YES | Evidence 877/877 | PARTIAL: assertion linkage/confidence, not evidence table | PARTIAL |

Seventeen of 18 domains contribute directly or indirectly to some active production path; Marketing does not provide an effective candidate/ranking channel. “Used” does not mean adequately populated or capable of the requested query.

Source proof: `candidate-retriever.ts:44-63,79-81`; `candidate-authorizer.ts:5`; `deterministic-reranker.ts:30-46`; `canonical-production-retriever.ts:25-52`; `app/api/search/route.ts:19-46`.
