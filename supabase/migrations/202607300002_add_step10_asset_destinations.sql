begin;

-- One durable Step 10 lifecycle per canonical asset and destination root.
create table if not exists public.asset_destinations (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete restrict,
  selected_source_file_id uuid not null
    references public.source_files(id) on delete restrict,
  destination_folder_id text not null,
  destination_drive_id text,
  destination_google_file_id text,
  destination_url text,
  destination_filename text not null,
  destination_relative_path text not null,
  migration_version text not null,
  idempotency_key text not null,
  upload_status text not null default 'NOT_STARTED',
  verification_level text not null default 'NONE',
  expected_bytes bigint not null,
  transferred_bytes bigint not null default 0,
  destination_reported_bytes bigint,
  source_sha256 text not null,
  provider_checksum_type text,
  provider_checksum_value text,
  upload_attempt_count integer not null default 0,
  last_attempt_at timestamptz,
  next_retry_at timestamptz,
  upload_started_at timestamptz,
  upload_completed_at timestamptz,
  verified_at timestamptz,
  retryable boolean,
  failure_code text,
  failure_reason text,
  source_metadata_snapshot jsonb not null default '{}'::jsonb,
  destination_metadata_snapshot jsonb not null default '{}'::jsonb,
  claim_owner text,
  claim_started_at timestamptz,
  claim_expires_at timestamptz,
  claim_renewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.asset_destinations
  drop constraint if exists asset_destinations_asset_folder_unique,
  drop constraint if exists asset_destinations_idempotency_key_unique,
  drop constraint if exists asset_destinations_upload_status_check,
  drop constraint if exists asset_destinations_verification_level_check,
  drop constraint if exists asset_destinations_counts_check,
  drop constraint if exists asset_destinations_sha256_check,
  drop constraint if exists asset_destinations_snapshots_check,
  drop constraint if exists asset_destinations_claim_check,
  drop constraint if exists asset_destinations_completion_check,
  drop constraint if exists asset_destinations_failure_check;

alter table public.asset_destinations
  add constraint asset_destinations_asset_folder_unique
    unique (asset_id, destination_folder_id),
  add constraint asset_destinations_idempotency_key_unique
    unique (idempotency_key),
  add constraint asset_destinations_upload_status_check
    check (
      upload_status in (
        'NOT_STARTED',
        'QUEUED',
        'CLAIMED',
        'UPLOADING',
        'UPLOADED',
        'VERIFIED',
        'FAILED_RETRYABLE',
        'FAILED_PERMANENT',
        'SOURCE_CHANGED',
        'SOURCE_NOT_FOUND',
        'SOURCE_ACCESS_DENIED',
        'DESTINATION_ACCESS_DENIED',
        'DESTINATION_CONFLICT',
        'MANUAL_REVIEW_REQUIRED'
      )
    ),
  add constraint asset_destinations_verification_level_check
    check (
      verification_level in (
        'NONE',
        'SOURCE_HASH_VERIFIED',
        'TRANSFER_BYTE_COUNT_VERIFIED',
        'DESTINATION_METADATA_VERIFIED',
        'PROVIDER_CHECKSUM_VERIFIED',
        'DESTINATION_SHA256_VERIFIED'
      )
    ),
  add constraint asset_destinations_counts_check
    check (
      expected_bytes >= 0
      and transferred_bytes >= 0
      and (
        destination_reported_bytes is null
        or destination_reported_bytes >= 0
      )
      and upload_attempt_count >= 0
    ),
  add constraint asset_destinations_sha256_check
    check (source_sha256 ~ '^[0-9a-f]{64}$'),
  add constraint asset_destinations_snapshots_check
    check (
      jsonb_typeof(source_metadata_snapshot) = 'object'
      and jsonb_typeof(destination_metadata_snapshot) = 'object'
    ),
  add constraint asset_destinations_claim_check
    check (
      (
        claim_owner is null
        and claim_started_at is null
        and claim_expires_at is null
        and claim_renewed_at is null
      )
      or (
        claim_owner is not null
        and claim_started_at is not null
        and claim_expires_at > claim_started_at
      )
    ),
  add constraint asset_destinations_completion_check
    check (
      (
        upload_status not in ('UPLOADED', 'VERIFIED')
      )
      or (
        upload_status = 'UPLOADED'
        and destination_google_file_id is not null
        and upload_completed_at is not null
      )
      or (
        upload_status = 'VERIFIED'
        and destination_google_file_id is not null
        and upload_completed_at is not null
        and verified_at is not null
        and verification_level in (
          'DESTINATION_METADATA_VERIFIED',
          'PROVIDER_CHECKSUM_VERIFIED',
          'DESTINATION_SHA256_VERIFIED'
        )
      )
    ),
  add constraint asset_destinations_failure_check
    check (
      (
        upload_status = 'FAILED_RETRYABLE'
        and retryable = true
        and failure_code is not null
      )
      or (
        upload_status <> 'FAILED_RETRYABLE'
      )
    );

create unique index if not exists
  asset_destinations_google_file_id_unique
  on public.asset_destinations (destination_google_file_id)
  where destination_google_file_id is not null;

create index if not exists asset_destinations_upload_status_idx
  on public.asset_destinations (upload_status, id);
create index if not exists asset_destinations_verification_level_idx
  on public.asset_destinations (verification_level, id);
create index if not exists asset_destinations_retryable_idx
  on public.asset_destinations (retryable, next_retry_at, upload_status)
  where retryable = true;
create index if not exists asset_destinations_retry_schedule_idx
  on public.asset_destinations (next_retry_at, created_at, id)
  where upload_status = 'FAILED_RETRYABLE';
create index if not exists asset_destinations_claim_expiry_idx
  on public.asset_destinations (claim_expires_at)
  where claim_expires_at is not null;
create index if not exists asset_destinations_asset_id_idx
  on public.asset_destinations (asset_id);
create index if not exists asset_destinations_source_file_id_idx
  on public.asset_destinations (selected_source_file_id);
create index if not exists asset_destinations_folder_id_idx
  on public.asset_destinations (destination_folder_id);
create index if not exists asset_destinations_google_file_id_idx
  on public.asset_destinations (destination_google_file_id)
  where destination_google_file_id is not null;

drop trigger if exists asset_destinations_set_updated_at
  on public.asset_destinations;
create trigger asset_destinations_set_updated_at
before update on public.asset_destinations
for each row execute function public.set_updated_at();

comment on table public.asset_destinations is
  'Durable Step 10 upload and verification lifecycle per asset and destination.';
comment on column public.asset_destinations.source_sha256 is
  'Complete source SHA-256 inherited from Step 9; provider checksums are separate.';
comment on column public.asset_destinations.verification_level is
  'Independent evidence level; DESTINATION_SHA256_VERIFIED requires a complete destination re-download.';
comment on column public.asset_destinations.idempotency_key is
  'Deterministic non-secret key derived from asset, destination, and migration version.';

-- Append-only events can reference the durable destination lifecycle.
alter table public.migration_events
  add column if not exists asset_destination_id uuid;

do $migration$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.migration_events'::regclass
      and conname = 'migration_events_asset_destination_id_fkey'
  ) then
    alter table public.migration_events
      add constraint migration_events_asset_destination_id_fkey
      foreign key (asset_destination_id)
      references public.asset_destinations(id)
      on delete set null;
  end if;
end
$migration$;

create index if not exists migration_events_asset_destination_idx
  on public.migration_events (asset_destination_id, occurred_at desc)
  where asset_destination_id is not null;

-- Atomic bounded claims use database time and SKIP LOCKED.
create or replace function public.claim_asset_destinations(
  requested_claim_owner text,
  requested_limit integer default 1,
  requested_lease_seconds integer default 900
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
    select candidate_source.id
    from public.asset_destinations as candidate_source
    where candidate_source.upload_attempt_count < 5
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
  )
  update public.asset_destinations as destination
  set
    upload_status = 'CLAIMED',
    upload_attempt_count = upload_attempt_count + 1,
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
    destination.claim_renewed_at;
$$;

revoke all on function public.claim_asset_destinations(
  text, integer, integer
) from public, anon, authenticated;
grant execute on function public.claim_asset_destinations(
  text, integer, integer
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
    and requested_lease_seconds between 30 and 3600;
  return found;
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
    and claim_owner = requested_claim_owner;
  return found;
end;
$$;

revoke all on function public.release_asset_destination_claim(
  uuid, text
) from public, anon, authenticated;
grant execute on function public.release_asset_destination_claim(
  uuid, text
) to service_role;

alter table public.asset_destinations enable row level security;

drop policy if exists "asset_destinations_authorized_read"
  on public.asset_destinations;
create policy "asset_destinations_authorized_read"
on public.asset_destinations for select
to authenticated
using (
  coalesce(
    (auth.jwt() -> 'app_metadata' ->> 'kdi_media_access')::boolean,
    false
  )
);

revoke all on table public.asset_destinations from public, anon;
revoke insert, update, delete, truncate
  on table public.asset_destinations from authenticated;
grant select on table public.asset_destinations to authenticated;
grant all on table public.asset_destinations to service_role;

commit;
