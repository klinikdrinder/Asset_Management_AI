-- KDI AI Search V3 Job 1.1: narrow client privilege remediation.
--
-- The six AI-intelligence tables inherited direct TRUNCATE grants for anon
-- and authenticated from the postgres/public default table ACL. RLS does not
-- govern TRUNCATE. Preserve owner and backend privileges; remove only client
-- and PUBLIC TRUNCATE access.
--
-- The two SECURITY DEFINER routines are trigger-only infrastructure. Their
-- null ACLs expose PostgreSQL's built-in PUBLIC EXECUTE default. Revoking
-- direct execution does not disable their existing trigger/event-trigger use.

begin;

revoke truncate on table
  public.asset_ai_profiles,
  public.asset_metadata_assertions,
  public.asset_people,
  public.asset_search_concepts,
  public.asset_transcript_chunks,
  public.asset_video_segments
from public, anon, authenticated;

revoke execute on function public.queue_new_asset_visual_index()
  from public, anon, authenticated;

revoke execute on function public.rls_auto_enable()
  from public, anon, authenticated;

-- Prevent recurrence for public tables created by the postgres role used by
-- this project's migration runner. Future client access must be explicit.
alter default privileges for role postgres in schema public
  revoke truncate on tables from public, anon, authenticated;

-- Prevent future functions from becoming direct client RPCs by default.
-- Explicitly intended RPCs must receive narrowly reviewed grants afterward.
alter default privileges for role postgres in schema public
  revoke execute on functions from public, anon, authenticated;

-- Supabase's managed supabase_admin defaults were inspected separately. The
-- postgres migration runner cannot alter them and Job 2 must continue using
-- the postgres-owned migration path rather than dashboard-owned DDL.

commit;

