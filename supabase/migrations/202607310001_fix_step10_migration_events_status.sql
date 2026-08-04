begin;

-- The deployed migration_events table retains a required legacy `status`
-- column in addition to the canonical `event_status` column.  Step 10 audit
-- inserts intentionally use event_status, so populate only the legacy field
-- for recognized Step 10 destination-lifecycle events before constraints run.
--
-- The legacy status CHECK is deployment-specific and is not exposed by
-- PostgREST.  Resolve its existing vocabulary from pg_constraint instead of
-- weakening it or inventing a new value.  Unsupported contracts fail closed.
create or replace function public.set_step10_migration_event_legacy_status()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  legacy_status_constraint text;
  preferred_status text;
  fallback_status text;
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

  select string_agg(
    pg_catalog.pg_get_constraintdef(constraint_row.oid),
    ' '
  )
  into legacy_status_constraint
  from pg_catalog.pg_constraint as constraint_row
  join pg_catalog.pg_attribute as status_attribute
    on status_attribute.attrelid = constraint_row.conrelid
   and status_attribute.attname = 'status'
   and status_attribute.attnum = any(constraint_row.conkey)
  where constraint_row.conrelid = 'public.migration_events'::regclass
    and constraint_row.contype = 'c';

  case new.event_status
    when 'SUCCESS' then
      preferred_status := 'SUCCESS';
      fallback_status := 'COMPLETED';
    when 'ERROR' then
      preferred_status := 'ERROR';
      fallback_status := 'FAILED';
    when 'WARNING' then
      preferred_status := 'WARNING';
      fallback_status := 'SKIPPED';
    when 'INFO' then
      preferred_status := 'INFO';
      fallback_status := 'PENDING';
    else
      raise exception
        'Unsupported Step 10 migration event_status contract';
  end case;

  if legacy_status_constraint is null then
    -- A plain required text column accepts the canonical event status.
    new.status := preferred_status;
  elsif position(
    pg_catalog.quote_literal(preferred_status)
    in legacy_status_constraint
  ) > 0 then
    new.status := preferred_status;
  elsif position(
    pg_catalog.quote_literal(fallback_status)
    in legacy_status_constraint
  ) > 0 then
    new.status := fallback_status;
  else
    raise exception
      'Deployed migration_events.status contract has no safe Step 10 mapping';
  end if;

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
