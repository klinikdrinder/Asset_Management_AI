# Job 5 RLS and function security audit

The `assets` SELECT policy now calls the central view function. Asset-derived policies were replaced/created for access control, legacy AI metadata, sources/destinations, scenes/keyframes, all scene intelligence, transcripts/OCR/clinical observations, embeddings, and search documents. Search-history policies bind sessions to `private.current_app_user_id()` and queries/results/feedback to their owning session.

No client write grant or policy was added. Raw access-control, vector, and search-document tables explicitly retain no PUBLIC/anon/authenticated privileges. RLS remains enabled. Transactional tests temporarily granted SELECT only inside a rolled-back transaction to prove both allow and deny paths.

All new functions use empty search paths. SECURITY DEFINER functions exist only in `private`; public API wrappers are SECURITY INVOKER. PUBLIC and anon execute are false. Authenticated may execute only current-caller view/download booleans; external-AI and explicit-user functions are service-only. Security advisors reported no Job 5 findings. Performance advisors report zero relevant uncovered foreign keys after the two-index follow-up.

Legacy `hybrid_search_assets` and `hybrid_search_assets_v2` hashes are unchanged. They were not rewritten to the Job 5 permission model. They must not be reused as the future V3 permission boundary; Job 7 must use the permission-first set relation.
