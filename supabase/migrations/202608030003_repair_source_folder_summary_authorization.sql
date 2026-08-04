-- Retire shared/broad reader bypasses and enforce individual RBAC on the
-- Staff-facing source-folder summary. Authorization objects only; no data DML.

begin;

do $$
begin
  if to_regtype('public.app_role') is null
    or to_regclass('public.app_users') is null
    or to_regprocedure('private.is_active_app_user()') is null then
    raise exception 'Individual RBAC prerequisites are not fully deployed';
  end if;
  if not exists (
    select 1 from pg_policies
    where schemaname='public' and policyname='source_folders_individual_read'
  ) then
    raise exception 'Individual source-folder RLS policy is missing';
  end if;
end;
$$;

-- These policies predate individual identities. The USING (true) policies
-- authorize every authenticated JWT; the claim policies authorize the retired
-- shared reader. Either path bypasses app_users and must be removed.
drop policy if exists "Authenticated users can read source folders" on public.source_folders;
drop policy if exists "Authenticated users can read source files" on public.source_files;
drop policy if exists "Authenticated users can read assets" on public.assets;
drop policy if exists "Authenticated users can read asset sources" on public.asset_sources;
drop policy if exists "Authenticated users can read sync runs" on public.sync_runs;
drop policy if exists "Authenticated users can read scan runs" on public.scan_runs;
drop policy if exists "Authenticated users can read migration events" on public.migration_events;

drop policy if exists source_folders_authorized_read on public.source_folders;
drop policy if exists source_files_authorized_read on public.source_files;
drop policy if exists assets_authorized_read on public.assets;
drop policy if exists asset_sources_authorized_read on public.asset_sources;
drop policy if exists asset_destinations_authorized_read on public.asset_destinations;
drop policy if exists sync_runs_authorized_read on public.sync_runs;
drop policy if exists scan_runs_authorized_read on public.scan_runs;
drop policy if exists migration_events_authorized_read on public.migration_events;

create or replace view public.source_folder_summary
with (security_invoker = true, security_barrier = true)
as
select
  sf.id, sf.source_name, sf.account_name, sf.folder_url, sf.google_folder_id,
  sf.active, sf.access_status, sf.permission_role, sf.last_access_checked_at,
  sf.last_scan_at, sf.last_successful_scan_at, sf.notes, sf.created_at, sf.updated_at,
  coalesce(file_totals.total_files,0)::bigint as total_files,
  coalesce(file_totals.take_files,0)::bigint as take_files,
  coalesce(file_totals.skip_files,0)::bigint as skip_files,
  coalesce(file_totals.uploaded_files,0)::bigint as uploaded_files,
  coalesce(file_totals.duplicate_files,0)::bigint as duplicate_files,
  coalesce(file_totals.failed_files,0)::bigint as failed_files,
  coalesce(asset_totals.asset_count,0)::bigint as asset_count,
  latest_scan.id as latest_scan_run_id,
  latest_scan.status as latest_scan_status,
  latest_scan.started_at as latest_scan_started_at,
  latest_scan.completed_at as latest_scan_completed_at
from public.source_folders sf
left join lateral (
  select count(*) as total_files,
    count(*) filter(where source_file.decision='TAKE') as take_files,
    count(*) filter(where source_file.decision='SKIP') as skip_files,
    count(*) filter(where source_file.processing_status='UPLOADED') as uploaded_files,
    count(*) filter(where source_file.processing_status='DUPLICATE') as duplicate_files,
    count(*) filter(where source_file.processing_status='FAILED') as failed_files
  from public.source_files source_file
  where source_file.source_folder_id=sf.id
) file_totals on true
left join lateral (
  select count(distinct asset_source.asset_id) as asset_count
  from public.source_files source_file
  join public.asset_sources asset_source on asset_source.source_file_id=source_file.id
  where source_file.source_folder_id=sf.id
) asset_totals on true
left join lateral (
  select scan.id,scan.status,scan.started_at,scan.completed_at
  from public.scan_runs scan
  where scan.source_folder_id=sf.id
  order by scan.created_at desc,scan.id desc
  limit 1
) latest_scan on true
where (select auth.uid()) is not null
  and exists (
    select 1
    from public.app_users application_user
    where application_user.user_id=(select auth.uid())
      and application_user.is_active
      and application_user.role in ('STAFF'::public.app_role,'ADMIN'::public.app_role)
  );

comment on view public.source_folder_summary is
  'Individual-RBAC source-folder access, scan, file-processing, and asset totals.';

revoke all on table public.source_folder_summary from public, anon, authenticated, service_role;
grant select on table public.source_folder_summary to authenticated, service_role;

-- Application users remain read-only across identity, media, and operations.
revoke insert, update, delete, truncate on public.approved_app_users, public.app_users,
  public.source_folders, public.sync_runs, public.scan_runs, public.source_files,
  public.assets, public.asset_sources, public.asset_destinations, public.migration_events
  from anon, authenticated;

do $$
declare
  view_definition text;
  view_options text[];
begin
  select pg_get_viewdef(c.oid,true),c.reloptions into view_definition,view_options
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname='source_folder_summary' and c.relkind='v';

  if view_definition !~ '\mapp_users\M'
    or view_definition !~ 'auth\.uid\(\)'
    or view_definition !~ 'is_active'
    or view_definition !~ 'STAFF'
    or view_definition !~ 'ADMIN' then
    raise exception 'source_folder_summary explicit individual-RBAC gate is missing';
  end if;
  if not coalesce(view_options,'{}'::text[]) @> array['security_invoker=true']
    or not coalesce(view_options,'{}'::text[]) @> array['security_barrier=true'] then
    raise exception 'source_folder_summary safe view options are missing';
  end if;
  if has_table_privilege('anon','public.source_folder_summary','SELECT')
    or not has_table_privilege('authenticated','public.source_folder_summary','SELECT') then
    raise exception 'source_folder_summary SELECT grants are unsafe';
  end if;
  if exists (
    select 1 from pg_policies
    where schemaname='public'
      and tablename in ('source_folders','source_files','assets','asset_sources',
        'asset_destinations','sync_runs','scan_runs','migration_events')
      and (coalesce(qual,'') ~ 'kdi_media' or coalesce(qual,'')='true')
  ) then
    raise exception 'A broad or shared-reader RLS bypass remains';
  end if;
end;
$$;

commit;
