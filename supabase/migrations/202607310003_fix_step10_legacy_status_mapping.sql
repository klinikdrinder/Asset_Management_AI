begin;

-- Preserve the deployed strict legacy migration_events.status vocabulary and
-- add only missing canonical Step 10 audit classes.  The catalog parser accepts
-- only a simple, validated single-column membership CHECK and fails closed for
-- every other shape.
do $migration$
declare
  status_attribute_number smallint;
  matching_constraint_count integer;
  constraint_oid oid;
  constraint_name name;
  constraint_expression text;
  constraint_comment text;
  unsupported_remainder text;
  legacy_values text[];
  required_values constant text[] :=
    array['INFO', 'SUCCESS', 'WARNING', 'ERROR']::text[];
  replacement_values text[];
  replacement_literals text;
begin
  select attribute_row.attnum
  into status_attribute_number
  from pg_catalog.pg_attribute as attribute_row
  where attribute_row.attrelid = 'public.migration_events'::regclass
    and attribute_row.attname = 'status'
    and not attribute_row.attisdropped;

  if status_attribute_number is null then
    raise exception 'migration_events.status column is missing';
  end if;

  select pg_catalog.count(*)
  into matching_constraint_count
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.migration_events'::regclass
    and constraint_row.contype = 'c'
    and constraint_row.convalidated
    and constraint_row.conkey
      = array[status_attribute_number]::smallint[];

  if matching_constraint_count <> 1 then
    raise exception
      'Expected exactly one strict migration_events.status CHECK';
  end if;

  select
    constraint_row.oid,
    constraint_row.conname,
    pg_catalog.pg_get_expr(
      constraint_row.conbin,
      constraint_row.conrelid
    ),
    pg_catalog.obj_description(
      constraint_row.oid,
      'pg_constraint'
    )
  into
    constraint_oid,
    constraint_name,
    constraint_expression,
    constraint_comment
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.migration_events'::regclass
    and constraint_row.contype = 'c'
    and constraint_row.convalidated
    and constraint_row.conkey
      = array[status_attribute_number]::smallint[];

  if constraint_oid is null
    or constraint_name is null
    or constraint_expression is null
  then
    raise exception
      'Expected strict migration_events.status CHECK was not found';
  end if;

  unsupported_remainder := pg_catalog.regexp_replace(
    constraint_expression,
    '''[A-Z][A-Z0-9_]*''(::text)?',
    '',
    'g'
  );
  unsupported_remainder := pg_catalog.regexp_replace(
    unsupported_remainder,
    '\m(status|ANY|ARRAY|OR)\M',
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
      'Unsupported migration_events.status CHECK expression shape';
  end if;

  select pg_catalog.array_agg(
    distinct match_row.value order by match_row.value
  )
  into legacy_values
  from (
    select match_result[1] as value
    from pg_catalog.regexp_matches(
      constraint_expression,
      '''([A-Z][A-Z0-9_]*)''',
      'g'
    ) as match_result
  ) as match_row;

  if legacy_values is null
    or pg_catalog.array_length(legacy_values, 1) is null
  then
    raise exception 'Existing migration_events.status vocabulary is empty';
  end if;

  select pg_catalog.array_agg(distinct value order by value)
  into replacement_values
  from pg_catalog.unnest(
    legacy_values || required_values
  ) as value_row(value);

  if replacement_values <> legacy_values then
    select pg_catalog.string_agg(
      pg_catalog.quote_literal(value) || '::text',
      ', '
      order by value
    )
    into replacement_literals
    from pg_catalog.unnest(replacement_values) as value_row(value);

    execute pg_catalog.format(
      'alter table public.migration_events drop constraint %I',
      constraint_name
    );
    execute pg_catalog.format(
      'alter table public.migration_events add constraint %I '
      'check (status = any (array[%s]))',
      constraint_name,
      replacement_literals
    );
    if constraint_comment is not null then
      execute pg_catalog.format(
        'comment on constraint %I on public.migration_events is %L',
        constraint_name,
        constraint_comment
      );
    end if;
  end if;
end;
$migration$;

create or replace function public.set_step10_migration_event_legacy_status()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
begin
  if new.asset_destination_id is null
    or new.event_type not in (
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
    )
  then
    return new;
  end if;

  if new.status is not null then
    return new;
  end if;

  case new.event_status
    when 'INFO' then new.status := 'INFO';
    when 'SUCCESS' then new.status := 'SUCCESS';
    when 'WARNING' then new.status := 'WARNING';
    when 'ERROR' then new.status := 'ERROR';
    else
      raise exception
        'Unsupported Step 10 migration event_status contract';
  end case;

  return new;
end;
$function$;

revoke all on function public.set_step10_migration_event_legacy_status()
from public, anon, authenticated;

drop trigger if exists migration_events_set_step10_legacy_status
  on public.migration_events;
create trigger migration_events_set_step10_legacy_status
before insert on public.migration_events
for each row
execute function public.set_step10_migration_event_legacy_status();

commit;
