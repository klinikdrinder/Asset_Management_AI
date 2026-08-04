-- Transactional production verifier: catalog and synthetic identities only.
-- All test records are rolled back and no production record is modified.
begin;

create temp table firebase_bridge_counts_before as
select 'app_users'::text relation,count(*)::bigint rows from public.app_users union all
select 'source_folders',count(*) from public.source_folders union all
select 'source_files',count(*) from public.source_files union all
select 'assets',count(*) from public.assets union all
select 'asset_sources',count(*) from public.asset_sources union all
select 'asset_destinations',count(*) from public.asset_destinations union all
select 'sync_runs',count(*) from public.sync_runs union all
select 'scan_runs',count(*) from public.scan_runs union all
select 'migration_events',count(*) from public.migration_events;


do $$
declare view_options text[]; view_definition text;
begin
  if not exists(select 1 from information_schema.columns where table_schema='public' and table_name='app_users' and column_name='firebase_uid' and data_type='text') then raise exception 'firebase_uid text column missing'; end if;
  if not exists(select 1 from pg_indexes where schemaname='public' and tablename='app_users' and indexname='app_users_firebase_uid_unique') then raise exception 'firebase UID uniqueness missing'; end if;
  if has_function_privilege('authenticated','public.bootstrap_firebase_app_user(text,text)','EXECUTE') or has_function_privilege('anon','public.bootstrap_firebase_app_user(text,text)','EXECUTE') then raise exception 'bootstrap RPC exposed'; end if;
  select pg_get_viewdef(c.oid,true),c.reloptions into view_definition,view_options from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname='source_folder_summary';
  if view_definition !~ 'current_app_user_id' or not coalesce(view_options,'{}') @> array['security_invoker=true'] or not coalesce(view_options,'{}') @> array['security_barrier=true'] then raise exception 'source_folder_summary boundary regressed'; end if;
end $$;

create temp table firebase_test_users(scenario text primary key,user_id uuid,email text,firebase_uid text,role public.app_role,is_active boolean,clinical boolean,download boolean);
insert into firebase_test_users values
('staff',gen_random_uuid(),'firebase-staff@example.invalid','firebase-staff-test','STAFF',true,true,false),
('admin',gen_random_uuid(),'firebase-admin@example.invalid','firebase-admin-test','ADMIN',true,false,true),
('inactive',gen_random_uuid(),'firebase-inactive@example.invalid','firebase-inactive-test','STAFF',false,true,true);

insert into auth.users(id,aud,role,email,email_confirmed_at,raw_app_meta_data,raw_user_meta_data,created_at,updated_at)
select user_id,'authenticated','authenticated',email,now(),'{}','{}',now(),now() from firebase_test_users;
insert into public.app_users(user_id,email,firebase_uid,firebase_linked_at,role,is_active,can_view_clinical,can_download)
select user_id,email,firebase_uid,now(),role,is_active,clinical,download from firebase_test_users;

create or replace function pg_temp.set_firebase_claims(uid text,issuer text='https://securetoken.google.com/kdi-media-library',audience text='kdi-media-library',verified boolean=true,metadata jsonb='{}') returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims',jsonb_build_object('sub',uid,'iss',issuer,'aud',audience,'email_verified',verified,'role','authenticated','user_metadata',metadata)::text,true);
end $$;

set local role authenticated;
select pg_temp.set_firebase_claims('firebase-staff-test',metadata=>' {"role":"ADMIN","can_download":true}'::jsonb);
do $$ begin
  if not private.is_active_app_user() or not private.has_app_role('STAFF') or private.has_app_role('ADMIN') then raise exception 'STAFF boundary failed'; end if;
  if not private.can_view_clinical_media() or private.can_download_media() then raise exception 'STAFF independent permissions failed'; end if;
end $$;

select pg_temp.set_firebase_claims('firebase-admin-test');
do $$ begin
  if not private.has_app_role('ADMIN') then raise exception 'ADMIN boundary failed'; end if;
  if private.can_view_clinical_media() or not private.can_download_media() then raise exception 'ADMIN independent permissions failed'; end if;
end $$;

select pg_temp.set_firebase_claims('firebase-inactive-test');
do $$ begin if private.is_active_app_user() or private.has_app_role('STAFF') then raise exception 'inactive identity allowed'; end if; end $$;
select pg_temp.set_firebase_claims('unknown-firebase-user');
do $$ begin if private.is_active_app_user() then raise exception 'unknown identity allowed'; end if; end $$;
select pg_temp.set_firebase_claims('firebase-staff-test','https://securetoken.google.com/attacker');
do $$ begin if private.is_active_app_user() then raise exception 'wrong issuer allowed'; end if; end $$;
select pg_temp.set_firebase_claims('firebase-staff-test',audience=>'attacker');
do $$ begin if private.is_active_app_user() then raise exception 'wrong audience allowed'; end if; end $$;
select pg_temp.set_firebase_claims('firebase-staff-test',verified=>false);
do $$ begin if private.is_active_app_user() then raise exception 'unverified email allowed'; end if; end $$;
reset role;

do $$ begin
  if exists(
    select 1 from firebase_bridge_counts_before b join (
      select 'app_users'::text relation,count(*)::bigint rows from public.app_users where user_id not in(select user_id from firebase_test_users) union all
      select 'source_folders',count(*) from public.source_folders union all select 'source_files',count(*) from public.source_files union all
      select 'assets',count(*) from public.assets union all select 'asset_sources',count(*) from public.asset_sources union all
      select 'asset_destinations',count(*) from public.asset_destinations union all select 'sync_runs',count(*) from public.sync_runs union all
      select 'scan_runs',count(*) from public.scan_runs union all select 'migration_events',count(*) from public.migration_events
    ) a using(relation) where a.rows<>b.rows
  ) then raise exception 'production count reconciliation failed'; end if;
end $$;

select 'FIREBASE_IDENTITY_BRIDGE_VERIFIED' result;
rollback;
