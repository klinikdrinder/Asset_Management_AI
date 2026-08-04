begin;

-- Extend the deployed strict migration_events.event_type vocabulary without
-- guessing or discarding any legacy value.  The replacement is performed in
-- one transaction under ALTER TABLE locking, so no unconstrained write window
-- is visible to other sessions.
do $migration$
declare
  event_type_attribute_number smallint;
  existing_constraint_oid oid;
  existing_expression text;
  unsupported_remainder text;
  existing_comment text;
  preserved_comment text;
  legacy_values text[];
  step10_values constant text[] := array[
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
  replacement_values text[];
  replacement_literals text;
begin
  select attribute_row.attnum
  into event_type_attribute_number
  from pg_catalog.pg_attribute as attribute_row
  where attribute_row.attrelid = 'public.migration_events'::regclass
    and attribute_row.attname = 'event_type'
    and not attribute_row.attisdropped;

  if event_type_attribute_number is null then
    raise exception 'migration_events.event_type column is missing';
  end if;

  select
    constraint_row.oid,
    pg_catalog.pg_get_expr(
      constraint_row.conbin,
      constraint_row.conrelid
    ),
    pg_catalog.obj_description(
      constraint_row.oid,
      'pg_constraint'
    )
  into
    existing_constraint_oid,
    existing_expression,
    existing_comment
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.migration_events'::regclass
    and constraint_row.conname = 'migration_events_event_type_check'
    and constraint_row.contype = 'c'
    and constraint_row.convalidated
    and constraint_row.conkey
      = array[event_type_attribute_number]::smallint[];

  if existing_constraint_oid is null or existing_expression is null then
    raise exception
      'Expected strict migration_events_event_type_check was not found';
  end if;

  -- Only accept a simple strict membership expression composed of event_type,
  -- equality, ANY/ARRAY, OR, text casts, literals, and grouping punctuation.
  -- Anything richer fails closed rather than being reinterpreted.
  unsupported_remainder := pg_catalog.regexp_replace(
    existing_expression,
    '''[A-Z][A-Z0-9_]*''(::text)?',
    '',
    'g'
  );
  unsupported_remainder := pg_catalog.regexp_replace(
    unsupported_remainder,
    '\m(event_type|ANY|ARRAY|OR)\M',
    '',
    'gi'
  );
  unsupported_remainder := pg_catalog.translate(
    unsupported_remainder,
    E' \t\n\r()[]{},=',
    ''
  );
  if unsupported_remainder <> '' then
    raise exception
      'Unsupported migration_events_event_type_check expression shape';
  end if;

  select pg_catalog.array_agg(distinct match_row.value order by match_row.value)
  into legacy_values
  from (
    select match_result[1] as value
    from pg_catalog.regexp_matches(
      existing_expression,
      '''([A-Z][A-Z0-9_]*)''',
      'g'
    ) as match_result
  ) as match_row;

  if legacy_values is null
    or pg_catalog.array_length(legacy_values, 1) is null
  then
    raise exception
      'Existing migration_events event_type vocabulary is empty';
  end if;

  select pg_catalog.array_agg(distinct value order by value)
  into replacement_values
  from pg_catalog.unnest(
    legacy_values || step10_values
  ) as value_row(value);

  select pg_catalog.string_agg(
    pg_catalog.quote_literal(value) || '::text',
    ', '
    order by value
  )
  into replacement_literals
  from pg_catalog.unnest(replacement_values) as value_row(value);

  if existing_comment like 'step10_preserved_legacy_event_types=%' then
    preserved_comment := existing_comment;
  else
    preserved_comment :=
      'step10_preserved_legacy_event_types='
      || pg_catalog.array_to_string(legacy_values, ',');
  end if;

  alter table public.migration_events
    drop constraint migration_events_event_type_check;

  execute pg_catalog.format(
    'alter table public.migration_events '
    || 'add constraint migration_events_event_type_check '
    || 'check (event_type = any (array[%s]))',
    replacement_literals
  );

  execute pg_catalog.format(
    'comment on constraint migration_events_event_type_check '
    || 'on public.migration_events is %L',
    preserved_comment
  );
end
$migration$;

commit;
