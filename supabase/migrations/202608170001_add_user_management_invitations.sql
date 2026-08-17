begin;

alter table public.app_users
  add column if not exists management_role text,
  add column if not exists invited_by uuid null references public.app_users(user_id) on delete set null,
  add column if not exists invited_at timestamptz null,
  add column if not exists invitation_accepted_at timestamptz null;

update public.app_users
set management_role = case when role = 'ADMIN'::public.app_role then 'admin' else 'user' end
where management_role is null;

alter table public.app_users alter column management_role set default 'user';
alter table public.app_users alter column management_role set not null;
alter table public.app_users drop constraint if exists app_users_management_role_check;
alter table public.app_users add constraint app_users_management_role_check
  check (management_role in ('super_admin','admin','user'));

-- Preserve and elevate the existing protected owner. The custom Admin account
-- and Supabase Auth identity were verified to have the same normalized email.
update public.app_users profile set management_role='super_admin',role='ADMIN'::public.app_role,is_active=true,disabled_at=null,updated_at=now()
where profile.email in (
  select lower(btrim(au.email)) from auth.users au
  join public.admin_accounts owner on owner.email=lower(btrim(au.email)) and owner.is_active
  where au.email is not null
);
insert into public.app_users(user_id,email,role,management_role,is_active,can_view_clinical,can_download,created_at,updated_at)
select au.id, lower(btrim(au.email)), 'ADMIN'::public.app_role, 'super_admin', true, false, true, now(), now()
from auth.users au
join public.admin_accounts owner on owner.email = lower(btrim(au.email)) and owner.is_active
where au.email is not null and not exists(select 1 from public.app_users profile where profile.email=lower(btrim(au.email)))
on conflict (user_id) do update set
  management_role='super_admin', role='ADMIN'::public.app_role, is_active=true,
  disabled_at=null, updated_at=now();

create unique index if not exists app_users_single_super_admin
  on public.app_users ((management_role)) where management_role='super_admin';

create table if not exists public.user_invitations (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid unique null references auth.users(id) on delete restrict,
  email text not null,
  assigned_role text not null check (assigned_role in ('admin','user')),
  status text not null default 'pending' check (status in ('pending','accepted','expired','cancelled')),
  invited_by uuid not null references public.app_users(user_id) on delete restrict,
  invited_at timestamptz not null default now(),
  last_sent_at timestamptz not null default now(),
  accepted_at timestamptz null,
  cancelled_at timestamptz null,
  send_count integer not null default 1 check (send_count between 1 and 50),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_invitations_email_normalized check (
    email=lower(btrim(email)) and email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'
  )
);
create unique index if not exists user_invitations_one_open_email
  on public.user_invitations(email) where status='pending';
create index if not exists user_invitations_status_sent_idx on public.user_invitations(status,last_sent_at desc);

create table if not exists public.user_management_audit (
  id bigint generated always as identity primary key,
  actor_user_id uuid null references public.app_users(user_id) on delete set null,
  action text not null,
  target_user_id uuid null references auth.users(id) on delete set null,
  target_email text null,
  role_before text null,
  role_after text null,
  outcome text not null check (outcome in ('allowed','rejected','failed')),
  metadata jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  constraint user_management_audit_target_email_normalized check (target_email is null or target_email=lower(btrim(target_email)))
);
create index if not exists user_management_audit_occurred_idx on public.user_management_audit(occurred_at desc);

create or replace function private.protect_super_admin()
returns trigger language plpgsql security definer set search_path=''
as $$
begin
  if tg_op='DELETE' and old.management_role='super_admin' then
    raise exception 'protected super admin cannot be deleted' using errcode='42501';
  end if;
  if tg_op='UPDATE' and old.management_role='super_admin' and (
    new.user_id is distinct from old.user_id or new.email is distinct from old.email or
    new.management_role is distinct from old.management_role or new.role is distinct from old.role or
    new.is_active is distinct from old.is_active or new.disabled_at is distinct from old.disabled_at
  ) then raise exception 'protected super admin cannot be modified' using errcode='42501'; end if;
  if tg_op='DELETE' then return old; end if;
  return new;
end;
$$;
drop trigger if exists protect_super_admin on public.app_users;
create trigger protect_super_admin before update or delete on public.app_users
for each row execute function private.protect_super_admin();

alter table public.user_invitations enable row level security;
alter table public.user_management_audit enable row level security;
revoke all on public.user_invitations,public.user_management_audit from public,anon,authenticated;
revoke insert,update,delete on public.app_users from anon,authenticated;
grant select,insert,update,delete on public.app_users,public.approved_app_users,public.user_invitations,public.user_management_audit to service_role;
grant usage,select on sequence public.user_management_audit_id_seq to service_role;
revoke all on function private.protect_super_admin() from public,anon,authenticated;

do $$
begin
  if (select count(*) from public.app_users where management_role='super_admin') <> 1 then
    raise exception 'exactly one existing Super Admin must be preserved';
  end if;
end;
$$;

commit;
