-- Transactional post-deployment verifier for
-- 202607310004_fix_step10_exact_legacy_status_contract.sql.
begin;

do $verification$
declare
  status_attribute_number smallint;
  status_expression text;
  event_status_expression text;
  event_type_expression text;
  function_body text;
  status_nullable text;
  trigger_count integer;
  lifecycle_id uuid;
  asset_uuid uuid;
  observed_mapping jsonb;
  deployed_statuses text[];
  required_statuses constant text[] := array[
    'QUEUED',
    'RUNNING',
    'SUCCESS',
    'SKIPPED',
    'DUPLICATE',
    'FAILED',
    'RETRYING',
    'CANCELLED',
    'INFO',
    'WARNING',
    'ERROR'
  ]::text[];
  required_event_statuses constant text[] :=
    array['INFO', 'SUCCESS', 'WARNING', 'ERROR']::text[];
  required_event_types constant text[] := array[
    'LIFECYCLE_INITIALIZED',
    'UPLOAD_QUEUED',
    'UPLOAD_CLAIMED',
    'CLAIM_RENEWED',
    'CLAIM_RELEASED',
    'CLAIM_RECOVERED',
    'UPLOAD_STARTED',
    'UPLOAD_CREATED',
    'UPLOAD_RECOVERED',
    'UPLOAD_VERIFIED',
    'UPLOAD_FAILED',
    'UPLOAD_RETRY_SCHEDULED',
    'SOURCE_CHANGED',
    'SOURCE_NOT_FOUND',
    'SOURCE_ACCESS_DENIED',
    'DESTINATION_ACCESS_DENIED',
    'DESTINATION_CONFLICT',
    'MANUAL_REVIEW_REQUIRED'
  ]::text[];
  required_value text;
begin
  select attribute_row.attnum
  into status_attribute_number
  from pg_catalog.pg_attribute as attribute_row
  where attribute_row.attrelid = 'public.migration_events'::regclass
    and attribute_row.attname = 'status'
    and not attribute_row.attisdropped;

  select pg_catalog.pg_get_expr(
    constraint_row.conbin,
    constraint_row.conrelid
  )
  into status_expression
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.migration_events'::regclass
    and constraint_row.conname = 'migration_events_status_check'
    and constraint_row.contype = 'c'
    and constraint_row.convalidated
    and constraint_row.conkey
      = array[status_attribute_number]::smallint[];
  if status_expression is null then
    raise exception 'Strict migration_events_status_check is not active';
  end if;

  select pg_catalog.array_agg(
    distinct match_row.value order by match_row.value
  )
  into deployed_statuses
  from (
    select match_result[1] as value
    from pg_catalog.regexp_matches(
      status_expression,
      '''([A-Z][A-Z0-9_]*)''',
      'g'
    ) as match_result
  ) as match_row;
  if deployed_statuses <> (
    select pg_catalog.array_agg(value order by value)
    from pg_catalog.unnest(required_statuses) as value_row(value)
  ) then
    raise exception 'Deployed migration_events.status vocabulary is incorrect';
  end if;
  if pg_catalog.strpos(
    status_expression,
    pg_catalog.quote_literal('STEP10_ARBITRARY_INVALID_STATUS')
  ) <> 0 then
    raise exception 'Arbitrary legacy status is unexpectedly allowed';
  end if;

  select column_row.is_nullable
  into status_nullable
  from information_schema.columns as column_row
  where column_row.table_schema = 'public'
    and column_row.table_name = 'migration_events'
    and column_row.column_name = 'status';
  if status_nullable <> 'NO' then
    raise exception 'migration_events.status is not required';
  end if;

  select pg_catalog.pg_get_expr(
    constraint_row.conbin,
    constraint_row.conrelid
  )
  into event_status_expression
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.migration_events'::regclass
    and constraint_row.conname = 'migration_events_event_status_check'
    and constraint_row.contype = 'c'
    and constraint_row.convalidated;
  foreach required_value in array required_event_statuses loop
    if pg_catalog.strpos(
      event_status_expression,
      pg_catalog.quote_literal(required_value)
    ) = 0 then
      raise exception 'Required event_status is missing: %', required_value;
    end if;
  end loop;
  if pg_catalog.strpos(
    event_status_expression,
    pg_catalog.quote_literal('STEP10_ARBITRARY_EVENT_STATUS')
  ) <> 0 then
    raise exception 'event_status constraint is not strict';
  end if;

  select pg_catalog.pg_get_expr(
    constraint_row.conbin,
    constraint_row.conrelid
  )
  into event_type_expression
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.migration_events'::regclass
    and constraint_row.conname = 'migration_events_event_type_check'
    and constraint_row.contype = 'c'
    and constraint_row.convalidated;
  foreach required_value in array required_event_types loop
    if pg_catalog.strpos(
      event_type_expression,
      pg_catalog.quote_literal(required_value)
    ) = 0 then
      raise exception 'Required Step 10 event type is missing: %', required_value;
    end if;
  end loop;
  if pg_catalog.strpos(
    event_type_expression,
    pg_catalog.quote_literal('STEP10_ARBITRARY_INVALID_EVENT')
  ) <> 0 then
    raise exception 'event_type constraint is not strict';
  end if;

  select pg_catalog.pg_get_functiondef(procedure_row.oid)
  into function_body
  from pg_catalog.pg_proc as procedure_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = procedure_row.pronamespace
  where namespace_row.nspname = 'public'
    and procedure_row.proname
      = 'set_step10_migration_event_legacy_status'
    and procedure_row.pronargs = 0;
  if function_body is null
    or function_body !~ 'new[.]status := ''INFO'''
    or function_body !~ 'new[.]status := ''SUCCESS'''
    or function_body !~ 'new[.]status := ''WARNING'''
    or function_body !~ 'new[.]status := ''ERROR'''
  then
    raise exception 'Step 10 legacy status helper mapping is incomplete';
  end if;

  select pg_catalog.count(*)
  into trigger_count
  from pg_catalog.pg_trigger as trigger_row
  where trigger_row.tgrelid = 'public.migration_events'::regclass
    and trigger_row.tgname
      = 'migration_events_set_step10_legacy_status'
    and not trigger_row.tgisinternal
    and (trigger_row.tgtype & 2) = 2
    and (trigger_row.tgtype & 4) = 4;
  if trigger_count <> 1 then
    raise exception 'Step 10 legacy status trigger is not active';
  end if;

  select destination_row.id, destination_row.asset_id
  into lifecycle_id, asset_uuid
  from public.asset_destinations as destination_row
  order by destination_row.id
  limit 1;

  insert into public.migration_events (
    asset_id,
    asset_destination_id,
    event_type,
    event_status,
    message,
    details
  )
  select
    asset_uuid,
    lifecycle_id,
    probe.event_type,
    probe.event_status,
    'Step 10 exact status verification',
    '{}'::jsonb
  from (
    values
      ('UPLOAD_STARTED', 'INFO'),
      ('UPLOAD_VERIFIED', 'SUCCESS'),
      ('MANUAL_REVIEW_REQUIRED', 'WARNING'),
      ('UPLOAD_FAILED', 'ERROR')
  ) as probe(event_type, event_status);

  select pg_catalog.jsonb_object_agg(
    event_row.event_status,
    event_row.status
  )
  into observed_mapping
  from public.migration_events as event_row
  where event_row.asset_destination_id = lifecycle_id
    and event_row.message = 'Step 10 exact status verification';
  if observed_mapping <> pg_catalog.jsonb_build_object(
    'INFO', 'INFO',
    'SUCCESS', 'SUCCESS',
    'WARNING', 'WARNING',
    'ERROR', 'ERROR'
  ) then
    raise exception 'Observed Step 10 legacy status mapping is incorrect';
  end if;

  begin
    insert into public.migration_events (
      asset_id,
      asset_destination_id,
      event_type,
      event_status,
      status,
      message,
      details
    ) values (
      asset_uuid,
      lifecycle_id,
      'UPLOAD_STARTED',
      'INFO',
      'STEP10_ARBITRARY_INVALID_STATUS',
      'Step 10 invalid status verification',
      '{}'::jsonb
    );
    raise exception 'Arbitrary legacy status was accepted';
  exception when check_violation then null;
  end;

  begin
    insert into public.migration_events (
      asset_id,
      asset_destination_id,
      event_type,
      event_status,
      status,
      message,
      details
    ) values (
      asset_uuid,
      lifecycle_id,
      'STEP10_ARBITRARY_INVALID_EVENT',
      'INFO',
      'INFO',
      'Step 10 invalid event verification',
      '{}'::jsonb
    );
    raise exception 'Arbitrary event type was accepted';
  exception when check_violation then null;
  end;

  if (select pg_catalog.count(*) from public.source_files) <> 886
    or (select pg_catalog.count(*) from public.assets) <> 878
    or (select pg_catalog.count(*) from public.asset_sources) <> 878
    or (select pg_catalog.count(*) from public.asset_destinations) <> 878
  then
    raise exception 'Step 9 or lifecycle reconciliation count changed';
  end if;
  if (
    select pg_catalog.count(*)
    from public.asset_destinations
    where destination_google_file_id is not null
  ) <> 0 then
    raise exception 'Pilot destination IDs exist before retry';
  end if;
end;
$verification$;

select 'STEP_10_LEGACY_STATUS_MAPPING_VERIFIED' as result;

rollback;
