-- KDI foundation live-state verification.
-- Every result set is read-only and may be run in the Supabase SQL Editor.

-- 1. Required table existence.
with expected_tables(table_name) as (
  values
    ('source_folders'),
    ('sync_runs'),
    ('scan_runs'),
    ('source_files'),
    ('assets'),
    ('asset_sources'),
    ('migration_events')
)
select
  expected.table_name,
  to_regclass(format('public.%I', expected.table_name)) is not null
    as table_exists
from expected_tables expected
order by expected.table_name;

-- 2. Live columns and data types.
select
  columns.table_schema,
  columns.table_name,
  columns.ordinal_position,
  columns.column_name,
  columns.data_type,
  columns.udt_schema,
  columns.udt_name,
  columns.is_nullable,
  columns.column_default
from information_schema.columns columns
where columns.table_schema = 'public'
  and columns.table_name in (
    'source_folders',
    'sync_runs',
    'scan_runs',
    'source_files',
    'assets',
    'asset_sources',
    'migration_events'
  )
order by columns.table_name, columns.ordinal_position;

-- 3. Columns introduced by the previously run pilot compatibility SQL.
with expected_columns(table_name, column_name) as (
  values
    ('source_files', 'last_scan_run_id'),
    ('source_files', 'skip_reason'),
    ('source_files', 'destination_file_id'),
    ('source_files', 'destination_web_view_link'),
    ('source_files', 'duplicate_of_source_file_id'),
    ('source_files', 'uploaded_at'),
    ('scan_runs', 'run_mode'),
    ('scan_runs', 'files_uploaded'),
    ('scan_runs', 'duplicates_found')
)
select
  expected.table_name,
  expected.column_name,
  columns.column_name is not null as column_exists,
  columns.data_type,
  columns.udt_name,
  columns.is_nullable,
  columns.column_default
from expected_columns expected
left join information_schema.columns columns
  on columns.table_schema = 'public'
  and columns.table_name = expected.table_name
  and columns.column_name = expected.column_name
order by expected.table_name, expected.column_name;

-- 4. Required foreign-key existence and live definitions.
with expected_foreign_keys(constraint_name) as (
  values
    ('source_files_last_scan_run_id_fkey'),
    ('source_files_duplicate_of_source_file_id_fkey')
),
live_foreign_keys as (
  select
    constraints.oid,
    constraints.conname,
    constraints.conrelid,
    constraints.convalidated
  from pg_catalog.pg_constraint constraints
  join pg_catalog.pg_class relation
    on relation.oid = constraints.conrelid
  join pg_catalog.pg_namespace namespace
    on namespace.oid = relation.relnamespace
  where namespace.nspname = 'public'
    and constraints.contype = 'f'
)
select
  expected.constraint_name,
  constraints.oid is not null as foreign_key_exists,
  namespace.nspname as table_schema,
  relation.relname as table_name,
  pg_get_constraintdef(constraints.oid, true) as definition,
  constraints.convalidated as is_validated
from expected_foreign_keys expected
left join live_foreign_keys constraints
  on constraints.conname = expected.constraint_name
left join pg_catalog.pg_class relation
  on relation.oid = constraints.conrelid
left join pg_catalog.pg_namespace namespace
  on namespace.oid = relation.relnamespace
order by expected.constraint_name;

-- 5a. set_updated_at() existence.
select
  exists (
    select 1
    from pg_catalog.pg_proc procedure
    join pg_catalog.pg_namespace namespace
      on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'public'
      and procedure.proname = 'set_updated_at'
      and procedure.pronargs = 0
  ) as set_updated_at_exists;

-- 5b. Non-internal triggers on the seven foundation tables.
select
  namespace.nspname as table_schema,
  relation.relname as table_name,
  trigger.tgname as trigger_name,
  trigger.tgenabled as enabled_state,
  pg_get_triggerdef(trigger.oid, true) as definition
from pg_catalog.pg_trigger trigger
join pg_catalog.pg_class relation
  on relation.oid = trigger.tgrelid
join pg_catalog.pg_namespace namespace
  on namespace.oid = relation.relnamespace
where namespace.nspname = 'public'
  and relation.relname in (
    'source_folders',
    'sync_runs',
    'scan_runs',
    'source_files',
    'assets',
    'asset_sources',
    'migration_events'
  )
  and not trigger.tgisinternal
order by relation.relname, trigger.tgname;

-- 5c. source_folder_summary view existence and definition.
select
  to_regclass('public.source_folder_summary') is not null
    as source_folder_summary_exists,
  views.view_definition
from information_schema.views views
where views.table_schema = 'public'
  and views.table_name = 'source_folder_summary'
union all
select
  false,
  null
where to_regclass('public.source_folder_summary') is null;

-- 5d. Live indexes involving google_folder_id.
select
  indexes.schemaname as table_schema,
  indexes.tablename as table_name,
  indexes.indexname as index_name,
  indexes.indexdef as definition
from pg_catalog.pg_indexes indexes
where indexes.schemaname = 'public'
  and indexes.tablename = 'source_folders'
  and indexes.indexdef ilike '%google_folder_id%'
order by indexes.indexname;

-- 5e. RLS state on all seven foundation tables.
with expected_tables(table_name) as (
  values
    ('source_folders'),
    ('sync_runs'),
    ('scan_runs'),
    ('source_files'),
    ('assets'),
    ('asset_sources'),
    ('migration_events')
)
select
  expected.table_name,
  relation.oid is not null as table_exists,
  coalesce(relation.relrowsecurity, false) as rls_enabled,
  coalesce(relation.relforcerowsecurity, false) as rls_forced
from expected_tables expected
left join pg_catalog.pg_namespace namespace
  on namespace.nspname = 'public'
left join pg_catalog.pg_class relation
  on relation.relnamespace = namespace.oid
  and relation.relname = expected.table_name
  and relation.relkind in ('r', 'p')
order by expected.table_name;

-- 5f. Existing policies on all seven foundation tables.
select
  policies.schemaname as table_schema,
  policies.tablename as table_name,
  policies.policyname as policy_name,
  policies.permissive,
  policies.roles,
  policies.cmd,
  policies.qual,
  policies.with_check
from pg_catalog.pg_policies policies
where policies.schemaname = 'public'
  and policies.tablename in (
    'source_folders',
    'sync_runs',
    'scan_runs',
    'source_files',
    'assets',
    'asset_sources',
    'migration_events'
  )
order by policies.tablename, policies.policyname;

-- 6. Duplicate non-null Google folder IDs.
select
  source_folders.google_folder_id,
  count(*) as duplicate_count
from public.source_folders source_folders
where source_folders.google_folder_id is not null
group by source_folders.google_folder_id
having count(*) > 1
order by source_folders.google_folder_id;

-- 7. Current approved source-folder records with non-secret fields only.
select
  source_folders.source_name,
  source_folders.google_folder_id,
  source_folders.active,
  source_folders.access_status,
  source_folders.permission_role
from public.source_folders source_folders
where source_folders.google_folder_id in (
  '1J7rUY-n4oVFqwY07jXOwwu_wFo8jeCsI',
  '1kYX3KIEFkerRMrTvZk2zPpVaFQoCLE4v',
  '1TkV6WEH5ymgqZmU7WgYFwYeZUxGYkEUt'
)
order by source_folders.source_name;

-- 8. Existing check constraints and validation state.
select
  namespace.nspname as table_schema,
  relation.relname as table_name,
  constraints.conname as constraint_name,
  constraints.convalidated as is_validated,
  pg_get_constraintdef(constraints.oid, true) as definition
from pg_catalog.pg_constraint constraints
join pg_catalog.pg_class relation
  on relation.oid = constraints.conrelid
join pg_catalog.pg_namespace namespace
  on namespace.oid = relation.relnamespace
where namespace.nspname = 'public'
  and relation.relname in (
    'source_folders',
    'sync_runs',
    'scan_runs',
    'source_files',
    'assets',
    'asset_sources',
    'migration_events'
  )
  and constraints.contype = 'c'
order by relation.relname, constraints.conname;

-- 9. Supabase migration-history storage existence.
with migration_history_status as (
  select
    exists (
      select 1
      from pg_catalog.pg_namespace namespace
      where namespace.nspname = 'supabase_migrations'
    ) as supabase_migrations_schema_exists,
    to_regclass('supabase_migrations.schema_migrations') is not null
      as schema_migrations_table_exists
)
select
  status.supabase_migrations_schema_exists,
  status.schema_migrations_table_exists,
  not status.schema_migrations_table_exists
    as migration_history_inspection_unavailable,
  case
    when status.schema_migrations_table_exists then
      'History storage exists, version rows are not queried by this script.'
    else
      'History storage is absent, versions 202607280001, '
      || '202607280002 and 202607280003 cannot be checked through it.'
  end as inspection_status,
  array[
    '202607280001',
    '202607280002',
    '202607280003'
  ]::text[] as requested_versions
from migration_history_status status;
