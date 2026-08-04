begin;

-- Repair migration for the already-existing foundation tables.
-- This file deliberately contains no CREATE TABLE, DROP TABLE, TRUNCATE, or DELETE.
-- Every exception aborts the transaction before an unsafe contract change is made.

create extension if not exists pgcrypto;

-- Standardize the updated_at trigger function.
-- CREATE OR REPLACE preserves dependent triggers and uses the canonical
-- PL/pgSQL assignment form accepted by the final verifier.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
begin
  new.updated_at := now();
  return new;
end;
$function$;

-- Add missing source_folders columns.  Columns with universal defaults are
-- added with those defaults so existing rows receive safe values.
alter table public.source_folders
  add column if not exists id uuid default gen_random_uuid(),
  add column if not exists source_name text,
  add column if not exists account_name text,
  add column if not exists folder_url text,
  add column if not exists google_folder_id text,
  add column if not exists active boolean default true,
  add column if not exists access_status text default 'PENDING',
  add column if not exists permission_role text default 'UNKNOWN',
  add column if not exists last_access_checked_at timestamptz,
  add column if not exists last_scan_at timestamptz,
  add column if not exists last_successful_scan_at timestamptz,
  add column if not exists notes text,
  add column if not exists created_at timestamptz default now(),
  add column if not exists updated_at timestamptz default now();

-- Restore source_folders defaults, including the permission-role default.
alter table public.source_folders
  alter column id set default gen_random_uuid(),
  alter column active set default true,
  alter column access_status set default 'PENDING',
  alter column permission_role set default 'UNKNOWN',
  alter column created_at set default now(),
  alter column updated_at set default now();

-- Repair account_name only for the three approved folder IDs.  Unknown rows
-- are not guessed and will be caught by the NOT NULL preflight below.
update public.source_folders
set account_name = case google_folder_id
  when '1J7rUY-n4oVFqwY07jXOwwu_wFo8jeCsI' then 'kdimktgsubang@gmail.com'
  when '1kYX3KIEFkerRMrTvZk2zPpVaFQoCLE4v' then 'kdisubang@gmail.com'
  when '1TkV6WEH5ymgqZmU7WgYFwYeZUxGYkEUt' then 'kdisubang@gmail.com'
end
where account_name is null
  and google_folder_id in (
    '1J7rUY-n4oVFqwY07jXOwwu_wFo8jeCsI',
    '1kYX3KIEFkerRMrTvZk2zPpVaFQoCLE4v',
    '1TkV6WEH5ymgqZmU7WgYFwYeZUxGYkEUt'
  );

-- UNKNOWN is the explicitly safe role for rows that have not been checked.
update public.source_folders
set permission_role = 'UNKNOWN'
where permission_role is null;

-- Safe universal backfills for source_folders contract columns.
update public.source_folders set id = gen_random_uuid() where id is null;
update public.source_folders set active = true where active is null;
update public.source_folders set access_status = 'PENDING' where access_status is null;
update public.source_folders set created_at = now() where created_at is null;
update public.source_folders set updated_at = now() where updated_at is null;

-- Add missing sync_runs columns and safe operational defaults.
alter table public.sync_runs
  add column if not exists id uuid default gen_random_uuid(),
  add column if not exists run_type text default 'MANUAL',
  add column if not exists status text default 'QUEUED',
  add column if not exists started_at timestamptz,
  add column if not exists completed_at timestamptz,
  add column if not exists folders_total integer default 0,
  add column if not exists folders_succeeded integer default 0,
  add column if not exists folders_failed integer default 0,
  add column if not exists files_discovered integer default 0,
  add column if not exists files_taken integer default 0,
  add column if not exists files_skipped integer default 0,
  add column if not exists files_uploaded integer default 0,
  add column if not exists duplicates_found integer default 0,
  add column if not exists files_failed integer default 0,
  add column if not exists error_message text,
  add column if not exists metadata jsonb default '{}'::jsonb,
  add column if not exists created_at timestamptz default now(),
  add column if not exists updated_at timestamptz default now();

-- Restore sync_runs defaults and backfill only semantically neutral values.
alter table public.sync_runs
  alter column id set default gen_random_uuid(),
  alter column run_type set default 'MANUAL',
  alter column status set default 'QUEUED',
  alter column folders_total set default 0,
  alter column folders_succeeded set default 0,
  alter column folders_failed set default 0,
  alter column files_discovered set default 0,
  alter column files_taken set default 0,
  alter column files_skipped set default 0,
  alter column files_uploaded set default 0,
  alter column duplicates_found set default 0,
  alter column files_failed set default 0,
  alter column metadata set default '{}'::jsonb,
  alter column created_at set default now(),
  alter column updated_at set default now();
update public.sync_runs set id = gen_random_uuid() where id is null;
update public.sync_runs set run_type = 'MANUAL' where run_type is null;
update public.sync_runs set status = 'QUEUED' where status is null;
update public.sync_runs set folders_total = 0 where folders_total is null;
update public.sync_runs set folders_succeeded = 0 where folders_succeeded is null;
update public.sync_runs set folders_failed = 0 where folders_failed is null;
update public.sync_runs set files_discovered = 0 where files_discovered is null;
update public.sync_runs set files_taken = 0 where files_taken is null;
update public.sync_runs set files_skipped = 0 where files_skipped is null;
update public.sync_runs set files_uploaded = 0 where files_uploaded is null;
update public.sync_runs set duplicates_found = 0 where duplicates_found is null;
update public.sync_runs set files_failed = 0 where files_failed is null;
update public.sync_runs set metadata = '{}'::jsonb where metadata is null;
update public.sync_runs set created_at = now() where created_at is null;
update public.sync_runs set updated_at = now() where updated_at is null;

-- Add missing scan_runs columns and safe operational defaults.
alter table public.scan_runs
  add column if not exists id uuid default gen_random_uuid(),
  add column if not exists sync_run_id uuid,
  add column if not exists source_folder_id uuid,
  add column if not exists run_mode text default 'DRY_RUN',
  add column if not exists status text default 'QUEUED',
  add column if not exists started_at timestamptz,
  add column if not exists completed_at timestamptz,
  add column if not exists files_discovered integer default 0,
  add column if not exists files_taken integer default 0,
  add column if not exists files_skipped integer default 0,
  add column if not exists files_uploaded integer default 0,
  add column if not exists duplicates_found integer default 0,
  add column if not exists files_failed integer default 0,
  add column if not exists next_page_token text,
  add column if not exists error_message text,
  add column if not exists metadata jsonb default '{}'::jsonb,
  add column if not exists created_at timestamptz default now(),
  add column if not exists updated_at timestamptz default now();
alter table public.scan_runs
  alter column id set default gen_random_uuid(),
  alter column run_mode set default 'DRY_RUN',
  alter column status set default 'QUEUED',
  alter column files_discovered set default 0,
  alter column files_taken set default 0,
  alter column files_skipped set default 0,
  alter column files_uploaded set default 0,
  alter column duplicates_found set default 0,
  alter column files_failed set default 0,
  alter column metadata set default '{}'::jsonb,
  alter column created_at set default now(),
  alter column updated_at set default now();
update public.scan_runs set id = gen_random_uuid() where id is null;
update public.scan_runs set run_mode = 'DRY_RUN' where run_mode is null;
update public.scan_runs set status = 'QUEUED' where status is null;
update public.scan_runs set files_discovered = 0 where files_discovered is null;
update public.scan_runs set files_taken = 0 where files_taken is null;
update public.scan_runs set files_skipped = 0 where files_skipped is null;
update public.scan_runs set files_uploaded = 0 where files_uploaded is null;
update public.scan_runs set duplicates_found = 0 where duplicates_found is null;
update public.scan_runs set files_failed = 0 where files_failed is null;
update public.scan_runs set metadata = '{}'::jsonb where metadata is null;
update public.scan_runs set created_at = now() where created_at is null;
update public.scan_runs set updated_at = now() where updated_at is null;

-- Add missing source_files columns and safe discovery-state defaults.
alter table public.source_files
  add column if not exists id uuid default gen_random_uuid(),
  add column if not exists source_folder_id uuid,
  add column if not exists last_scan_run_id uuid,
  add column if not exists google_file_id text,
  add column if not exists file_name text,
  add column if not exists mime_type text,
  add column if not exists file_extension text,
  add column if not exists size_bytes bigint,
  add column if not exists md5_checksum text,
  add column if not exists drive_created_at timestamptz,
  add column if not exists drive_modified_at timestamptz,
  add column if not exists web_view_link text,
  add column if not exists thumbnail_link text,
  add column if not exists parent_google_folder_id text,
  add column if not exists relative_path text,
  add column if not exists decision text default 'PENDING',
  add column if not exists processing_status text default 'DISCOVERED',
  add column if not exists processing_error text,
  add column if not exists skip_reason text,
  add column if not exists destination_file_id text,
  add column if not exists destination_web_view_link text,
  add column if not exists duplicate_of_source_file_id uuid,
  add column if not exists uploaded_at timestamptz,
  add column if not exists trashed boolean default false,
  add column if not exists is_missing boolean default false,
  add column if not exists first_seen_at timestamptz default now(),
  add column if not exists last_seen_at timestamptz default now(),
  add column if not exists metadata jsonb default '{}'::jsonb,
  add column if not exists created_at timestamptz default now(),
  add column if not exists updated_at timestamptz default now();
alter table public.source_files
  alter column id set default gen_random_uuid(),
  alter column decision set default 'PENDING',
  alter column processing_status set default 'DISCOVERED',
  alter column trashed set default false,
  alter column is_missing set default false,
  alter column first_seen_at set default now(),
  alter column last_seen_at set default now(),
  alter column metadata set default '{}'::jsonb,
  alter column created_at set default now(),
  alter column updated_at set default now();
update public.source_files set id = gen_random_uuid() where id is null;
update public.source_files set decision = 'PENDING' where decision is null;
update public.source_files set processing_status = 'DISCOVERED' where processing_status is null;
update public.source_files set trashed = false where trashed is null;
update public.source_files set is_missing = false where is_missing is null;
update public.source_files set first_seen_at = coalesce(created_at, now()) where first_seen_at is null;
update public.source_files set last_seen_at = greatest(coalesce(first_seen_at, now()), coalesce(created_at, now())) where last_seen_at is null;
update public.source_files set metadata = '{}'::jsonb where metadata is null;
update public.source_files set created_at = now() where created_at is null;
update public.source_files set updated_at = now() where updated_at is null;

-- Add missing assets columns and safe pending-state defaults.
alter table public.assets
  add column if not exists id uuid default gen_random_uuid(),
  add column if not exists content_hash text,
  add column if not exists file_name text,
  add column if not exists mime_type text,
  add column if not exists file_extension text,
  add column if not exists size_bytes bigint,
  add column if not exists storage_bucket text,
  add column if not exists storage_path text,
  add column if not exists upload_status text default 'PENDING',
  add column if not exists uploaded_at timestamptz,
  add column if not exists last_verified_at timestamptz,
  add column if not exists upload_error text,
  add column if not exists metadata jsonb default '{}'::jsonb,
  add column if not exists created_at timestamptz default now(),
  add column if not exists updated_at timestamptz default now();
alter table public.assets
  alter column id set default gen_random_uuid(),
  alter column upload_status set default 'PENDING',
  alter column metadata set default '{}'::jsonb,
  alter column created_at set default now(),
  alter column updated_at set default now();
update public.assets set id = gen_random_uuid() where id is null;
update public.assets set upload_status = 'PENDING' where upload_status is null;
update public.assets set metadata = '{}'::jsonb where metadata is null;
update public.assets set created_at = now() where created_at is null;
update public.assets set updated_at = now() where updated_at is null;

-- Add missing asset_sources columns and install the new default.
alter table public.asset_sources
  add column if not exists id uuid default gen_random_uuid(),
  add column if not exists asset_id uuid,
  add column if not exists source_file_id uuid,
  add column if not exists relationship_type text default 'ORIGINAL',
  add column if not exists created_at timestamptz default now(),
  add column if not exists updated_at timestamptz default now();
alter table public.asset_sources
  alter column id set default gen_random_uuid(),
  alter column relationship_type set default 'ORIGINAL',
  alter column created_at set default now(),
  alter column updated_at set default now();

-- Apply the required, lossless legacy relationship mapping.
update public.asset_sources
set relationship_type = case relationship_type
  when 'ORIGINAL_SOURCE' then 'ORIGINAL'
  when 'EXACT_DUPLICATE' then 'DUPLICATE'
end
where relationship_type in ('ORIGINAL_SOURCE', 'EXACT_DUPLICATE');
update public.asset_sources set id = gen_random_uuid() where id is null;
update public.asset_sources set relationship_type = 'ORIGINAL' where relationship_type is null;
update public.asset_sources set created_at = now() where created_at is null;
update public.asset_sources set updated_at = now() where updated_at is null;

-- Add missing migration_events columns and safe event-log defaults.
alter table public.migration_events
  add column if not exists id uuid default gen_random_uuid(),
  add column if not exists sync_run_id uuid,
  add column if not exists scan_run_id uuid,
  add column if not exists source_folder_id uuid,
  add column if not exists source_file_id uuid,
  add column if not exists asset_id uuid,
  add column if not exists event_type text,
  add column if not exists event_status text default 'INFO',
  add column if not exists message text,
  add column if not exists details jsonb default '{}'::jsonb,
  add column if not exists occurred_at timestamptz default now(),
  add column if not exists created_at timestamptz default now(),
  add column if not exists updated_at timestamptz default now();
alter table public.migration_events
  alter column id set default gen_random_uuid(),
  alter column event_status set default 'INFO',
  alter column details set default '{}'::jsonb,
  alter column occurred_at set default now(),
  alter column created_at set default now(),
  alter column updated_at set default now();
update public.migration_events set id = gen_random_uuid() where id is null;
update public.migration_events set event_status = 'INFO' where event_status is null;
update public.migration_events set details = '{}'::jsonb where details is null;
update public.migration_events set occurred_at = now() where occurred_at is null;
update public.migration_events set created_at = now() where created_at is null;
update public.migration_events set updated_at = now() where updated_at is null;

-- Confirm every required non-null value is now known.  Required foreign keys
-- and descriptive identifiers are never fabricated.
do $repair$
declare
  problem text;
begin
  select string_agg(item, ', ') into problem
  from (
    select 'source_folders required fields' item where exists (
      select 1 from public.source_folders
      where id is null or source_name is null or account_name is null
         or folder_url is null or google_folder_id is null or active is null
         or access_status is null or permission_role is null
         or created_at is null or updated_at is null)
    union all select 'sync_runs required fields' where exists (
      select 1 from public.sync_runs where id is null or run_type is null or status is null
        or folders_total is null or folders_succeeded is null or folders_failed is null
        or files_discovered is null or files_taken is null or files_skipped is null
        or files_uploaded is null or duplicates_found is null or files_failed is null
        or metadata is null or created_at is null or updated_at is null)
    union all select 'scan_runs required fields' where exists (
      select 1 from public.scan_runs where id is null or source_folder_id is null
        or run_mode is null or status is null or files_discovered is null
        or files_taken is null or files_skipped is null or files_uploaded is null
        or duplicates_found is null or files_failed is null or metadata is null
        or created_at is null or updated_at is null)
    union all select 'source_files required fields' where exists (
      select 1 from public.source_files where id is null or source_folder_id is null
        or google_file_id is null or file_name is null or decision is null
        or processing_status is null or trashed is null or is_missing is null
        or first_seen_at is null or last_seen_at is null or metadata is null
        or created_at is null or updated_at is null)
    union all select 'assets required fields' where exists (
      select 1 from public.assets where id is null or file_name is null
        or upload_status is null or metadata is null or created_at is null or updated_at is null)
    union all select 'asset_sources required fields' where exists (
      select 1 from public.asset_sources where id is null or asset_id is null
        or source_file_id is null or relationship_type is null
        or created_at is null or updated_at is null)
    union all select 'migration_events required fields' where exists (
      select 1 from public.migration_events where id is null or event_type is null
        or event_status is null or details is null or occurred_at is null
        or created_at is null or updated_at is null)
  ) failures;
  if problem is not null then
    raise exception 'Cannot safely set NOT NULL; review live data for: %', problem;
  end if;
end
$repair$;

-- Install the intended nullability only after the preceding data preflight.
alter table public.source_folders
  alter column id set not null, alter column source_name set not null,
  alter column account_name set not null, alter column folder_url set not null,
  alter column google_folder_id set not null, alter column active set not null,
  alter column access_status set not null, alter column permission_role set not null,
  alter column created_at set not null, alter column updated_at set not null;
alter table public.sync_runs
  alter column id set not null, alter column run_type set not null,
  alter column status set not null, alter column folders_total set not null,
  alter column folders_succeeded set not null, alter column folders_failed set not null,
  alter column files_discovered set not null, alter column files_taken set not null,
  alter column files_skipped set not null, alter column files_uploaded set not null,
  alter column duplicates_found set not null, alter column files_failed set not null,
  alter column metadata set not null, alter column created_at set not null,
  alter column updated_at set not null;
alter table public.scan_runs
  alter column id set not null, alter column source_folder_id set not null,
  alter column run_mode set not null, alter column status set not null,
  alter column files_discovered set not null, alter column files_taken set not null,
  alter column files_skipped set not null, alter column files_uploaded set not null,
  alter column duplicates_found set not null, alter column files_failed set not null,
  alter column metadata set not null, alter column created_at set not null,
  alter column updated_at set not null;
alter table public.source_files
  alter column id set not null, alter column source_folder_id set not null,
  alter column google_file_id set not null, alter column file_name set not null,
  alter column decision set not null, alter column processing_status set not null,
  alter column trashed set not null, alter column is_missing set not null,
  alter column first_seen_at set not null, alter column last_seen_at set not null,
  alter column metadata set not null, alter column created_at set not null,
  alter column updated_at set not null;
alter table public.assets
  alter column id set not null, alter column file_name set not null,
  alter column upload_status set not null, alter column metadata set not null,
  alter column created_at set not null, alter column updated_at set not null;
alter table public.asset_sources
  alter column id set not null, alter column asset_id set not null,
  alter column source_file_id set not null, alter column relationship_type set not null,
  alter column created_at set not null, alter column updated_at set not null;
alter table public.migration_events
  alter column id set not null, alter column event_type set not null,
  alter column event_status set not null, alter column details set not null,
  alter column occurred_at set not null, alter column created_at set not null,
  alter column updated_at set not null;

-- Preflight all intended status/value domains before replacing outdated checks.
-- No undocumented status mapping is assumed.
do $repair$
begin
  if exists (select 1 from public.source_folders where access_status not in
    ('PENDING','ACCESSIBLE','INACCESSIBLE','ERROR','DISABLED')) then
    raise exception 'Unmapped source_folders.access_status values require review';
  end if;
  if exists (select 1 from public.source_folders where permission_role not in
    ('UNKNOWN','VIEWER','COMMENTER','EDITOR','OWNER')) then
    raise exception 'Unmapped source_folders.permission_role values require review';
  end if;
  if exists (select 1 from public.sync_runs where run_type not in
    ('MANUAL','INITIAL_MIGRATION','DAILY_SYNC','RETRY')) then
    raise exception 'Unmapped sync_runs.run_type values require review';
  end if;
  if exists (select 1 from public.sync_runs where status not in
    ('QUEUED','RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED','CANCELLED')) then
    raise exception 'Unmapped sync_runs.status values require review';
  end if;
  if exists (select 1 from public.scan_runs where run_mode not in ('DRY_RUN','MIGRATION')) then
    raise exception 'Unmapped scan_runs.run_mode values require review';
  end if;
  if exists (select 1 from public.scan_runs where status not in
    ('QUEUED','RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED','CANCELLED')) then
    raise exception 'Unmapped scan_runs.status values require review';
  end if;
  if exists (select 1 from public.source_files where decision not in ('PENDING','TAKE','SKIP')) then
    raise exception 'Unmapped source_files.decision values require review';
  end if;
  if exists (select 1 from public.source_files where processing_status not in
    ('DISCOVERED','QUEUED','HASHING','READY','DUPLICATE','UPLOADING','UPLOADED','SKIPPED','FAILED','INACCESSIBLE')) then
    raise exception 'Unmapped source_files.processing_status values require review';
  end if;
  if exists (select 1 from public.assets where upload_status not in
    ('PENDING','UPLOADING','UPLOADED','FAILED','MISSING','VERIFICATION_REQUIRED')) then
    raise exception 'Unmapped assets.upload_status values require review';
  end if;
  if exists (select 1 from public.asset_sources where relationship_type not in
    ('ORIGINAL','DUPLICATE')) then
    raise exception 'Unmapped asset_sources.relationship_type values require review';
  end if;
  if exists (select 1 from public.migration_events where event_status not in
    ('INFO','SUCCESS','WARNING','ERROR')) then
    raise exception 'Unmapped migration_events.event_status values require review';
  end if;
end
$repair$;

-- Replace only named CHECK constraints whose definitions may be outdated.
alter table public.source_folders drop constraint if exists source_folders_access_status_check;
alter table public.source_folders add constraint source_folders_access_status_check
  check (access_status in ('PENDING','ACCESSIBLE','INACCESSIBLE','ERROR','DISABLED'));
alter table public.source_folders drop constraint if exists source_folders_permission_role_check;
alter table public.source_folders add constraint source_folders_permission_role_check
  check (permission_role in ('UNKNOWN','VIEWER','COMMENTER','EDITOR','OWNER'));
alter table public.sync_runs drop constraint if exists sync_runs_run_type_check;
alter table public.sync_runs add constraint sync_runs_run_type_check
  check (run_type in ('MANUAL','INITIAL_MIGRATION','DAILY_SYNC','RETRY'));
alter table public.sync_runs drop constraint if exists sync_runs_status_check;
alter table public.sync_runs add constraint sync_runs_status_check
  check (status in ('QUEUED','RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED','CANCELLED'));
alter table public.scan_runs drop constraint if exists scan_runs_run_mode_check;
alter table public.scan_runs add constraint scan_runs_run_mode_check check (run_mode in ('DRY_RUN','MIGRATION'));
alter table public.scan_runs drop constraint if exists scan_runs_status_check;
alter table public.scan_runs add constraint scan_runs_status_check
  check (status in ('QUEUED','RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED','CANCELLED'));
alter table public.source_files drop constraint if exists source_files_decision_check;
alter table public.source_files add constraint source_files_decision_check check (decision in ('PENDING','TAKE','SKIP'));
alter table public.source_files drop constraint if exists source_files_processing_status_check;
alter table public.source_files add constraint source_files_processing_status_check
  check (processing_status in ('DISCOVERED','QUEUED','HASHING','READY','DUPLICATE','UPLOADING','UPLOADED','SKIPPED','FAILED','INACCESSIBLE'));
alter table public.assets drop constraint if exists assets_upload_status_check;
alter table public.assets add constraint assets_upload_status_check
  check (upload_status in ('PENDING','UPLOADING','UPLOADED','FAILED','MISSING','VERIFICATION_REQUIRED'));
alter table public.asset_sources drop constraint if exists asset_sources_relationship_type_check;
alter table public.asset_sources add constraint asset_sources_relationship_type_check
  check (relationship_type in ('ORIGINAL','DUPLICATE'));
alter table public.migration_events drop constraint if exists migration_events_event_status_check;
alter table public.migration_events add constraint migration_events_event_status_check
  check (event_status in ('INFO','SUCCESS','WARNING','ERROR'));

-- Add all non-domain CHECK constraints when missing; validation protects data.
do $repair$
begin
  if not exists (select 1 from pg_constraint where conrelid='public.sync_runs'::regclass and conname='sync_runs_counts_check') then
    alter table public.sync_runs add constraint sync_runs_counts_check check (
      folders_total>=0 and folders_succeeded>=0 and folders_failed>=0 and files_discovered>=0
      and files_taken>=0 and files_skipped>=0 and files_uploaded>=0 and duplicates_found>=0 and files_failed>=0);
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.sync_runs'::regclass and conname='sync_runs_timestamps_check') then
    alter table public.sync_runs add constraint sync_runs_timestamps_check check (completed_at is null or started_at is null or completed_at>=started_at);
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.sync_runs'::regclass and conname='sync_runs_metadata_object_check') then
    alter table public.sync_runs add constraint sync_runs_metadata_object_check check (jsonb_typeof(metadata)='object');
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.scan_runs'::regclass and conname='scan_runs_counts_check') then
    alter table public.scan_runs add constraint scan_runs_counts_check check (
      files_discovered>=0 and files_taken>=0 and files_skipped>=0 and files_uploaded>=0 and duplicates_found>=0 and files_failed>=0);
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.scan_runs'::regclass and conname='scan_runs_timestamps_check') then
    alter table public.scan_runs add constraint scan_runs_timestamps_check check (completed_at is null or started_at is null or completed_at>=started_at);
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.scan_runs'::regclass and conname='scan_runs_metadata_object_check') then
    alter table public.scan_runs add constraint scan_runs_metadata_object_check check (jsonb_typeof(metadata)='object');
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.source_files'::regclass and conname='source_files_size_bytes_check') then
    alter table public.source_files add constraint source_files_size_bytes_check check (size_bytes is null or size_bytes>=0);
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.source_files'::regclass and conname='source_files_md5_checksum_check') then
    alter table public.source_files add constraint source_files_md5_checksum_check check (md5_checksum is null or md5_checksum ~ '^[0-9A-Fa-f]{32}$');
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.source_files'::regclass and conname='source_files_seen_timestamps_check') then
    alter table public.source_files add constraint source_files_seen_timestamps_check check (last_seen_at>=first_seen_at);
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.source_files'::regclass and conname='source_files_metadata_object_check') then
    alter table public.source_files add constraint source_files_metadata_object_check check (jsonb_typeof(metadata)='object');
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.assets'::regclass and conname='assets_content_hash_check') then
    alter table public.assets add constraint assets_content_hash_check check (content_hash is null or content_hash ~ '^[0-9A-Fa-f]{64}$');
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.assets'::regclass and conname='assets_size_bytes_check') then
    alter table public.assets add constraint assets_size_bytes_check check (size_bytes is null or size_bytes>=0);
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.assets'::regclass and conname='assets_storage_location_check') then
    alter table public.assets add constraint assets_storage_location_check check (
      (storage_bucket is null and storage_path is null) or (storage_bucket is not null and storage_path is not null));
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.assets'::regclass and conname='assets_metadata_object_check') then
    alter table public.assets add constraint assets_metadata_object_check check (jsonb_typeof(metadata)='object');
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.migration_events'::regclass and conname='migration_events_details_object_check') then
    alter table public.migration_events add constraint migration_events_details_object_check check (jsonb_typeof(details)='object');
  end if;
end
$repair$;

-- Validate any pre-existing NOT VALID checks/foreign keys now that the data
-- preflights and repairs have completed. A violation aborts without data loss.
do $repair$
declare
  item record;
begin
  for item in
    select n.nspname, r.relname, c.conname
    from pg_constraint c
    join pg_class r on r.oid=c.conrelid
    join pg_namespace n on n.oid=r.relnamespace
    where n.nspname='public'
      and r.relname in ('source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','migration_events')
      and c.contype in ('c','f')
      and not c.convalidated
  loop
    execute format('alter table %I.%I validate constraint %I',item.nspname,item.relname,item.conname);
  end loop;
end
$repair$;

-- Repair the two existing foreign keys whose delete behavior differs from
-- the foundation contract. Replacing these constraints does not change rows;
-- it changes only what happens if a parent source folder is deleted later.
alter table public.scan_runs
  drop constraint if exists scan_runs_source_folder_id_fkey;
alter table public.scan_runs
  add constraint scan_runs_source_folder_id_fkey
  foreign key (source_folder_id)
  references public.source_folders(id)
  on delete cascade;

alter table public.source_files
  drop constraint if exists source_files_source_folder_id_fkey;
alter table public.source_files
  add constraint source_files_source_folder_id_fkey
  foreign key (source_folder_id)
  references public.source_folders(id)
  on delete cascade;

-- Add primary, remaining foreign-key, and unique constraints only when their
-- intended named constraints are missing. Existing bad references or
-- duplicates abort the transaction safely.
do $repair$
begin
  if not exists (select 1 from pg_constraint where conrelid='public.source_folders'::regclass and conname='source_folders_pkey') then alter table public.source_folders add constraint source_folders_pkey primary key (id); end if;
  if not exists (select 1 from pg_constraint where conrelid='public.sync_runs'::regclass and conname='sync_runs_pkey') then alter table public.sync_runs add constraint sync_runs_pkey primary key (id); end if;
  if not exists (select 1 from pg_constraint where conrelid='public.scan_runs'::regclass and conname='scan_runs_pkey') then alter table public.scan_runs add constraint scan_runs_pkey primary key (id); end if;
  if not exists (select 1 from pg_constraint where conrelid='public.source_files'::regclass and conname='source_files_pkey') then alter table public.source_files add constraint source_files_pkey primary key (id); end if;
  if not exists (select 1 from pg_constraint where conrelid='public.assets'::regclass and conname='assets_pkey') then alter table public.assets add constraint assets_pkey primary key (id); end if;
  if not exists (select 1 from pg_constraint where conrelid='public.asset_sources'::regclass and conname='asset_sources_pkey') then alter table public.asset_sources add constraint asset_sources_pkey primary key (id); end if;
  if not exists (select 1 from pg_constraint where conrelid='public.migration_events'::regclass and conname='migration_events_pkey') then alter table public.migration_events add constraint migration_events_pkey primary key (id); end if;
  if not exists (select 1 from pg_constraint where conrelid='public.scan_runs'::regclass and conname='scan_runs_sync_run_id_fkey') then alter table public.scan_runs add constraint scan_runs_sync_run_id_fkey foreign key(sync_run_id) references public.sync_runs(id) on delete set null; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.scan_runs'::regclass and conname='scan_runs_source_folder_id_fkey') then alter table public.scan_runs add constraint scan_runs_source_folder_id_fkey foreign key(source_folder_id) references public.source_folders(id) on delete cascade; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.source_files'::regclass and conname='source_files_source_folder_id_fkey') then alter table public.source_files add constraint source_files_source_folder_id_fkey foreign key(source_folder_id) references public.source_folders(id) on delete cascade; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.source_files'::regclass and conname='source_files_last_scan_run_id_fkey') then alter table public.source_files add constraint source_files_last_scan_run_id_fkey foreign key(last_scan_run_id) references public.scan_runs(id) on delete set null; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.source_files'::regclass and conname='source_files_duplicate_of_source_file_id_fkey') then alter table public.source_files add constraint source_files_duplicate_of_source_file_id_fkey foreign key(duplicate_of_source_file_id) references public.source_files(id) on delete set null; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.asset_sources'::regclass and conname='asset_sources_asset_id_fkey') then alter table public.asset_sources add constraint asset_sources_asset_id_fkey foreign key(asset_id) references public.assets(id) on delete cascade; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.asset_sources'::regclass and conname='asset_sources_source_file_id_fkey') then alter table public.asset_sources add constraint asset_sources_source_file_id_fkey foreign key(source_file_id) references public.source_files(id) on delete cascade; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.migration_events'::regclass and conname='migration_events_sync_run_id_fkey') then alter table public.migration_events add constraint migration_events_sync_run_id_fkey foreign key(sync_run_id) references public.sync_runs(id) on delete set null; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.migration_events'::regclass and conname='migration_events_scan_run_id_fkey') then alter table public.migration_events add constraint migration_events_scan_run_id_fkey foreign key(scan_run_id) references public.scan_runs(id) on delete set null; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.migration_events'::regclass and conname='migration_events_source_folder_id_fkey') then alter table public.migration_events add constraint migration_events_source_folder_id_fkey foreign key(source_folder_id) references public.source_folders(id) on delete set null; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.migration_events'::regclass and conname='migration_events_source_file_id_fkey') then alter table public.migration_events add constraint migration_events_source_file_id_fkey foreign key(source_file_id) references public.source_files(id) on delete set null; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.migration_events'::regclass and conname='migration_events_asset_id_fkey') then alter table public.migration_events add constraint migration_events_asset_id_fkey foreign key(asset_id) references public.assets(id) on delete set null; end if;
  if not exists (select 1 from pg_constraint where conrelid='public.source_files'::regclass and conname='source_files_folder_google_file_unique') then alter table public.source_files add constraint source_files_folder_google_file_unique unique(source_folder_id,google_file_id); end if;
  if not exists (select 1 from pg_constraint where conrelid='public.asset_sources'::regclass and conname='asset_sources_asset_source_unique') then alter table public.asset_sources add constraint asset_sources_asset_source_unique unique(asset_id,source_file_id); end if;
  if not exists (select 1 from pg_constraint where conrelid='public.asset_sources'::regclass and conname='asset_sources_source_file_unique') then alter table public.asset_sources add constraint asset_sources_source_file_unique unique(source_file_id); end if;
end
$repair$;

-- Add the complete migration-001 index set. Unique-index creation intentionally
-- aborts on duplicates rather than choosing or deleting a row.
create unique index if not exists source_folders_google_folder_id_unique on public.source_folders(google_folder_id);
create index if not exists source_folders_active_access_status_idx on public.source_folders(active,access_status);
create index if not exists source_folders_account_name_idx on public.source_folders(account_name);
create index if not exists source_folders_last_scan_at_idx on public.source_folders(last_scan_at desc);
create index if not exists sync_runs_status_created_at_idx on public.sync_runs(status,created_at desc);
create index if not exists sync_runs_run_type_created_at_idx on public.sync_runs(run_type,created_at desc);
create index if not exists scan_runs_sync_run_id_idx on public.scan_runs(sync_run_id);
create index if not exists scan_runs_source_folder_created_at_idx on public.scan_runs(source_folder_id,created_at desc);
create index if not exists scan_runs_status_created_at_idx on public.scan_runs(status,created_at desc);
create index if not exists source_files_last_scan_run_id_idx on public.source_files(last_scan_run_id);
create index if not exists source_files_google_file_id_idx on public.source_files(google_file_id);
create index if not exists source_files_folder_decision_status_idx on public.source_files(source_folder_id,decision,processing_status);
create index if not exists source_files_exact_duplicate_idx on public.source_files(md5_checksum,size_bytes) where md5_checksum is not null and size_bytes is not null;
create index if not exists source_files_destination_file_id_idx on public.source_files(destination_file_id) where destination_file_id is not null;
create unique index if not exists assets_content_hash_unique on public.assets(content_hash) where content_hash is not null;
create unique index if not exists assets_storage_location_unique on public.assets(storage_bucket,storage_path) where storage_bucket is not null and storage_path is not null;
create index if not exists assets_upload_status_created_at_idx on public.assets(upload_status,created_at desc);
create index if not exists asset_sources_asset_id_idx on public.asset_sources(asset_id);
create index if not exists asset_sources_relationship_type_idx on public.asset_sources(relationship_type);
create index if not exists migration_events_sync_run_occurred_at_idx on public.migration_events(sync_run_id,occurred_at desc);
create index if not exists migration_events_scan_run_occurred_at_idx on public.migration_events(scan_run_id,occurred_at desc);
create index if not exists migration_events_source_folder_occurred_at_idx on public.migration_events(source_folder_id,occurred_at desc);
create index if not exists migration_events_source_file_occurred_at_idx on public.migration_events(source_file_id,occurred_at desc);
create index if not exists migration_events_asset_occurred_at_idx on public.migration_events(asset_id,occurred_at desc);
create index if not exists migration_events_type_status_occurred_at_idx on public.migration_events(event_type,event_status,occurred_at desc);

-- Add or repair each required updated_at trigger without changing table data.
do $repair$
declare
  table_name text;
  trigger_name text;
  trigger_ok boolean;
begin
  foreach table_name in array array['source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','migration_events']
  loop
    trigger_name := table_name || '_set_updated_at';
    select t.tgenabled <> 'D'
       and pg_get_triggerdef(t.oid,true) ~* 'BEFORE UPDATE.*FOR EACH ROW EXECUTE FUNCTION (public[.])?set_updated_at[(][)]'
    into trigger_ok
    from pg_trigger t
    where t.tgrelid = format('public.%I',table_name)::regclass
      and t.tgname = trigger_name and not t.tgisinternal;
    if not coalesce(trigger_ok,false) then
      execute format('drop trigger if exists %I on public.%I',trigger_name,table_name);
      execute format('create trigger %I before update on public.%I for each row execute function public.set_updated_at()',trigger_name,table_name);
    end if;
  end loop;
end
$repair$;

-- Enable RLS on every foundation table.
alter table public.source_folders enable row level security;
alter table public.sync_runs enable row level security;
alter table public.scan_runs enable row level security;
alter table public.source_files enable row level security;
alter table public.assets enable row level security;
alter table public.asset_sources enable row level security;
alter table public.migration_events enable row level security;

-- Add or repair the seven authenticated authorized-read policies.
do $repair$
declare
  table_name text;
  policy_name text;
  policy_ok boolean;
begin
  foreach table_name in array array['source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','migration_events']
  loop
    policy_name := table_name || '_authorized_read';
    select p.cmd='SELECT' and p.permissive='PERMISSIVE'
       and 'authenticated'=any(p.roles)
       and p.qual ~ 'kdi_media_reader' and p.qual ~ '''true'''
    into policy_ok
    from pg_policies p
    where p.schemaname='public' and p.tablename=table_name and p.policyname=policy_name;
    if not coalesce(policy_ok,false) then
      execute format('drop policy if exists %I on public.%I',policy_name,table_name);
      execute format(
        'create policy %I on public.%I for select to authenticated using (coalesce((select auth.jwt() -> ''app_metadata'' ->> ''kdi_media_reader'') = ''true'', false))',
        policy_name,table_name);
    end if;
  end loop;
end
$repair$;

-- Restore the intended privileges associated with the RLS policies.
revoke all on table public.source_folders, public.sync_runs, public.scan_runs,
  public.source_files, public.assets, public.asset_sources, public.migration_events from anon;
grant select on table public.source_folders, public.sync_runs, public.scan_runs,
  public.source_files, public.assets, public.asset_sources, public.migration_events to authenticated;
grant select,insert,update,delete on table public.source_folders, public.sync_runs,
  public.scan_runs, public.source_files, public.assets, public.asset_sources,
  public.migration_events to service_role;

-- Recreate source_folder_summary exactly from migration 001. Dropping only the
-- derived view is required because CREATE OR REPLACE cannot change an existing
-- view's column names/order/types; no underlying table row is modified.
drop view if exists public.source_folder_summary;
create view public.source_folder_summary
with (security_invoker = true)
as
select
  sf.id, sf.source_name, sf.account_name, sf.folder_url, sf.google_folder_id,
  sf.active, sf.access_status, sf.permission_role, sf.last_access_checked_at,
  sf.last_scan_at, sf.last_successful_scan_at, sf.notes, sf.created_at, sf.updated_at,
  coalesce(file_totals.total_files,0)::bigint as total_files,
  coalesce(file_totals.take_files,0)::bigint as take_files,
  coalesce(file_totals.skip_files,0)::bigint as skip_files,
  coalesce(file_totals.uploaded_files,0)::bigint as uploaded_files,
  coalesce(file_totals.duplicate_files,0)::bigint as duplicate_files,
  coalesce(file_totals.failed_files,0)::bigint as failed_files,
  coalesce(asset_totals.asset_count,0)::bigint as asset_count,
  latest_scan.id as latest_scan_run_id,
  latest_scan.status as latest_scan_status,
  latest_scan.started_at as latest_scan_started_at,
  latest_scan.completed_at as latest_scan_completed_at
from public.source_folders sf
left join lateral (
  select count(*) as total_files,
    count(*) filter(where source_file.decision='TAKE') as take_files,
    count(*) filter(where source_file.decision='SKIP') as skip_files,
    count(*) filter(where source_file.processing_status='UPLOADED') as uploaded_files,
    count(*) filter(where source_file.processing_status='DUPLICATE') as duplicate_files,
    count(*) filter(where source_file.processing_status='FAILED') as failed_files
  from public.source_files source_file
  where source_file.source_folder_id=sf.id
) file_totals on true
left join lateral (
  select count(distinct asset_source.asset_id) as asset_count
  from public.source_files source_file
  join public.asset_sources asset_source on asset_source.source_file_id=source_file.id
  where source_file.source_folder_id=sf.id
) asset_totals on true
left join lateral (
  select scan.id,scan.status,scan.started_at,scan.completed_at
  from public.scan_runs scan
  where scan.source_folder_id=sf.id
  order by scan.created_at desc,scan.id desc
  limit 1
) latest_scan on true;

-- Restore the view metadata and access grants.
comment on view public.source_folder_summary is
  'Source-folder access, scan, file-processing, and asset totals.';
revoke all on table public.source_folder_summary from anon;
grant select on table public.source_folder_summary to authenticated;
grant select on table public.source_folder_summary to service_role;
revoke all on function public.set_updated_at() from public;

commit;