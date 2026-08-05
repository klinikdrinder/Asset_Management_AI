begin;

-- Reuse sync_runs/scan_runs/source_files. Metadata holds the expanded counters;
-- these columns are only durable checkpoint/retry fields that cannot safely be
-- inferred after interruption.
alter table public.source_files
  add column if not exists sync_classification text,
  add column if not exists sync_processing_status text not null default 'IDLE',
  add column if not exists sync_attempt_count integer not null default 0,
  add column if not exists sync_retry_eligible boolean not null default false,
  add column if not exists sync_last_failure_reason text,
  add column if not exists sync_last_success_at timestamptz;

alter table public.source_files
  add constraint source_files_sync_classification_check check (
    sync_classification is null or sync_classification in
      ('NEW','CHANGED','UNCHANGED','INACCESSIBLE','REMOVED_FROM_SOURCE')
  ),
  add constraint source_files_sync_processing_status_check check (
    sync_processing_status in
      ('IDLE','CLASSIFIED','PROCESSING','COMPLETED','AWAITING_RETRY','FAILED')
  ),
  add constraint source_files_sync_attempt_count_check check
    (sync_attempt_count between 0 and 5);

create table if not exists public.synchronization_locks (
  lock_name text primary key,
  owner_run_id uuid not null references public.sync_runs(id) on delete cascade,
  acquired_at timestamptz not null default now(),
  expires_at timestamptz not null,
  constraint synchronization_locks_name_check check (btrim(lock_name) <> ''),
  constraint synchronization_locks_expiry_check check (expires_at > acquired_at)
);

alter table public.synchronization_locks enable row level security;
revoke all on table public.synchronization_locks from public, anon, authenticated;
grant select, insert, update, delete on table public.synchronization_locks to service_role;

create or replace function public.acquire_synchronization_lock(
  requested_lock_name text, requested_run_id uuid,
  requested_lease_seconds integer default 7200
) returns boolean language plpgsql security invoker set search_path = '' as $$
declare affected bigint;
begin
  if nullif(btrim(requested_lock_name),'') is null
     or requested_run_id is null
     or requested_lease_seconds not between 60 and 21600 then
    return false;
  end if;
  insert into public.synchronization_locks(lock_name,owner_run_id,expires_at)
  values (btrim(requested_lock_name),requested_run_id,
          now()+make_interval(secs=>requested_lease_seconds))
  on conflict(lock_name) do update set
    owner_run_id=excluded.owner_run_id, acquired_at=now(),
    expires_at=excluded.expires_at
  where public.synchronization_locks.expires_at <= now()
     or public.synchronization_locks.owner_run_id=excluded.owner_run_id;
  get diagnostics affected = row_count;
  return affected = 1;
end $$;

create or replace function public.release_synchronization_lock(
  requested_lock_name text, requested_run_id uuid
) returns boolean language plpgsql security invoker set search_path = '' as $$
declare affected bigint;
begin
  delete from public.synchronization_locks
  where lock_name=btrim(requested_lock_name) and owner_run_id=requested_run_id;
  get diagnostics affected = row_count;
  return affected = 1;
end $$;

revoke all on function public.acquire_synchronization_lock(text,uuid,integer) from public,anon,authenticated;
revoke all on function public.release_synchronization_lock(text,uuid) from public,anon,authenticated;
grant execute on function public.acquire_synchronization_lock(text,uuid,integer) to service_role;
grant execute on function public.release_synchronization_lock(text,uuid) to service_role;

create index if not exists source_files_sync_resume_idx on public.source_files
  (sync_processing_status,sync_retry_eligible,sync_attempt_count)
  where sync_processing_status in ('PROCESSING','AWAITING_RETRY','FAILED');

commit;
