-- PROPOSED — NOT APPLIED. Review artifact for owner approval.
-- Apply via the Supabase MCP apply_migration (project wcqqjpndlwsvatjuqnol) ONLY after sign-off.
--
-- Purpose: enable the user-context RLS search path (decision 2, 2026-09-11) and the
-- proper tsvector FTS channel (task #3). All statements are ADDITIVE and reversible:
--   - one new SECURITY INVOKER function (FTS ranking)
--   - INSERT/UPDATE RLS policies so an authenticated user can write ONLY their own
--     search telemetry (retrieval already RLS-filters via private.can_user_view_asset)
-- No data is modified. No existing policy/function is dropped except the ones this
-- migration itself (re)creates. Rollback = drop the function + the 7 named policies.
--
-- Preconditions verified live: RLS is enabled on the four telemetry tables (SELECT-only
-- owner_read policies already exist); helper fns private.current_app_user_id() and
-- private.is_search_session_owner(uuid) exist; search_document_builds has search_vector
-- (tsvector) + GIN index search_document_fts_idx; match_kdi_semantic_search_embeddings
-- is already SECURITY INVOKER (no change needed here).

begin;

-- 1) FTS ranking function. SECURITY INVOKER => inherits the caller's RLS, so under a
--    user-context client it returns only assets the user may view. Ordered by ts_rank
--    over the existing GIN index. Replaces the per-token ILIKE scan in candidate-retriever.ts.
create or replace function public.match_search_documents_fts(
  query_text   text,
  result_limit int default 20
)
returns table (
  id uuid, asset_id uuid, scene_id uuid, event_id uuid, document_type text, rank real
)
language sql
stable
security invoker
set search_path = public
as $$
  select b.id, b.asset_id, b.scene_id, b.event_id, b.document_type,
         ts_rank(b.search_vector, websearch_to_tsquery('english', query_text))::real as rank
  from public.search_document_builds b
  where b.active and not b.stale and b.status = 'READY'
    and b.search_vector @@ websearch_to_tsquery('english', query_text)
  order by rank desc
  limit greatest(1, least(coalesce(result_limit, 20), 100));
$$;

grant execute on function public.match_search_documents_fts(text, int) to authenticated;

-- 2) Telemetry write policies (user-context). Each ties the row to the caller's own
--    session so a user can never write another user's telemetry.

-- search_sessions: user may create/update their own session rows.
drop policy if exists search_sessions_owner_insert on public.search_sessions;
create policy search_sessions_owner_insert on public.search_sessions
  for insert to authenticated
  with check (user_id = (select private.current_app_user_id()));

drop policy if exists search_sessions_owner_update on public.search_sessions;
create policy search_sessions_owner_update on public.search_sessions
  for update to authenticated
  using (user_id = (select private.current_app_user_id()))
  with check (user_id = (select private.current_app_user_id()));

-- search_queries: rows must belong to a session the caller owns.
drop policy if exists search_queries_owner_insert on public.search_queries;
create policy search_queries_owner_insert on public.search_queries
  for insert to authenticated
  with check ((select private.is_search_session_owner(session_id)));

drop policy if exists search_queries_owner_update on public.search_queries;
create policy search_queries_owner_update on public.search_queries
  for update to authenticated
  using ((select private.is_search_session_owner(session_id)))
  with check ((select private.is_search_session_owner(session_id)));

-- search_results: rows must belong to a query in a session the caller owns.
drop policy if exists search_results_owner_insert on public.search_results;
create policy search_results_owner_insert on public.search_results
  for insert to authenticated
  with check (exists (
    select 1 from public.search_queries q
    where q.id = search_query_id and (select private.is_search_session_owner(q.session_id))
  ));

-- search_feedback: user may record feedback against their own queries.
drop policy if exists search_feedback_owner_insert on public.search_feedback;
create policy search_feedback_owner_insert on public.search_feedback
  for insert to authenticated
  with check (exists (
    select 1 from public.search_queries q
    where q.id = search_query_id and (select private.is_search_session_owner(q.session_id))
  ));

commit;

-- ROLLBACK (if ever needed):
-- drop function if exists public.match_search_documents_fts(text, int);
-- drop policy if exists search_sessions_owner_insert on public.search_sessions;
-- drop policy if exists search_sessions_owner_update on public.search_sessions;
-- drop policy if exists search_queries_owner_insert on public.search_queries;
-- drop policy if exists search_queries_owner_update on public.search_queries;
-- drop policy if exists search_results_owner_insert on public.search_results;
-- drop policy if exists search_feedback_owner_insert on public.search_feedback;
