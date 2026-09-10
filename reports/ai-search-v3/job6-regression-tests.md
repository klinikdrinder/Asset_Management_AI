# Job 6 regression tests

- TypeScript typecheck: PASS
- Dashboard tests: PASS — 240/240
- Python tests: PASS — 655 tests plus 74 subtests
- Focused Job 6 tests: PASS — 5/5 (included in Python total)
- Authorization/restricted/non-pilot boundary: PASS
- Scene/keyframe/ontology/structured extraction: PASS
- Visual dimensions and pgvector storage: PASS
- Text embedding/transcript: DEFERRED — no approved working provider
- Search documents and idempotency: PASS (second run added zero rows)
- RLS/function privileges/download security: PASS
- V1/V2 hashes: PASS
- Live health/login/protected library: PASS — 200/200/307

An initial unscoped pytest collection hit the repository's known duplicate utility/test basename. The authoritative repository invocation with `PYTHONPATH=src;repository` and the `tests` target passed fully.
