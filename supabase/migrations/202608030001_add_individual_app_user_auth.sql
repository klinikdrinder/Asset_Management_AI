begin;

create type public.app_role as enum ('STAFF', 'ADMIN');

create table public.approved_app_users (
  normalized_email text primary key,
  role public.app_role not null,
  is_active boolean not null default true,
  can_view_clinical boolean not null default false,
  can_download boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid null references auth.users(id) on delete set null,
  constraint approved_app_users_normalized_email check (
    normalized_email = lower(btrim(normalized_email))
    and normalized_email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'
  )
);

create table public.app_users (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text unique not null,
  role public.app_role not null,
  is_active boolean not null default true,
  can_view_clinical boolean not null default false,
  can_download boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid null references auth.users(id) on delete set null,
  disabled_at timestamptz null,
  constraint app_users_normalized_email check (email = lower(btrim(email)))
);

alter table public.approved_app_users enable row level security;
alter table public.app_users enable row level security;

revoke all on public.approved_app_users from public, anon, authenticated;
revoke all on public.app_users from public, anon;
grant select on public.app_users to authenticated;

create policy app_users_select_self
on public.app_users for select to authenticated
using ((select auth.uid()) = user_id);

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create or replace function private.is_active_app_user()
returns boolean language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.app_users u
    where u.user_id = (select auth.uid()) and u.is_active
  );
$$;

create or replace function private.has_app_role(required_role public.app_role)
returns boolean language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.app_users u
    where u.user_id = (select auth.uid()) and u.is_active
      and (u.role = 'ADMIN'::public.app_role or u.role = required_role)
  );
$$;

create or replace function private.can_view_clinical_media()
returns boolean language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.app_users u
    where u.user_id = (select auth.uid()) and u.is_active and u.can_view_clinical
  );
$$;

create or replace function private.can_download_media()
returns boolean language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.app_users u
    where u.user_id = (select auth.uid()) and u.is_active and u.can_download
  );
$$;

revoke all on function private.is_active_app_user() from public, anon;
revoke all on function private.has_app_role(public.app_role) from public, anon;
revoke all on function private.can_view_clinical_media() from public, anon;
revoke all on function private.can_download_media() from public, anon;
grant usage on schema private to authenticated;
grant execute on function private.is_active_app_user() to authenticated;
grant execute on function private.has_app_role(public.app_role) to authenticated;
grant execute on function private.can_view_clinical_media() to authenticated;
grant execute on function private.can_download_media() to authenticated;

create or replace function public.link_current_app_user()
returns void language plpgsql security definer
set search_path = ''
as $$
declare
  current_user_id uuid := (select auth.uid());
  auth_email text;
  approved public.approved_app_users%rowtype;
begin
  if current_user_id is null then raise exception 'authentication required' using errcode = '28000'; end if;
  select lower(btrim(u.email)) into auth_email from auth.users u where u.id = current_user_id and u.email_confirmed_at is not null;
  if auth_email is null then raise exception 'access denied' using errcode = '42501'; end if;
  select * into approved from public.approved_app_users a where a.normalized_email = auth_email and a.is_active;
  if not found then raise exception 'access denied' using errcode = '42501'; end if;
  insert into public.app_users(user_id,email,role,is_active,can_view_clinical,can_download,created_by)
  values(current_user_id,auth_email,approved.role,true,approved.can_view_clinical,approved.can_download,approved.created_by)
  on conflict(user_id) do update set
    email=excluded.email,role=excluded.role,is_active=true,
    can_view_clinical=excluded.can_view_clinical,can_download=excluded.can_download,
    disabled_at=null,updated_at=now();
end;
$$;

revoke all on function public.link_current_app_user() from public, anon;
grant execute on function public.link_current_app_user() to authenticated;

-- Staged individual-user policies. Legacy reader policies remain until the live
-- OAuth/RLS/media/refresh/logout acceptance gate has passed.
create policy source_folders_individual_read on public.source_folders for select to authenticated using ((select private.is_active_app_user()));
create policy source_files_individual_read on public.source_files for select to authenticated using ((select private.is_active_app_user()));
create policy assets_individual_read on public.assets for select to authenticated using ((select private.is_active_app_user()));
create policy asset_sources_individual_read on public.asset_sources for select to authenticated using ((select private.is_active_app_user()));
create policy asset_destinations_individual_read on public.asset_destinations for select to authenticated using ((select private.is_active_app_user()));
create policy sync_runs_admin_read on public.sync_runs for select to authenticated using ((select private.has_app_role('ADMIN'::public.app_role)));
create policy scan_runs_admin_read on public.scan_runs for select to authenticated using ((select private.has_app_role('ADMIN'::public.app_role)));
create policy migration_events_admin_read on public.migration_events for select to authenticated using ((select private.has_app_role('ADMIN'::public.app_role)));

-- Keep all application-user and media writes denied to anon/authenticated.
revoke insert, update, delete, truncate on public.approved_app_users, public.app_users from anon, authenticated;
revoke insert, update, delete, truncate on public.source_folders, public.sync_runs, public.scan_runs,
  public.source_files, public.assets, public.asset_sources, public.asset_destinations, public.migration_events
  from anon, authenticated;

commit;
