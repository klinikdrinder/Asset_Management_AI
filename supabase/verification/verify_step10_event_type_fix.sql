
do $verification$
declare
  event_type_attribute_number smallint;
  constraint_row record;
  current_values text[];
  preserved_legacy_values text[];
  required_step10_values constant text[] := array[
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
  missing_values text[];
  function_body text;
begin
  select attribute_row.attnum
  into event_type_attribute_number
  from pg_catalog.pg_attribute as attribute_row
  where attribute_row.attrelid = 'public.migration_events'::regclass
    and attribute_row.attname = 'event_type'
    and not attribute_row.attisdropped;

  if event_type_attribute_number is null then
    raise exception
      'migration_events.event_type column was not found';
  end if;

  select
    constraint_item.oid,
    constraint_item.convalidated,
    constraint_item.conkey,
    pg_catalog.pg_get_constraintdef(constraint_item.oid) as definition,
    pg_catalog.pg_get_expr(
      constraint_item.conbin,
      constraint_item.conrelid
    ) as expression,
    pg_catalog.obj_description(
      constraint_item.oid,
      'pg_constraint'
    ) as description
  into constraint_row
  from pg_catalog.pg_constraint as constraint_item
  where constraint_item.conrelid = 'public.migration_events'::regclass
    and constraint_item.conname = 'migration_events_event_type_check'
    and constraint_item.contype = 'c';

  if constraint_row.oid is null
    or not constraint_row.convalidated
    or constraint_row.conkey
      <> array[event_type_attribute_number]::smallint[]
  then
    raise exception
      'Strict migration_events_event_type_check is missing or invalid';
  end if;

  if constraint_row.expression !~*
    'event_type[[:space:]]*=[[:space:]]*any'
  then
    raise exception
      'event_type CHECK is not a strict membership constraint';
  end if;

  select pg_catalog.array_agg(
    distinct match_row.value
    order by match_row.value
  )
  into current_values
  from (
    select match_result[1] as value
    from pg_catalog.regexp_matches(
      constraint_row.expression,
      '''([A-Z][A-Z0-9_]*)''',
      'g'
    ) as match_result
  ) as match_row;

  if current_values is null then
    raise exception
      'No event-type values could be extracted from the deployed constraint';
  end if;

  select pg_catalog.string_to_array(
    pg_catalog.substr(
      constraint_row.description,
      pg_catalog.length(
        'step10_preserved_legacy_event_types='
      ) + 1
    ),
    ','
  )
  into preserved_legacy_values
  where constraint_row.description
    like 'step10_preserved_legacy_event_types=%';

  if preserved_legacy_values is null then
    raise exception
      'Preserved legacy event vocabulary metadata is missing';
  end if;

  select pg_catalog.array_agg(value order by value)
  into missing_values
  from pg_catalog.unnest(
    required_step10_values || preserved_legacy_values
  ) as value_row(value)
  where not (value = any(current_values));

  if missing_values is not null then
    raise exception
      'Required event types are missing: %',
      missing_values;
  end if;

  if 'STEP10_ARBITRARY_INVALID_EVENT' = any(current_values)
    or constraint_row.expression
      like '%STEP10_ARBITRARY_INVALID_EVENT%'
  then
    raise exception
      'Arbitrary event type is unexpectedly allowed';
  end if;

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

  if function_body is null
    or function_body !~ 'new[.]status'
    or function_body !~ 'new[.]event_status'
  then
    raise exception
      'Step 10 status compatibility helper changed';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid = 'public.migration_events'::regclass
      and trigger_row.tgname
        = 'migration_events_set_step10_legacy_status'
      and not trigger_row.tgisinternal
      and trigger_row.tgenabled <> 'D'
      and pg_catalog.pg_get_triggerdef(trigger_row.oid)
        ~* 'BEFORE INSERT'
  ) then
    raise exception
      'Step 10 status compatibility trigger changed';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint as status_constraint
    where status_constraint.conrelid
      = 'public.migration_events'::regclass
      and status_constraint.conname
        = 'migration_events_event_status_check'
      and pg_catalog.pg_get_constraintdef(status_constraint.oid)
        ~ '''INFO'''
      and pg_catalog.pg_get_constraintdef(status_constraint.oid)
        ~ '''SUCCESS'''
      and pg_catalog.pg_get_constraintdef(status_constraint.oid)
        ~ '''WARNING'''
      and pg_catalog.pg_get_constraintdef(status_constraint.oid)
        ~ '''ERROR'''
  ) then
    raise exception
      'migration_events.event_status contract changed';
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
  select count(*)
  into source_file_count
  from public.source_files;

  select count(*)
  into eligible_hashed_count
  from public.source_files
  where decision = 'TAKE'
    and processing_status = 'READY'
    and hash_status = 'HASHED'
    and hash_algorithm = 'SHA-256'
    and content_sha256 ~ '^[0-9a-f]{64}$';

  select count(*)
  into asset_count
  from public.assets;

  select count(*)
  into relationship_count
  from public.asset_sources;

  select count(*)
  into destination_count
  from public.asset_destinations;

  select count(*)
  into orphan_relationship_count
  from public.asset_sources as relationship
  left join public.assets as asset
    on asset.id = relationship.asset_id
  left join public.source_files as source_file
    on source_file.id = relationship.source_file_id
  where asset.id is null
    or source_file.id is null;

  if source_file_count <> 886
    or eligible_hashed_count <> 878
    or asset_count <> 878
    or relationship_count <> 878
    or destination_count <> 0
    or orphan_relationship_count <> 0
  then
    raise exception
      'Pre-B3 production reconciliation failed. '
      'source_files=%, eligible_hashed=%, assets=%, '
      'asset_sources=%, asset_destinations=%, '
      'orphan_relationships=%',
      source_file_count,
      eligible_hashed_count,
      asset_count,
      relationship_count,
      destination_count,
      orphan_relationship_count;
  end if;
end
$data_reconciliation$;

with constraint_contract as (
  select
    pg_catalog.pg_get_expr(
      constraint_row.conbin,
      constraint_row.conrelid
    ) as expression,
    pg_catalog.obj_description(
      constraint_row.oid,
      'pg_constraint'
    ) as description
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid
      = 'public.migration_events'::regclass
    and constraint_row.conname
      = 'migration_events_event_type_check'
)
select
  'STEP_10_EVENT_TYPE_FIX_VERIFIED' as result,
  description as preserved_legacy_vocabulary,
  expression as deployed_event_type_contract,
  (
    select count(*)
    from public.asset_destinations
  ) as asset_destinations
from constraint_contract;