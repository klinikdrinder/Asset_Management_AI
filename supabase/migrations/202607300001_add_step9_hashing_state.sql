begin;

-- Step 9 Phase B stores one durable hashing lifecycle per source occurrence.
-- Canonical assets and asset_sources remain a separate Phase C concern.
alter table public.source_files
  add column if not exists hash_algorithm text,
  add column if not exists content_sha256 text,
  add column if not exists hash_status text not null default 'NOT_STARTED',
  add column if not exists hash_expected_bytes bigint,
  add column if not exists hash_observed_bytes bigint,
  add column if not exists hash_attempt_count integer not null default 0,
  add column if not exists hash_last_attempt_at timestamptz,
  add column if not exists hash_completed_at timestamptz,
  add column if not exists hash_failure_code text,
  add column if not exists hash_failure_reason text,
  add column if not exists hash_retryable boolean,
  add column if not exists hash_source_snapshot jsonb,
  add column if not exists hash_drive_modified_at timestamptz,
  add column if not exists hash_drive_size bigint,
  add column if not exists hash_drive_mime_type text,
  add column if not exists hash_drive_version text,
  add column if not exists hash_claim_owner text,
  add column if not exists hash_claimed_at timestamptz,
  add column if not exists hash_claim_expires_at timestamptz;

alter table public.source_files
  drop constraint if exists source_files_hash_algorithm_check,
  drop constraint if exists source_files_content_sha256_check,
  drop constraint if exists source_files_hash_status_check,
  drop constraint if exists source_files_hash_counts_check,
  drop constraint if exists source_files_hash_claim_check,
  drop constraint if exists source_files_hash_completion_check,
  drop constraint if exists source_files_hash_snapshot_check;

alter table public.source_files
  add constraint source_files_hash_algorithm_check
    check (hash_algorithm is null or hash_algorithm = 'SHA-256'),
  add constraint source_files_content_sha256_check
    check (
      content_sha256 is null
      or content_sha256 ~ '^[0-9a-f]{64}$'
    ),
  add constraint source_files_hash_status_check
    check (
      hash_status in (
        'NOT_STARTED',
        'QUEUED',
        'HASHING',
        'HASHED',
        'FAILED_RETRYABLE',
        'FAILED_PERMANENT',
        'SOURCE_CHANGED',
        'SOURCE_NOT_FOUND',
        'SOURCE_ACCESS_DENIED',
        'SOURCE_TRASHED'
      )
    ),
  add constraint source_files_hash_counts_check
    check (
      hash_attempt_count >= 0
      and (hash_expected_bytes is null or hash_expected_bytes >= 0)
      and (hash_observed_bytes is null or hash_observed_bytes >= 0)
    ),
  add constraint source_files_hash_claim_check
    check (
      (
        hash_claim_owner is null
        and hash_claimed_at is null
        and hash_claim_expires_at is null
      )
      or (
        hash_claim_owner is not null
        and hash_claimed_at is not null
        and hash_claim_expires_at > hash_claimed_at
      )
    ),
  add constraint source_files_hash_completion_check
    check (
      (
        hash_status = 'HASHED'
        and hash_algorithm = 'SHA-256'
        and content_sha256 is not null
        and hash_completed_at is not null
        and hash_retryable = false
        and hash_failure_code is null
        and hash_failure_reason is null
      )
      or (
        hash_status <> 'HASHED'
        and content_sha256 is null
        and hash_completed_at is null
      )
    ),
  add constraint source_files_hash_snapshot_check
    check (
      hash_source_snapshot is null
      or jsonb_typeof(hash_source_snapshot) = 'object'
    );

create index if not exists source_files_hash_work_queue_idx
  on public.source_files (hash_status, hash_claim_expires_at, id)
  where decision = 'TAKE' and processing_status = 'READY';

create index if not exists source_files_hash_claim_expiry_idx
  on public.source_files (hash_claim_expires_at)
  where hash_status = 'HASHING';

create index if not exists source_files_content_sha256_idx
  on public.source_files (hash_algorithm, content_sha256)
  where hash_status = 'HASHED';

comment on column public.source_files.content_sha256 is
  'Lowercase complete-file SHA-256 calculated by Step 9; never a partial or provider-supplied digest.';
comment on column public.source_files.hash_status is
  'Independent Step 9 hashing lifecycle; canonical asset creation occurs later.';
comment on column public.source_files.hash_source_snapshot is
  'Sanitized Drive metadata observed for source-change detection.';
comment on column public.source_files.hash_claim_expires_at is
  'Lease expiry allowing safe recovery after an interrupted worker.';

-- Atomic database-authoritative claim. An active lease cannot be stolen.
create or replace function public.claim_source_file_hash(
  requested_source_file_id uuid,
  requested_claim_owner text,
  requested_lease_seconds integer default 900
)
returns setof public.source_files
language sql
security invoker
set search_path = ''
as $$
  update public.source_files
  set
    hash_status = 'HASHING',
    hash_attempt_count = hash_attempt_count + 1,
    hash_last_attempt_at = now(),
    hash_claim_owner = nullif(btrim(requested_claim_owner), ''),
    hash_claimed_at = now(),
    hash_claim_expires_at = now()
      + make_interval(secs => requested_lease_seconds),
    hash_failure_code = null,
    hash_failure_reason = null,
    hash_retryable = null
  where id = requested_source_file_id
    and decision = 'TAKE'
    and processing_status = 'READY'
    and requested_lease_seconds between 30 and 3600
    and nullif(btrim(requested_claim_owner), '') is not null
    and (
      hash_status in ('NOT_STARTED', 'QUEUED', 'FAILED_RETRYABLE')
      or (
        hash_status = 'HASHING'
        and hash_claim_expires_at <= now()
      )
    )
  returning *;
$$;

revoke all on function public.claim_source_file_hash(uuid, text, integer)
  from public, anon, authenticated;
grant execute on function public.claim_source_file_hash(uuid, text, integer)
  to service_role;

create or replace function public.renew_source_file_hash_claim(
  requested_source_file_id uuid,
  requested_claim_owner text,
  requested_lease_seconds integer default 900
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
begin
  update public.source_files
  set hash_claim_expires_at = now()
    + make_interval(secs => requested_lease_seconds)
  where id = requested_source_file_id
    and hash_status = 'HASHING'
    and hash_claim_owner = requested_claim_owner
    and hash_claim_expires_at > now()
    and requested_lease_seconds between 30 and 3600;
  return found;
end;
$$;

revoke all on function public.renew_source_file_hash_claim(
  uuid, text, integer
) from public, anon, authenticated;
grant execute on function public.renew_source_file_hash_claim(
  uuid, text, integer
) to service_role;

commit;
