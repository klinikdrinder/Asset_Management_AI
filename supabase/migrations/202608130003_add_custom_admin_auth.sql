begin;
create extension if not exists pgcrypto with schema extensions;
create table if not exists public.admin_accounts(
 id uuid primary key default gen_random_uuid(),email text not null,password_hash text not null,full_name text,role text not null default 'admin' check(role in('admin')),
 is_active boolean not null default true,must_change_password boolean not null default false,failed_login_attempts integer not null default 0 check(failed_login_attempts>=0),locked_until timestamptz,
 password_changed_at timestamptz,last_login_at timestamptz,created_at timestamptz not null default now(),updated_at timestamptz not null default now(),
 constraint admin_accounts_email_normalized check(email=lower(btrim(email)))
);
create unique index if not exists admin_accounts_email_ci_unique on public.admin_accounts(lower(btrim(email)));
create table if not exists public.admin_sessions(
 id uuid primary key default gen_random_uuid(),admin_account_id uuid not null references public.admin_accounts(id) on delete cascade,token_hash text not null unique,
 expires_at timestamptz not null,created_at timestamptz not null default now(),last_used_at timestamptz,revoked_at timestamptz
);
create index if not exists admin_sessions_active_lookup on public.admin_sessions(token_hash,expires_at) where revoked_at is null;
create table if not exists public.admin_auth_audit(
 id bigint generated always as identity primary key,admin_account_id uuid references public.admin_accounts(id) on delete set null,event_type text not null,
 occurred_at timestamptz not null default now(),metadata jsonb not null default '{}'::jsonb
);
alter table public.admin_accounts enable row level security;
alter table public.admin_sessions enable row level security;
alter table public.admin_auth_audit enable row level security;
revoke all on public.admin_accounts,public.admin_sessions,public.admin_auth_audit from public,anon,authenticated;
grant select,insert,update,delete on public.admin_accounts,public.admin_sessions,public.admin_auth_audit to service_role;
grant usage,select on sequence public.admin_auth_audit_id_seq to service_role;
commit;
