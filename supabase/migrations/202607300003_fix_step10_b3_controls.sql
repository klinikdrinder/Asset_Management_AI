begin;

-- Replace the original unscoped claim signature so callers cannot
-- accidentally select the wrong overload after this corrective migration.
drop function if exists public.claim_asset_destinations(
  text, integer, integer
);
drop function if exists public.claim_asset_destinations(
  text, integer, integer, uuid[]
);

create or replace function public.claim_asset_destinations(
  requested_claim_owner text,
  requested_limit integer default 1,
  requested_lease_seconds integer default 900,
  requested_asset_destination_ids uuid[] default null,
  requested_destination_folder_id text default null
)
returns table (
  id uuid,
  asset_id uuid,
  selected_source_file_id uuid,
  destination_folder_id text,
  destination_drive_id text,
  destination_google_file_id text,
  destination_filename text,
  destination_relative_path text,
  migration_version text,
  idempotency_key text,
  upload_status text,
  verification_level text,
  expected_bytes bigint,
  transferred_bytes bigint,
  source_sha256 text,
  upload_attempt_count integer,
  last_attempt_at timestamptz,
  next_retry_at timestamptz,
  claim_owner text,
  claim_started_at timestamptz,
  claim_expires_at timestamptz,
  claim_renewed_at timestamptz
)
language sql
security invoker
set search_path = ''
as $$
  with candidates as (
    select
      candidate_source.id,
      candidate_source.upload_status as previous_status
    from public.asset_destinations as candidate_source
    where candidate_source.upload_attempt_count < 5
      and (
        requested_asset_destination_ids is null
        or candidate_source.id = any(requested_asset_destination_ids)
      )
      and (
        requested_destination_folder_id is null
        or candidate_source.destination_folder_id
          = requested_destination_folder_id
      )
      and (
        candidate_source.upload_status in (
          'NOT_STARTED',
          'QUEUED',
          'FAILED_RETRYABLE'
        )
        or (
          candidate_source.upload_status in ('CLAIMED', 'UPLOADING')
          and candidate_source.claim_expires_at <= now()
        )
      )
      and (
        candidate_source.claim_expires_at is null
        or candidate_source.claim_expires_at <= now()
      )
      and (
        candidate_source.next_retry_at is null
        or candidate_source.next_retry_at <= now()
      )
      and requested_limit between 1 and 100
      and requested_lease_seconds between 30 and 3600
      and nullif(btrim(requested_claim_owner), '') is not null
    order by
      case candidate_source.upload_status
        when 'QUEUED' then 0
        when 'FAILED_RETRYABLE' then 1
        else 2
      end,
      coalesce(
        candidate_source.next_retry_at,
        candidate_source.last_attempt_at,
        candidate_source.created_at
      ),
      candidate_source.created_at,
      candidate_source.id
    for update skip locked
    limit requested_limit
  ),
  claimed as (
    update public.asset_destinations as destination
    set
      upload_status = 'CLAIMED',
      upload_attempt_count = destination.upload_attempt_count + 1,
      last_attempt_at = now(),
      claim_owner = nullif(btrim(requested_claim_owner), ''),
      claim_started_at = now(),
      claim_expires_at = now()
        + make_interval(secs => requested_lease_seconds),
      claim_renewed_at = null,
      next_retry_at = null,
      retryable = null,
      failure_code = null,
      failure_reason = null
    from candidates
    where destination.id = candidates.id
    returning
      destination.id,
      destination.asset_id,
      destination.selected_source_file_id,
      destination.destination_folder_id,
      destination.destination_drive_id,
      destination.destination_google_file_id,
      destination.destination_filename,
      destination.destination_relative_path,
      destination.migration_version,
      destination.idempotency_key,
      destination.upload_status,
      destination.verification_level,
      destination.expected_bytes,
      destination.transferred_bytes,
      destination.source_sha256,
      destination.upload_attempt_count,
      destination.last_attempt_at,
      destination.next_retry_at,
      destination.claim_owner,
      destination.claim_started_at,
      destination.claim_expires_at,
      destination.claim_renewed_at,
      candidates.previous_status
  ),
  recovery_events as (
    insert into public.migration_events (
      asset_id,
      asset_destination_id,
      event_type,
      event_status,
      message,
      details
    )
    select
      claimed.asset_id,
      claimed.id,
      'CLAIM_RECOVERED',
      'SUCCESS',
      'Expired Step 10 claim recovered',
      jsonb_build_object('previous_status', claimed.previous_status)
    from claimed
    where claimed.previous_status in ('CLAIMED', 'UPLOADING')
    returning asset_destination_id
  )
  select
    claimed.id,
    claimed.asset_id,
    claimed.selected_source_file_id,
    claimed.destination_folder_id,
    claimed.destination_drive_id,
    claimed.destination_google_file_id,
    claimed.destination_filename,
    claimed.destination_relative_path,
    claimed.migration_version,
    claimed.idempotency_key,
    claimed.upload_status,
    claimed.verification_level,
    claimed.expected_bytes,
    claimed.transferred_bytes,
    claimed.source_sha256,
    claimed.upload_attempt_count,
    claimed.last_attempt_at,
    claimed.next_retry_at,
    claimed.claim_owner,
    claimed.claim_started_at,
    claimed.claim_expires_at,
    claimed.claim_renewed_at
  from claimed;
$$;

revoke all on function public.claim_asset_destinations(
  text, integer, integer, uuid[], text
) from public, anon, authenticated;
grant execute on function public.claim_asset_destinations(
  text, integer, integer, uuid[], text
) to service_role;

create or replace function public.renew_asset_destination_claim(
  requested_asset_destination_id uuid,
  requested_claim_owner text,
  requested_lease_seconds integer default 900
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  affected_asset_id uuid;
  renewed boolean := false;
begin
  update public.asset_destinations
  set
    claim_expires_at = now()
      + make_interval(secs => requested_lease_seconds),
    claim_renewed_at = now()
  where id = requested_asset_destination_id
    and upload_status in ('CLAIMED', 'UPLOADING')
    and claim_owner = requested_claim_owner
    and claim_expires_at > now()
    and requested_lease_seconds between 30 and 3600
  returning asset_id into affected_asset_id;

  renewed := found;
  if renewed then
    insert into public.migration_events (
      asset_id,
      asset_destination_id,
      event_type,
      event_status,
      message,
      details
    )
    values (
      affected_asset_id,
      requested_asset_destination_id,
      'CLAIM_RENEWED',
      'SUCCESS',
      'Step 10 claim renewed',
      jsonb_build_object('lease_seconds', requested_lease_seconds)
    );
  end if;
  return renewed;
end;
$$;

revoke all on function public.renew_asset_destination_claim(
  uuid, text, integer
) from public, anon, authenticated;
grant execute on function public.renew_asset_destination_claim(
  uuid, text, integer
) to service_role;

create or replace function public.release_asset_destination_claim(
  requested_asset_destination_id uuid,
  requested_claim_owner text
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  affected_asset_id uuid;
  released boolean := false;
begin
  update public.asset_destinations
  set
    upload_status = 'QUEUED',
    claim_owner = null,
    claim_started_at = null,
    claim_expires_at = null,
    claim_renewed_at = null
  where id = requested_asset_destination_id
    and upload_status in ('CLAIMED', 'UPLOADING')
    and claim_owner = requested_claim_owner
  returning asset_id into affected_asset_id;

  released := found;
  if released then
    insert into public.migration_events (
      asset_id,
      asset_destination_id,
      event_type,
      event_status,
      message,
      details
    )
    values (
      affected_asset_id,
      requested_asset_destination_id,
      'CLAIM_RELEASED',
      'SUCCESS',
      'Step 10 claim released',
      '{}'::jsonb
    );
  end if;
  return released;
end;
$$;

revoke all on function public.release_asset_destination_claim(
  uuid, text
) from public, anon, authenticated;
grant execute on function public.release_asset_destination_claim(
  uuid, text
) to service_role;

create or replace function public.log_asset_destination_initialized()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  insert into public.migration_events (
    asset_id,
    asset_destination_id,
    event_type,
    event_status,
    message,
    details
  )
  values (
    new.asset_id,
    new.id,
    'LIFECYCLE_INITIALIZED',
    'SUCCESS',
    'Step 10 destination lifecycle initialized',
    jsonb_build_object(
      'migration_version', new.migration_version,
      'verification_level', new.verification_level
    )
  );
  return new;
end;
$$;

revoke all on function public.log_asset_destination_initialized()
from public, anon, authenticated;

drop trigger if exists asset_destinations_log_initialization
  on public.asset_destinations;
create trigger asset_destinations_log_initialization
after insert on public.asset_destinations
for each row execute function public.log_asset_destination_initialized();

commit;
