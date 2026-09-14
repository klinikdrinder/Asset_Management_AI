# Job 7 conversational search

`POST /api/search/v3` implements authenticated, same-origin V3 invocation. It records scoped sessions, queries, returned asset IDs, scores, filters, ranking version, and timing. Session reads and updates are explicitly constrained by the authenticated `user_id`, with database RLS retained.

New searches, deterministic refinements, requested counts, and next-page exclusions are supported. No transcript claims are generated because Job 6 produced no transcript rows.

