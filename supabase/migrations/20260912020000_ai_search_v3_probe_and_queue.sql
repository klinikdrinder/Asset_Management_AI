-- AI Search v3 (job 1) — pre-flight probe + DB-backed work queue.
-- Already applied to project wcqqjpndlwsvatjuqnol via the Management API during
-- job 1; kept here for reproducibility in other environments. Idempotent.

begin;

-- Pre-flight media probe results (one row per asset).
create table if not exists public.asset_media_probe (
  asset_id uuid primary key references public.assets(id) on delete cascade,
  media text, source_folder text, status text, reason text,
  frames_extracted int, file_size_bytes bigint,
  probed_at timestamptz not null default now());
create index if not exists asset_media_probe_status_idx on public.asset_media_probe(status);

-- Work queue: one row per asset per run.
create table if not exists public.ai_search_job_queue (
  id bigserial primary key,
  run_id uuid not null,
  asset_id uuid not null references public.assets(id) on delete cascade,
  state text not null default 'QUEUED' check (state in ('QUEUED','CLAIMED','DONE','FAILED')),
  claimed_by text, claimed_at timestamptz, claim_expires_at timestamptz,
  attempts int not null default 0, last_error text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(run_id, asset_id));
create index if not exists ai_search_job_queue_run_state_idx on public.ai_search_job_queue(run_id, state);

-- Single-instance lock + heartbeat progress.
create table if not exists public.ai_search_run_lock (
  lock_name text primary key, holder text, run_id uuid,
  acquired_at timestamptz, heartbeat_at timestamptz,
  processed int not null default 0, total int not null default 0);

-- Atomic claim: QUEUED or expired-CLAIMED, one worker per row (FOR UPDATE SKIP LOCKED).
create or replace function public.ai_search_claim_jobs(p_run uuid, p_worker text, p_lease int, p_limit int)
returns setof uuid language plpgsql as $$
begin
  return query
  with cte as (
    select id from public.ai_search_job_queue
    where run_id=p_run and (state='QUEUED' or (state='CLAIMED' and claim_expires_at < now()))
    order by id for update skip locked limit p_limit)
  update public.ai_search_job_queue q
    set state='CLAIMED', claimed_by=p_worker, claimed_at=now(),
        claim_expires_at=now() + make_interval(secs => p_lease),
        attempts=attempts+1, updated_at=now()
  from cte where q.id=cte.id
  returning q.asset_id;
end $$;

-- Single-instance lock: grants only if free or stale.
create or replace function public.ai_search_acquire_lock(p_name text, p_holder text, p_run uuid, p_stale int)
returns boolean language plpgsql as $$
declare cur text;
begin
  insert into public.ai_search_run_lock(lock_name,holder,run_id,acquired_at,heartbeat_at)
  values(p_name,p_holder,p_run,now(),now())
  on conflict(lock_name) do update set holder=excluded.holder, run_id=excluded.run_id,
     acquired_at=now(), heartbeat_at=now()
  where public.ai_search_run_lock.heartbeat_at < now() - make_interval(secs => p_stale);
  select holder into cur from public.ai_search_run_lock where lock_name=p_name;
  return cur = p_holder;
end $$;

grant select,insert,update,delete on
  public.asset_media_probe, public.ai_search_job_queue, public.ai_search_run_lock to service_role;
grant usage, select on sequence public.ai_search_job_queue_id_seq to service_role;
grant execute on function public.ai_search_claim_jobs(uuid,text,int,int) to service_role;
grant execute on function public.ai_search_acquire_lock(text,text,uuid,int) to service_role;

commit;
