-- Additive Firebase identity bridge. The existing Supabase UUID remains the
-- profile primary key and rollback identity; Firebase UIDs are always text.
begin;

create temp table firebase_migration_counts_before on commit drop as
select 'approved_app_users'::text relation_name,count(*)::bigint row_count from public.approved_app_users union all
select 'app_users',count(*) from public.app_users union all
select 'source_folders',count(*) from public.source_folders union all
select 'source_files',count(*) from public.source_files union all
select 'assets',count(*) from public.assets union all
select 'asset_sources',count(*) from public.asset_sources union all
select 'asset_destinations',count(*) from public.asset_destinations union all
select 'sync_runs',count(*) from public.sync_runs union all
select 'scan_runs',count(*) from public.scan_runs union all
select 'migration_events',count(*) from public.migration_events;

alter table public.app_users
  add column if not exists firebase_uid text null,
  add column if not exists firebase_linked_at timestamptz null;

alter table public.app_users
  add constraint app_users_firebase_uid_format check (
    firebase_uid is null or (
      firebase_uid = btrim(firebase_uid)
      and length(firebase_uid) between 1 and 128
      and firebase_uid !~ '[[:space:]]'
    )
  );

create unique index app_users_firebase_uid_unique
  on public.app_users(firebase_uid)
  where firebase_uid is not null;

create or replace function private.is_verified_firebase_identity()
returns boolean language sql stable security invoker
set search_path = ''
as $$
  select coalesce(
    (auth.jwt() ->> 'iss') = 'https://securetoken.google.com/kdi-media-library'
    and (auth.jwt() ->> 'aud') = 'kdi-media-library'
    and (auth.jwt() ->> 'email_verified')::boolean is true
    and nullif(btrim(auth.jwt() ->> 'sub'),'') is not null,
    false
  );
$$;

create or replace function private.current_app_user_id()
returns uuid language sql stable security definer
set search_path = ''
as $$
  select case
    when (auth.jwt() ->> 'iss') = 'https://securetoken.google.com/kdi-media-library'
      then (
        select u.user_id from public.app_users u
        where private.is_verified_firebase_identity()
          and u.firebase_uid = (auth.jwt() ->> 'sub')
        limit 1
      )
    when (auth.jwt() ->> 'iss') ~ '^https://wcqqjpndlwsvatjuqnol[.]supabase[.]co/auth/v1/?$'
      then auth.uid()
    else null
  end;
$$;

create or replace function private.is_active_app_user()
returns boolean language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.app_users u
    where u.user_id = private.current_app_user_id() and u.is_active
  );
$$;

create or replace function private.has_app_role(required_role public.app_role)
returns boolean language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.app_users u
    where u.user_id = private.current_app_user_id() and u.is_active
      and (u.role = 'ADMIN'::public.app_role or u.role = required_role)
  );
$$;

create or replace function private.can_view_clinical_media()
returns boolean language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.app_users u
    where u.user_id = private.current_app_user_id()
      and u.is_active and u.can_view_clinical
  );
$$;

create or replace function private.can_download_media()
returns boolean language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.app_users u
    where u.user_id = private.current_app_user_id()
      and u.is_active and u.can_download
  );
$$;

drop policy if exists app_users_select_self on public.app_users;
create policy app_users_select_self on public.app_users
for select to authenticated
using (user_id = (select private.current_app_user_id()));

-- Server-only bootstrap. It never changes database-controlled authorization.
create or replace function public.bootstrap_firebase_app_user(
  requested_firebase_uid text,
  requested_email text
)
returns table(user_id uuid, role public.app_role, is_active boolean)
language plpgsql security definer
set search_path = ''
as $$
declare
  normalized_requested_email text := lower(btrim(requested_email));
  matched public.app_users%rowtype;
begin
  if auth.role() <> 'service_role' then
    raise exception 'access denied' using errcode='42501';
  end if;
  if requested_firebase_uid is null
    or requested_firebase_uid <> btrim(requested_firebase_uid)
    or length(requested_firebase_uid) not between 1 and 128
    or requested_firebase_uid ~ '[[:space:]]'
    or normalized_requested_email !~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$' then
    raise exception 'access denied' using errcode='42501';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(normalized_requested_email,0));
  perform pg_advisory_xact_lock(hashtextextended(requested_firebase_uid,1));

  if exists (
    select 1 from public.app_users u
    where u.firebase_uid=requested_firebase_uid
      and u.email<>normalized_requested_email
  ) then
    raise exception 'identity conflict' using errcode='23505';
  end if;

  select * into matched from public.app_users u
  where u.email=normalized_requested_email
  for update;

  if not found or not matched.is_active then
    raise exception 'access denied' using errcode='42501';
  end if;
  if matched.firebase_uid is not null
    and matched.firebase_uid<>requested_firebase_uid then
    raise exception 'identity conflict' using errcode='23505';
  end if;

  update public.app_users u
  set firebase_uid=requested_firebase_uid,
      firebase_linked_at=coalesce(u.firebase_linked_at,now()),
      updated_at=now()
  where u.user_id=matched.user_id;

  return query select matched.user_id,matched.role,matched.is_active;
end;
$$;

revoke all on function public.bootstrap_firebase_app_user(text,text) from public,anon,authenticated;
grant execute on function public.bootstrap_firebase_app_user(text,text) to service_role;

-- Preserve the repaired explicit view boundary with issuer-aware resolution.
create or replace view public.source_folder_summary
with (security_invoker=true,security_barrier=true)
as
select
  sf.id,sf.source_name,sf.account_name,sf.folder_url,sf.google_folder_id,
  sf.active,sf.access_status,sf.permission_role,sf.last_access_checked_at,
  sf.last_scan_at,sf.last_successful_scan_at,sf.notes,sf.created_at,sf.updated_at,
  coalesce(ft.total_files,0)::bigint total_files,
  coalesce(ft.take_files,0)::bigint take_files,
  coalesce(ft.skip_files,0)::bigint skip_files,
  coalesce(ft.uploaded_files,0)::bigint uploaded_files,
  coalesce(ft.duplicate_files,0)::bigint duplicate_files,
  coalesce(ft.failed_files,0)::bigint failed_files,
  coalesce(at.asset_count,0)::bigint asset_count,
  ls.id latest_scan_run_id,ls.status latest_scan_status,
  ls.started_at latest_scan_started_at,ls.completed_at latest_scan_completed_at
from public.source_folders sf
left join lateral (
  select count(*) total_files,
    count(*) filter(where x.decision='TAKE') take_files,
    count(*) filter(where x.decision='SKIP') skip_files,
    count(*) filter(where x.processing_status='UPLOADED') uploaded_files,
    count(*) filter(where x.processing_status='DUPLICATE') duplicate_files,
    count(*) filter(where x.processing_status='FAILED') failed_files
  from public.source_files x where x.source_folder_id=sf.id
) ft on true
left join lateral (
  select count(distinct s.asset_id) asset_count
  from public.source_files x join public.asset_sources s on s.source_file_id=x.id
  where x.source_folder_id=sf.id
) at on true
left join lateral (
  select x.id,x.status,x.started_at,x.completed_at from public.scan_runs x
  where x.source_folder_id=sf.id order by x.created_at desc,x.id desc limit 1
) ls on true
where exists (
  select 1 from public.app_users u
  where u.user_id=(select private.current_app_user_id()) and u.is_active
    and u.role in ('STAFF'::public.app_role,'ADMIN'::public.app_role)
);

revoke all on table public.source_folder_summary from public,anon,authenticated,service_role;
grant select on table public.source_folder_summary to authenticated,service_role;

-- Reassert write/RPC boundaries after the identity additions.
revoke insert,update,delete,truncate on public.approved_app_users,public.app_users,
  public.source_folders,public.sync_runs,public.scan_runs,public.source_files,
  public.assets,public.asset_sources,public.asset_destinations,public.migration_events
  from anon,authenticated;

create temp table firebase_migration_counts_after on commit drop as
select 'approved_app_users'::text relation_name,count(*)::bigint row_count from public.approved_app_users union all
select 'app_users',count(*) from public.app_users union all
select 'source_folders',count(*) from public.source_folders union all
select 'source_files',count(*) from public.source_files union all
select 'assets',count(*) from public.assets union all
select 'asset_sources',count(*) from public.asset_sources union all
select 'asset_destinations',count(*) from public.asset_destinations union all
select 'sync_runs',count(*) from public.sync_runs union all
select 'scan_runs',count(*) from public.scan_runs union all
select 'migration_events',count(*) from public.migration_events;

do $$ begin
  if exists(
    select 1 from firebase_migration_counts_before b
    join firebase_migration_counts_after a using(relation_name)
    where b.row_count<>a.row_count
  ) then raise exception 'Firebase migration changed production row counts'; end if;
end $$;

select b.relation_name,b.row_count before_count,a.row_count after_count
from firebase_migration_counts_before b
join firebase_migration_counts_after a using(relation_name)
order by b.relation_name;

commit;
