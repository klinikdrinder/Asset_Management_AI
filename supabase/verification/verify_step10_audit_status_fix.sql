-- Read-only post-application verification for
-- 202607310001_fix_step10_migration_events_status.sql.
-- Run in Supabase SQL Editor after applying the migration and before B3.

do $verification$
declare
  function_body text;
  trigger_ok boolean;
  status_required boolean;
  event_status_required boolean;
  event_status_default text;
  event_status_check text;
  legacy_status_check text;
  missing_event text;
begin
  select pg_catalog.pg_get_functiondef(procedure_row.oid)
  into function_body
  from pg_catalog.pg_proc as procedure_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = procedure_row.pronamespace
  where namespace_row.nspname = 'public'
    and procedure_row.proname
      = 'set_step10_migration_event_legacy_status'
    and pg_catalog.pg_get_function_identity_arguments(
      procedure_row.oid
    ) = '';

  if function_body is null then
    raise exception 'Step 10 legacy audit-status helper is not deployed';
  end if;

  select exists (
    select 1
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as table_row
      on table_row.oid = trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = table_row.relnamespace
    where namespace_row.nspname = 'public'
      and table_row.relname = 'migration_events'
      and trigger_row.tgname
        = 'migration_events_set_step10_legacy_status'
      and not trigger_row.tgisinternal
      and trigger_row.tgenabled <> 'D'
      and pg_catalog.pg_get_triggerdef(trigger_row.oid)
        ~* 'BEFORE INSERT'
  ) into trigger_ok;
  if not trigger_ok then
    raise exception 'Step 10 legacy audit-status trigger is not active';
  end if;

  select column_row.is_nullable = 'NO'
  into status_required
  from information_schema.columns as column_row
  where column_row.table_schema = 'public'
    and column_row.table_name = 'migration_events'
    and column_row.column_name = 'status';
  if not coalesce(status_required, false) then
    raise exception 'migration_events.status is missing or nullable';
  end if;

  select
    column_row.is_nullable = 'NO',
    column_row.column_default
  into event_status_required, event_status_default
  from information_schema.columns as column_row
  where column_row.table_schema = 'public'
    and column_row.table_name = 'migration_events'
    and column_row.column_name = 'event_status';
  if not coalesce(event_status_required, false)
    or event_status_default !~ '''INFO'''
  then
    raise exception 'migration_events.event_status contract changed';
  end if;

  select pg_catalog.pg_get_constraintdef(constraint_row.oid)
  into event_status_check
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.migration_events'::regclass
    and constraint_row.conname = 'migration_events_event_status_check';
  if event_status_check is null
    or event_status_check !~ '''INFO'''
    or event_status_check !~ '''SUCCESS'''
    or event_status_check !~ '''WARNING'''
    or event_status_check !~ '''ERROR'''
  then
    raise exception 'migration_events.event_status CHECK changed';
  end if;

  select string_agg(
    pg_catalog.pg_get_constraintdef(constraint_row.oid),
    ' '
  )
  into legacy_status_check
  from pg_catalog.pg_constraint as constraint_row
  join pg_catalog.pg_attribute as status_attribute
    on status_attribute.attrelid = constraint_row.conrelid
   and status_attribute.attname = 'status'
   and status_attribute.attnum = any(constraint_row.conkey)
  where constraint_row.conrelid = 'public.migration_events'::regclass
    and constraint_row.contype = 'c';
  if legacy_status_check is not null
    and legacy_status_check !~ '''SUCCESS'''
    and legacy_status_check !~ '''COMPLETED'''
  then
    raise exception
      'migration_events.status has no allowed successful Step 10 mapping';
  end if;

  select required.event_type into missing_event
  from (
    values
      ('LIFECYCLE_INITIALIZED'),
      ('CLAIM_RENEWED'),
      ('CLAIM_RELEASED'),
      ('CLAIM_RECOVERED'),
      ('UPLOAD_FAILED'),
      ('UPLOAD_RETRY_SCHEDULED'),
      ('UPLOAD_VERIFIED')
  ) as required(event_type)
  where function_body not like '%' || required.event_type || '%'
  limit 1;
  if missing_event is not null then
    raise exception 'Missing Step 10 event mapping: %', missing_event;
  end if;

  if function_body !~ 'new[.]status'
    or function_body !~ 'new[.]event_status'
    or function_body !~ 'asset_destination_id'
    or function_body !~ 'pg_get_constraintdef'
  then
    raise exception 'Step 10 audit-status helper body is incomplete';
  end if;
end
$verification$;

do $data_reconciliation$
declare
  source_file_count bigint;
  eligible_hashed_count bigint;
  asset_count bigint;
  relationship_count bigint;
  destination_count bigint;
  orphan_relationship_count bigint;
begin
  select count(*) into source_file_count from public.source_files;
  select count(*) into eligible_hashed_count
  from public.source_files
  where decision = 'TAKE'
    and processing_status = 'READY'
    and hash_status = 'HASHED'
    and hash_algorithm = 'SHA-256'
    and content_sha256 ~ '^[0-9a-f]{64}$';
  select count(*) into asset_count from public.assets;
  select count(*) into relationship_count from public.asset_sources;
  select count(*) into destination_count from public.asset_destinations;
  select count(*) into orphan_relationship_count
  from public.asset_sources as relationship
  left join public.assets as asset
    on asset.id = relationship.asset_id
  left join public.source_files as source_file
    on source_file.id = relationship.source_file_id
  where asset.id is null or source_file.id is null;

  if source_file_count <> 886
    or eligible_hashed_count <> 878
    or asset_count <> 878
    or relationship_count <> 878
    or destination_count <> 0
    or orphan_relationship_count <> 0
  then
    raise exception 'Pre-B3 production reconciliation failed';
  end if;
end
$data_reconciliation$;

select
  'STEP_10_AUDIT_STATUS_FIX_VERIFIED' as result,
  886::bigint as expected_source_files,
  878::bigint as expected_canonical_assets,
  0::bigint as expected_asset_destinations;
