# Job 7 regression tests

- TypeScript typecheck: PASS
- Dashboard: PASS, 245/245 (243 server + 2 client)
- Python: PASS, 665 tests + 74 subtests
- Focused Job 7: PASS, 10/10 Python plus 5 dashboard tests
- Query parser, ontology mapping, 512d vectors, pgvector, lexical/structured retrieval, scoring, deduplication, threshold, counts, conversations, permissions, injection safety, and V1/V2 regression: PASS
- Production build and staging runtime acceptance: PASS
- Live production: login 200, library 307 protected, health 200, V3 unauthenticated 403, download unauthenticated 401
- Deployment guard sentinel regression: PASS

The first guarded switch detected a verifier defect involving the intentional `childPid=0` startup sentinel and attempted rollback; the established rollback restored production. The verifier was corrected and regression-tested, the full candidate gate reran, and the second atomic switch passed with the previous release retained.

