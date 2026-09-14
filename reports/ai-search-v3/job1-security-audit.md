# Job 1 RLS and Security Audit

## Overall result

All 26 public tables have RLS enabled. No data or grants were changed. A critical destructive table-grant exposure and two default-`PUBLIC EXECUTE` SECURITY DEFINER exposures block Job 2.

## Critical destructive table grants — STOP finding

Direct privilege checks confirm that both `anon` and `authenticated` have `TRUNCATE` on:

- `asset_ai_profiles`
- `asset_people`
- `asset_video_segments`
- `asset_transcript_chunks`
- `asset_search_concepts`
- `asset_metadata_assertions`

RLS does not apply to `TRUNCATE`. These roles lack SELECT on the six tables, but the destructive privilege remains effective. This is a critical security gap and a hard Job 2 blocker. Per Job 1 instructions it was reported but not changed, and no destructive call was attempted.


## Policy matrix

| Tables | SELECT | INSERT | UPDATE | DELETE | Interpretation |
|---|:---:|:---:|:---:|:---:|---|
| source_folders, sync_runs, scan_runs, source_files, assets, asset_sources, migration_events, asset_destinations, app_users, asset_semantic_index | Yes | No | No | No | Authenticated individual-read policies; service operations rely on service role |
| asset_ai_profiles, asset_people, asset_video_segments, asset_transcript_chunks, asset_search_concepts, asset_metadata_assertions | Policy exists but no role SELECT grant | No | No | No | Intended service-managed tables, but browser roles incorrectly hold TRUNCATE/REFERENCES/TRIGGER |
| admin_accounts, admin_auth_audit, admin_sessions, approved_app_users, asset_embeddings, asset_visual_embeddings, asset_visual_index_jobs, synchronization_locks, user_invitations, user_management_audit | No | No | No | No | Default-deny to Data API roles; direct service/admin access only by grants/bypass |

The policy-less embedding/job tables are intentionally inaccessible to browser roles based on migration comments and explicit table revokes. The policy-less admin/session/audit/invitation/lock tables are also consistent with server/service-only access, but this intent should be recorded in schema comments in a future approved hardening migration.

## SECURITY DEFINER review

- `hybrid_search_assets`: authenticated execute only; locked `search_path = ''`; explicitly calls `private.is_active_app_user()`; appropriate privileged read of hidden embeddings. Current grant is intentional.
- `hybrid_search_assets_v2`: authenticated execute only; locked `search_path = ''`; calls `private.is_active_app_user()` in its WHERE clause; current grant is intentional. Authorization is evaluated per plan row rather than isolated in a CTE, but it still gates results.
- `queue_new_asset_visual_index`: trigger function, locked empty search path, but ACL is default `PUBLIC EXECUTE`. Supabase advisor flags anon and authenticated RPC execution. Even if a direct RPC call cannot construct a trigger return value usefully, exposure is unnecessary and violates least privilege. **Blocker: revoke PUBLIC/anon/authenticated execute after explicit review.**
- `rls_auto_enable`: event-trigger function, `search_path=pg_catalog`, ACL is default `PUBLIC EXECUTE`. Advisor flags the exposed definer. Its body is DDL-event specific, but direct API exposure is unnecessary. **Blocker: revoke PUBLIC/anon/authenticated execute after explicit review.**
- Other definers inventoried in the baseline: `bootstrap_firebase_app_user` is service-role only; `link_current_app_user` is authenticated and implements the identity-linking contract.

## Advisor findings

- INFO: RLS enabled with no policy on the ten default-deny tables above.
- WARN: `vector` and `pg_trgm` installed in `public`. Moving extensions would be invasive because live functions/operators explicitly qualify `public`; defer.
- WARN: leaked-password protection disabled. Review in Supabase Auth settings.
- WARN: authenticated SECURITY DEFINER search RPCs. Accepted because they lock search path and enforce active-user authorization.
- WARN: the two default-PUBLIC definers above. Not accepted for Job 2 readiness.

Advisor reference: https://supabase.com/docs/guides/database/database-linter

## Criticality

A broad destructive privilege path was demonstrated through effective privilege checks (without executing it). The database audit stopped at that point. Job 2 is **NOT READY** until all destructive browser-role grants and default definer execute grants are resolved and verified.
