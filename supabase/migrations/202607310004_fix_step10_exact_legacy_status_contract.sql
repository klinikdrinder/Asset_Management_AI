begin;

do $migration$
declare
  status_attribute_number smallint;
  status_required boolean;
  constraint_expression text;
  constraint_comment text;
  unsupported_remainder text;
  deployed_values text[];
  original_values constant text[] := array[
    'QUEUED',
    'RUNNING',
    'SUCCESS',
    'SKIPPED',
    'DUPLICATE',
    'FAILED',
    'RETRYING',
    'CANCELLED'
  ]::text[];
  replacement_values constant text[] := array[
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
begin
  select attribute_row.attnum, attribute_row.attnotnull
  into status_attribute_number, status_required
  from pg_catalog.pg_attribute as attribute_row
  where attribute_row.attrelid = 'public.migration_events'::regclass
    and attribute_row.attname = 'status'
    and not attribute_row.attisdropped;

  if status_attribute_number is null then
    raise exception 'migration_events.status column is missing';
  end if;
  if not status_required then
    raise exception 'migration_events.status must remain NOT NULL';
  end if;

  select
    pg_catalog.pg_get_expr(
      constraint_row.conbin,
      constraint_row.conrelid
    ),
    pg_catalog.obj_description(
      constraint_row.oid,
      'pg_constraint'
    )
  into constraint_expression, constraint_comment
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.migration_events'::regclass
    and constraint_row.conname = 'migration_events_status_check'
    and constraint_row.contype = 'c'
    and constraint_row.convalidated
    and constraint_row.conkey
      = array[status_attribute_number]::smallint[];

  if constraint_expression is null then
    raise exception
      'Expected strict migration_events_status_check was not found';
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
      'Unsupported migration_events_status_check expression shape';
  end if;

  select pg_catalog.array_agg(
    distinct match_row.value order by match_row.value
  )
  into deployed_values
  from (
    select match_result[1] as value
    from pg_catalog.regexp_matches(
      constraint_expression,
      '''([A-Z][A-Z0-9_]*)''',
      'g'
    ) as match_result
  ) as match_row;

  if deployed_values <> (
    select pg_catalog.array_agg(value order by value)
    from pg_catalog.unnest(original_values) as value_row(value)
  ) and deployed_values <> (
    select pg_catalog.array_agg(value order by value)
    from pg_catalog.unnest(replacement_values) as value_row(value)
  ) then
    raise exception
      'Unexpected migration_events.status vocabulary';
  end if;

  if exists (
    select 1
    from public.migration_events as event_row
    where event_row.status <> all (replacement_values)
  ) then
    raise exception
      'Existing migration_events rows violate the replacement status contract';
  end if;

  if not (
    deployed_values = (
      select pg_catalog.array_agg(value order by value)
      from pg_catalog.unnest(replacement_values) as value_row(value)
    )
  ) then
    alter table public.migration_events
      drop constraint migration_events_status_check;
    alter table public.migration_events
      add constraint migration_events_status_check
      check (
        status in (
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
        )
      );
    if constraint_comment is not null then
      execute pg_catalog.format(
        'comment on constraint migration_events_status_check '
        'on public.migration_events is %L',
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
