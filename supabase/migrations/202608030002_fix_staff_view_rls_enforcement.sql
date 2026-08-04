-- Defense-in-depth authorization gate for the Staff source-folder summary.
--
-- The deployed source_folder_summary view was queryable by authenticated users
-- and relied exclusively on the underlying tables' permissive RLS policies.
-- Legacy shared-reader policies intentionally remain staged during the OAuth
-- transition, so the view also requires an active app_users identity directly.
-- No base-table row is modified by this migration.

begin;

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
where (select private.is_active_app_user());

comment on view public.source_folder_summary is
  'Active-user-gated source-folder access, scan, file-processing, and asset totals.';

revoke all on table public.source_folder_summary from public, anon;
grant select on table public.source_folder_summary to authenticated;
grant select on table public.source_folder_summary to service_role;

do $$
declare
  view_definition text;
  view_options text[];
begin
  select pg_catalog.pg_get_viewdef(c.oid, true), c.reloptions
    into view_definition, view_options
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname='source_folder_summary' and c.relkind='v';

  if view_definition is null
    or view_definition !~ 'private\.is_active_app_user\(\)' then
    raise exception 'source_folder_summary active-user gate was not installed';
  end if;
  if not coalesce(view_options,'{}'::text[]) @> array['security_invoker=true']
    or not coalesce(view_options,'{}'::text[]) @> array['security_barrier=true'] then
    raise exception 'source_folder_summary safe view options were not installed';
  end if;
  if pg_catalog.has_table_privilege('anon','public.source_folder_summary','SELECT') then
    raise exception 'anonymous source_folder_summary SELECT remains available';
  end if;
end;
$$;

commit;
