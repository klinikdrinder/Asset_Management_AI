begin;

create extension if not exists pgcrypto;

-- Maintains updated_at consistently on mutable foundation records.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- Registered Google Drive source folders. This definition preserves the exact
-- column contract already present in the hosted Supabase project.
create table if not exists public.source_folders (
  id uuid primary key default gen_random_uuid(),
  source_name text not null,
  account_name text not null,
  folder_url text not null,
  google_folder_id text not null,
  active boolean not null default true,
  access_status text not null default 'PENDING',
  permission_role text not null default 'UNKNOWN',
  last_access_checked_at timestamptz,
  last_scan_at timestamptz,
  last_successful_scan_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint source_folders_access_status_check
    check (
      access_status in (
        'PENDING',
        'ACCESSIBLE',
        'INACCESSIBLE',
        'ERROR',
        'DISABLED'
      )
    ),
  constraint source_folders_permission_role_check
    check (
      permission_role in (
        'UNKNOWN',
        'VIEWER',
        'COMMENTER',
        'EDITOR',
        'OWNER'
      )
    )
);

-- A top-level synchronization execution spanning one or more source folders.
create table if not exists public.sync_runs (
  id uuid primary key default gen_random_uuid(),
  run_type text not null default 'MANUAL',
  status text not null default 'QUEUED',
  started_at timestamptz,
  completed_at timestamptz,
  folders_total integer not null default 0,
  folders_succeeded integer not null default 0,
  folders_failed integer not null default 0,
  files_discovered integer not null default 0,
  files_taken integer not null default 0,
  files_skipped integer not null default 0,
  files_uploaded integer not null default 0,
  duplicates_found integer not null default 0,
  files_failed integer not null default 0,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint sync_runs_run_type_check
    check (
      run_type in (
        'MANUAL',
        'INITIAL_MIGRATION',
        'DAILY_SYNC',
        'RETRY'
      )
    ),
  constraint sync_runs_status_check
    check (
      status in (
        'QUEUED',
        'RUNNING',
        'COMPLETED',
        'COMPLETED_WITH_ERRORS',
        'FAILED',
        'CANCELLED'
      )
    ),
  constraint sync_runs_counts_check
    check (
      folders_total >= 0
      and folders_succeeded >= 0
      and folders_failed >= 0
      and files_discovered >= 0
      and files_taken >= 0
      and files_skipped >= 0
      and files_uploaded >= 0
      and duplicates_found >= 0
      and files_failed >= 0
    ),
  constraint sync_runs_timestamps_check
    check (
      completed_at is null
      or started_at is null
      or completed_at >= started_at
    ),
  constraint sync_runs_metadata_object_check
    check (jsonb_typeof(metadata) = 'object')
);

-- One scan of one source folder, optionally belonging to a top-level sync run.
-- run_mode distinguishes non-copying verification from live migration work.
create table if not exists public.scan_runs (
  id uuid primary key default gen_random_uuid(),
  sync_run_id uuid references public.sync_runs(id) on delete set null,
  source_folder_id uuid not null
    references public.source_folders(id) on delete cascade,
  run_mode text not null default 'DRY_RUN',
  status text not null default 'QUEUED',
  started_at timestamptz,
  completed_at timestamptz,
  files_discovered integer not null default 0,
  files_taken integer not null default 0,
  files_skipped integer not null default 0,
  files_uploaded integer not null default 0,
  duplicates_found integer not null default 0,
  files_failed integer not null default 0,
  next_page_token text,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint scan_runs_run_mode_check
    check (run_mode in ('DRY_RUN', 'MIGRATION')),
  constraint scan_runs_status_check
    check (
      status in (
        'QUEUED',
        'RUNNING',
        'COMPLETED',
        'COMPLETED_WITH_ERRORS',
        'FAILED',
        'CANCELLED'
      )
    ),
  constraint scan_runs_counts_check
    check (
      files_discovered >= 0
      and files_taken >= 0
      and files_skipped >= 0
      and files_uploaded >= 0
      and duplicates_found >= 0
      and files_failed >= 0
    ),
  constraint scan_runs_timestamps_check
    check (
      completed_at is null
      or started_at is null
      or completed_at >= started_at
    ),
  constraint scan_runs_metadata_object_check
    check (jsonb_typeof(metadata) = 'object')
);

alter table public.scan_runs
  add column if not exists sync_run_id uuid;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.scan_runs'::regclass
      and conname = 'scan_runs_sync_run_id_fkey'
  ) then
    alter table public.scan_runs
      add constraint scan_runs_sync_run_id_fkey
      foreign key (sync_run_id)
      references public.sync_runs(id)
      on delete set null;
  end if;
end;
$$;

-- Google Drive files discovered beneath registered source folders, including
-- processing decisions and destination/duplicate outcomes.
create table if not exists public.source_files (
  id uuid primary key default gen_random_uuid(),
  source_folder_id uuid not null
    references public.source_folders(id) on delete cascade,
  last_scan_run_id uuid references public.scan_runs(id) on delete set null,
  google_file_id text not null,
  file_name text not null,
  mime_type text,
  file_extension text,
  size_bytes bigint,
  md5_checksum text,
  drive_created_at timestamptz,
  drive_modified_at timestamptz,
  web_view_link text,
  thumbnail_link text,
  parent_google_folder_id text,
  relative_path text,
  decision text not null default 'PENDING',
  processing_status text not null default 'DISCOVERED',
  processing_error text,
  skip_reason text,
  destination_file_id text,
  destination_web_view_link text,
  duplicate_of_source_file_id uuid
    references public.source_files(id) on delete set null,
  uploaded_at timestamptz,
  trashed boolean not null default false,
  is_missing boolean not null default false,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint source_files_folder_google_file_unique
    unique (source_folder_id, google_file_id),
  constraint source_files_size_bytes_check
    check (size_bytes is null or size_bytes >= 0),
  constraint source_files_md5_checksum_check
    check (
      md5_checksum is null
      or md5_checksum ~ '^[0-9A-Fa-f]{32}$'
    ),
  constraint source_files_decision_check
    check (decision in ('PENDING', 'TAKE', 'SKIP')),
  constraint source_files_processing_status_check
    check (
      processing_status in (
        'DISCOVERED',
        'QUEUED',
        'HASHING',
        'READY',
        'DUPLICATE',
        'UPLOADING',
        'UPLOADED',
        'SKIPPED',
        'FAILED',
        'INACCESSIBLE'
      )
    ),
  constraint source_files_seen_timestamps_check
    check (last_seen_at >= first_seen_at),
  constraint source_files_metadata_object_check
    check (jsonb_typeof(metadata) = 'object')
);

-- A unique canonical file after exact duplicate detection. content_hash is a
-- SHA-256 digest when available; the partial unique index permits pending rows.
create table if not exists public.assets (
  id uuid primary key default gen_random_uuid(),
  content_hash text,
  file_name text not null,
  mime_type text,
  file_extension text,
  size_bytes bigint,
  storage_bucket text,
  storage_path text,
  upload_status text not null default 'PENDING',
  uploaded_at timestamptz,
  last_verified_at timestamptz,
  upload_error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint assets_content_hash_check
    check (
      content_hash is null
      or content_hash ~ '^[0-9A-Fa-f]{64}$'
    ),
  constraint assets_size_bytes_check
    check (size_bytes is null or size_bytes >= 0),
  constraint assets_upload_status_check
    check (
      upload_status in (
        'PENDING',
        'UPLOADING',
        'UPLOADED',
        'FAILED',
        'MISSING',
        'VERIFICATION_REQUIRED'
      )
    ),
  constraint assets_storage_location_check
    check (
      (storage_bucket is null and storage_path is null)
      or (storage_bucket is not null and storage_path is not null)
    ),
  constraint assets_metadata_object_check
    check (jsonb_typeof(metadata) = 'object')
);

-- Connects each canonical asset to one or more original source files. A source
-- file may resolve to only one canonical asset.
create table if not exists public.asset_sources (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  source_file_id uuid not null
    references public.source_files(id) on delete cascade,
  relationship_type text not null default 'ORIGINAL',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_sources_asset_source_unique
    unique (asset_id, source_file_id),
  constraint asset_sources_source_file_unique
    unique (source_file_id),
  constraint asset_sources_relationship_type_check
    check (relationship_type in ('ORIGINAL', 'DUPLICATE'))
);

-- Append-oriented operational events for synchronization, scanning, duplicate
-- detection, uploads, retries, and failures.
create table if not exists public.migration_events (
  id uuid primary key default gen_random_uuid(),
  sync_run_id uuid references public.sync_runs(id) on delete set null,
  scan_run_id uuid references public.scan_runs(id) on delete set null,
  source_folder_id uuid
    references public.source_folders(id) on delete set null,
  source_file_id uuid references public.source_files(id) on delete set null,
  asset_id uuid references public.assets(id) on delete set null,
  event_type text not null,
  event_status text not null default 'INFO',
  message text,
  details jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint migration_events_event_status_check
    check (event_status in ('INFO', 'SUCCESS', 'WARNING', 'ERROR')),
  constraint migration_events_details_object_check
    check (jsonb_typeof(details) = 'object')
);

comment on table public.source_folders is
  'Approved Google Drive folders scanned by the KDI media workflow.';
comment on table public.sync_runs is
  'Top-level manual, initial, daily, or retry synchronization executions.';
comment on table public.scan_runs is
  'Per-source-folder scans performed during dry runs or migrations.';
comment on table public.source_files is
  'Google Drive files, decisions, processing state, and copy outcomes.';
comment on table public.assets is
  'Canonical unique files produced after exact duplicate detection.';
comment on table public.asset_sources is
  'Links canonical assets to their original or duplicate source files.';
comment on table public.migration_events is
  'Operational event log for the media migration and sync workflows.';
comment on column public.source_files.md5_checksum is
  'Google Drive MD5 checksum used with size_bytes for exact duplicates.';
comment on column public.assets.content_hash is
  'Canonical SHA-256 content digest when hashing has completed.';

-- Enforce the required source-folder status contract on future writes without
-- invalidating deployment solely because legacy rows have not yet been audited.
do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.source_folders'::regclass
      and conname = 'source_folders_access_status_check'
  ) then
    alter table public.source_folders
      add constraint source_folders_access_status_check
      check (
        access_status in (
          'PENDING',
          'ACCESSIBLE',
          'INACCESSIBLE',
          'ERROR',
          'DISABLED'
        )
      ) not valid;
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.source_folders'::regclass
      and conname = 'source_folders_permission_role_check'
  ) then
    alter table public.source_folders
      add constraint source_folders_permission_role_check
      check (
        permission_role in (
          'UNKNOWN',
          'VIEWER',
          'COMMENTER',
          'EDITOR',
          'OWNER'
        )
      ) not valid;
  end if;
end;
$$;

create unique index if not exists source_folders_google_folder_id_unique
  on public.source_folders (google_folder_id);
create index if not exists source_folders_active_access_status_idx
  on public.source_folders (active, access_status);
create index if not exists source_folders_account_name_idx
  on public.source_folders (account_name);
create index if not exists source_folders_last_scan_at_idx
  on public.source_folders (last_scan_at desc);

create index if not exists sync_runs_status_created_at_idx
  on public.sync_runs (status, created_at desc);
create index if not exists sync_runs_run_type_created_at_idx
  on public.sync_runs (run_type, created_at desc);

create index if not exists scan_runs_sync_run_id_idx
  on public.scan_runs (sync_run_id);
create index if not exists scan_runs_source_folder_created_at_idx
  on public.scan_runs (source_folder_id, created_at desc);
create index if not exists scan_runs_status_created_at_idx
  on public.scan_runs (status, created_at desc);

create index if not exists source_files_last_scan_run_id_idx
  on public.source_files (last_scan_run_id);
create index if not exists source_files_google_file_id_idx
  on public.source_files (google_file_id);
create index if not exists source_files_folder_decision_status_idx
  on public.source_files (
    source_folder_id,
    decision,
    processing_status
  );
create index if not exists source_files_exact_duplicate_idx
  on public.source_files (md5_checksum, size_bytes)
  where md5_checksum is not null and size_bytes is not null;
create index if not exists source_files_destination_file_id_idx
  on public.source_files (destination_file_id)
  where destination_file_id is not null;

create unique index if not exists assets_content_hash_unique
  on public.assets (content_hash)
  where content_hash is not null;
create unique index if not exists assets_storage_location_unique
  on public.assets (storage_bucket, storage_path)
  where storage_bucket is not null and storage_path is not null;
create index if not exists assets_upload_status_created_at_idx
  on public.assets (upload_status, created_at desc);

create index if not exists asset_sources_asset_id_idx
  on public.asset_sources (asset_id);
create index if not exists asset_sources_relationship_type_idx
  on public.asset_sources (relationship_type);

create index if not exists migration_events_sync_run_occurred_at_idx
  on public.migration_events (sync_run_id, occurred_at desc);
create index if not exists migration_events_scan_run_occurred_at_idx
  on public.migration_events (scan_run_id, occurred_at desc);
create index if not exists migration_events_source_folder_occurred_at_idx
  on public.migration_events (source_folder_id, occurred_at desc);
create index if not exists migration_events_source_file_occurred_at_idx
  on public.migration_events (source_file_id, occurred_at desc);
create index if not exists migration_events_asset_occurred_at_idx
  on public.migration_events (asset_id, occurred_at desc);
create index if not exists migration_events_type_status_occurred_at_idx
  on public.migration_events (
    event_type,
    event_status,
    occurred_at desc
  );

drop trigger if exists source_folders_set_updated_at
  on public.source_folders;
create trigger source_folders_set_updated_at
before update on public.source_folders
for each row execute function public.set_updated_at();

drop trigger if exists sync_runs_set_updated_at on public.sync_runs;
create trigger sync_runs_set_updated_at
before update on public.sync_runs
for each row execute function public.set_updated_at();

drop trigger if exists scan_runs_set_updated_at on public.scan_runs;
create trigger scan_runs_set_updated_at
before update on public.scan_runs
for each row execute function public.set_updated_at();

drop trigger if exists source_files_set_updated_at on public.source_files;
create trigger source_files_set_updated_at
before update on public.source_files
for each row execute function public.set_updated_at();

drop trigger if exists assets_set_updated_at on public.assets;
create trigger assets_set_updated_at
before update on public.assets
for each row execute function public.set_updated_at();

drop trigger if exists asset_sources_set_updated_at
  on public.asset_sources;
create trigger asset_sources_set_updated_at
before update on public.asset_sources
for each row execute function public.set_updated_at();

drop trigger if exists migration_events_set_updated_at
  on public.migration_events;
create trigger migration_events_set_updated_at
before update on public.migration_events
for each row execute function public.set_updated_at();

alter table public.source_folders enable row level security;
alter table public.sync_runs enable row level security;
alter table public.scan_runs enable row level security;
alter table public.source_files enable row level security;
alter table public.assets enable row level security;
alter table public.asset_sources enable row level security;
alter table public.migration_events enable row level security;

-- Authenticated reads require an explicit app_metadata claim. This satisfies
-- authenticated-read access without exposing media metadata to every user.
drop policy if exists "source_folders_authorized_read"
  on public.source_folders;
create policy "source_folders_authorized_read"
on public.source_folders for select
to authenticated
using (
  coalesce(
    (select auth.jwt() -> 'app_metadata' ->> 'kdi_media_reader') = 'true',
    false
  )
);

drop policy if exists "sync_runs_authorized_read" on public.sync_runs;
create policy "sync_runs_authorized_read"
on public.sync_runs for select
to authenticated
using (
  coalesce(
    (select auth.jwt() -> 'app_metadata' ->> 'kdi_media_reader') = 'true',
    false
  )
);

drop policy if exists "scan_runs_authorized_read" on public.scan_runs;
create policy "scan_runs_authorized_read"
on public.scan_runs for select
to authenticated
using (
  coalesce(
    (select auth.jwt() -> 'app_metadata' ->> 'kdi_media_reader') = 'true',
    false
  )
);

drop policy if exists "source_files_authorized_read"
  on public.source_files;
create policy "source_files_authorized_read"
on public.source_files for select
to authenticated
using (
  coalesce(
    (select auth.jwt() -> 'app_metadata' ->> 'kdi_media_reader') = 'true',
    false
  )
);

drop policy if exists "assets_authorized_read" on public.assets;
create policy "assets_authorized_read"
on public.assets for select
to authenticated
using (
  coalesce(
    (select auth.jwt() -> 'app_metadata' ->> 'kdi_media_reader') = 'true',
    false
  )
);

drop policy if exists "asset_sources_authorized_read"
  on public.asset_sources;
create policy "asset_sources_authorized_read"
on public.asset_sources for select
to authenticated
using (
  coalesce(
    (select auth.jwt() -> 'app_metadata' ->> 'kdi_media_reader') = 'true',
    false
  )
);

drop policy if exists "migration_events_authorized_read"
  on public.migration_events;
create policy "migration_events_authorized_read"
on public.migration_events for select
to authenticated
using (
  coalesce(
    (select auth.jwt() -> 'app_metadata' ->> 'kdi_media_reader') = 'true',
    false
  )
);

revoke all on table public.source_folders from anon;
revoke all on table public.sync_runs from anon;
revoke all on table public.scan_runs from anon;
revoke all on table public.source_files from anon;
revoke all on table public.assets from anon;
revoke all on table public.asset_sources from anon;
revoke all on table public.migration_events from anon;

grant select on table public.source_folders to authenticated;
grant select on table public.sync_runs to authenticated;
grant select on table public.scan_runs to authenticated;
grant select on table public.source_files to authenticated;
grant select on table public.assets to authenticated;
grant select on table public.asset_sources to authenticated;
grant select on table public.migration_events to authenticated;

grant select, insert, update, delete
  on table public.source_folders,
    public.sync_runs,
    public.scan_runs,
    public.source_files,
    public.assets,
    public.asset_sources,
    public.migration_events
  to service_role;

create or replace view public.source_folder_summary
with (security_invoker = true)
as
select
  sf.id,
  sf.source_name,
  sf.account_name,
  sf.folder_url,
  sf.google_folder_id,
  sf.active,
  sf.access_status,
  sf.permission_role,
  sf.last_access_checked_at,
  sf.last_scan_at,
  sf.last_successful_scan_at,
  sf.notes,
  sf.created_at,
  sf.updated_at,
  coalesce(file_totals.total_files, 0)::bigint as total_files,
  coalesce(file_totals.take_files, 0)::bigint as take_files,
  coalesce(file_totals.skip_files, 0)::bigint as skip_files,
  coalesce(file_totals.uploaded_files, 0)::bigint as uploaded_files,
  coalesce(file_totals.duplicate_files, 0)::bigint as duplicate_files,
  coalesce(file_totals.failed_files, 0)::bigint as failed_files,
  coalesce(asset_totals.asset_count, 0)::bigint as asset_count,
  latest_scan.id as latest_scan_run_id,
  latest_scan.status as latest_scan_status,
  latest_scan.started_at as latest_scan_started_at,
  latest_scan.completed_at as latest_scan_completed_at
from public.source_folders sf
left join lateral (
  select
    count(*) as total_files,
    count(*) filter (where source_file.decision = 'TAKE') as take_files,
    count(*) filter (where source_file.decision = 'SKIP') as skip_files,
    count(*) filter (
      where source_file.processing_status = 'UPLOADED'
    ) as uploaded_files,
    count(*) filter (
      where source_file.processing_status = 'DUPLICATE'
    ) as duplicate_files,
    count(*) filter (
      where source_file.processing_status = 'FAILED'
    ) as failed_files
  from public.source_files source_file
  where source_file.source_folder_id = sf.id
) file_totals on true
left join lateral (
  select count(distinct asset_source.asset_id) as asset_count
  from public.source_files source_file
  join public.asset_sources asset_source
    on asset_source.source_file_id = source_file.id
  where source_file.source_folder_id = sf.id
) asset_totals on true
left join lateral (
  select
    scan.id,
    scan.status,
    scan.started_at,
    scan.completed_at
  from public.scan_runs scan
  where scan.source_folder_id = sf.id
  order by scan.created_at desc, scan.id desc
  limit 1
) latest_scan on true;

comment on view public.source_folder_summary is
  'Source-folder access, scan, file-processing, and asset totals.';

revoke all on table public.source_folder_summary from anon;
grant select on table public.source_folder_summary to authenticated;
grant select on table public.source_folder_summary to service_role;

revoke all on function public.set_updated_at() from public;

commit;
