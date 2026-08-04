-- KDI individual-user RBAC/RLS behavioral verification.
-- Run only after 202608030001_add_individual_app_user_auth.sql has been applied.
-- Every synthetic identity and application row is enclosed by this transaction
-- and is removed by the final ROLLBACK. No production media row is mutated.

begin;

create temporary table rbac_verification_results (
  category text not null,
  status text not null check (status in ('PASS', 'FAIL', 'NOT_APPLICABLE')),
  detail text not null
) on commit drop;

create temporary table rbac_test_identities (
  scenario text primary key,
  user_id uuid not null,
  email text not null
) on commit drop;

create temporary table rbac_baselines (
  relation_name text primary key,
  row_count bigint not null
) on commit drop;

create or replace function pg_temp.assert_no_visible_rows(test_sql text, boundary text)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
declare
  visible boolean := false;
begin
  begin
    execute test_sql into visible;
  exception
    when insufficient_privilege then
      return;
  end;
  if coalesce(visible, false) then
    raise exception 'RBAC verification failed: % exposed protected rows', boundary;
  end if;
end;
$$;

create or replace function pg_temp.assert_query_true(test_sql text, boundary text)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
declare
  actual boolean := false;
begin
  execute test_sql into actual;
  if not coalesce(actual, false) then
    raise exception 'RBAC verification failed: %', boundary;
  end if;
end;
$$;

create or replace function pg_temp.assert_visible_count(
  test_sql text,
  expected_count bigint,
  object_name text,
  identity_class text
)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
declare
  actual_count bigint := 0;
begin
  begin
    execute 'select count(*) from (' || test_sql || ') as protected_probe'
      into actual_count;
  exception
    when insufficient_privilege then
      actual_count := 0;
  end;
  if actual_count is distinct from expected_count then
    raise exception
      'RBAC verification failed: object=% identity=% expected_visible_rows=% actual_visible_rows=%',
      object_name, identity_class, expected_count, actual_count;
  end if;
end;
$$;

create or replace function pg_temp.assert_permission_denied(test_sql text, boundary text)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
begin
  begin
    execute test_sql;
  exception
    when insufficient_privilege then
      return;
  end;
  raise exception 'RBAC verification failed: % was callable', boundary;
end;
$$;

create or replace function pg_temp.set_test_claims(
  requested_user_id uuid,
  requested_role text default 'authenticated',
  requested_user_metadata jsonb default '{}'::jsonb,
  requested_app_metadata jsonb default '{}'::jsonb
)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
begin
  perform pg_catalog.set_config('request.jwt.claim.sub', requested_user_id::text, true);
  perform pg_catalog.set_config(
    'request.jwt.claims',
    pg_catalog.jsonb_build_object(
      'sub', requested_user_id::text,
      'role', requested_role,
      'aud', 'authenticated',
      'user_metadata', requested_user_metadata,
      'app_metadata', requested_app_metadata
    )::text,
    true
  );
end;
$$;

grant execute on function pg_temp.assert_no_visible_rows(text, text) to anon, authenticated;
grant execute on function pg_temp.assert_query_true(text, text) to authenticated;
grant execute on function pg_temp.assert_visible_count(text, bigint, text, text) to anon, authenticated;
grant execute on function pg_temp.assert_permission_denied(text, text) to anon, authenticated;
grant execute on function pg_temp.set_test_claims(uuid, text, jsonb, jsonb) to anon, authenticated;
grant select, insert on rbac_verification_results to anon, authenticated;
grant select on rbac_test_identities, rbac_baselines to authenticated;

-- A. Schema, catalog, constraints, indexes, RLS, policies, views, and functions.
do $$
declare
  expected record;
  actual_labels text[];
begin
  select pg_catalog.array_agg(e.enumlabel order by e.enumsortorder)
    into actual_labels
  from pg_catalog.pg_type t
  join pg_catalog.pg_namespace n on n.oid = t.typnamespace
  join pg_catalog.pg_enum e on e.enumtypid = t.oid
  where n.nspname = 'public' and t.typname = 'app_role';
  if actual_labels is distinct from array['STAFF', 'ADMIN']::text[] then
    raise exception 'RBAC verification failed: app_role must contain exactly STAFF and ADMIN';
  end if;

  for expected in
    select * from (values
      ('approved_app_users','normalized_email','text',true),
      ('approved_app_users','role','app_role',true),
      ('approved_app_users','is_active','boolean',true),
      ('approved_app_users','can_view_clinical','boolean',true),
      ('approved_app_users','can_download','boolean',true),
      ('approved_app_users','created_at','timestamp with time zone',true),
      ('approved_app_users','updated_at','timestamp with time zone',true),
      ('approved_app_users','created_by','uuid',false),
      ('app_users','user_id','uuid',true),
      ('app_users','email','text',true),
      ('app_users','role','app_role',true),
      ('app_users','is_active','boolean',true),
      ('app_users','can_view_clinical','boolean',true),
      ('app_users','can_download','boolean',true),
      ('app_users','created_at','timestamp with time zone',true),
      ('app_users','updated_at','timestamp with time zone',true),
      ('app_users','created_by','uuid',false),
      ('app_users','disabled_at','timestamp with time zone',false)
    ) as required(table_name, column_name, type_name, required_not_null)
  loop
    if not exists (
      select 1
      from pg_catalog.pg_attribute a
      join pg_catalog.pg_class c on c.oid = a.attrelid
      join pg_catalog.pg_namespace n on n.oid = c.relnamespace
      where n.nspname = 'public' and c.relname = expected.table_name
        and a.attname = expected.column_name and not a.attisdropped
        and pg_catalog.format_type(a.atttypid, a.atttypmod) = expected.type_name
        and (not expected.required_not_null or a.attnotnull)
    ) then
      raise exception 'RBAC verification failed: missing/invalid %.%', expected.table_name, expected.column_name;
    end if;
  end loop;

  if not exists (
    select 1 from pg_catalog.pg_constraint c
    where c.conrelid = 'public.approved_app_users'::regclass and c.contype = 'p'
      and c.conkey = array[(select attnum from pg_catalog.pg_attribute where attrelid=c.conrelid and attname='normalized_email')]::smallint[]
  ) then raise exception 'RBAC verification failed: approved_app_users primary key missing'; end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint c
    where c.conrelid = 'public.app_users'::regclass and c.contype = 'p'
      and c.conkey = array[(select attnum from pg_catalog.pg_attribute where attrelid=c.conrelid and attname='user_id')]::smallint[]
  ) then raise exception 'RBAC verification failed: app_users primary key missing'; end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint c
    where c.conrelid = 'public.app_users'::regclass and c.contype = 'u'
      and c.conkey = array[(select attnum from pg_catalog.pg_attribute where attrelid=c.conrelid and attname='email')]::smallint[]
  ) then raise exception 'RBAC verification failed: app_users email uniqueness missing'; end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint c
    where c.conrelid = 'public.app_users'::regclass and c.contype = 'f'
      and c.confrelid = 'auth.users'::regclass
      and c.conkey @> array[(select attnum from pg_catalog.pg_attribute where attrelid=c.conrelid and attname='user_id')]::smallint[]
  ) then raise exception 'RBAC verification failed: app_users auth.users foreign key missing'; end if;
  if exists (
    select 1 from (values
      ('approved_app_users','created_by'),('app_users','created_by')
    ) required(table_name,column_name)
    where not exists (
      select 1 from pg_catalog.pg_constraint c
      where c.conrelid=pg_catalog.to_regclass('public.' || required.table_name)
        and c.contype='f' and c.confrelid='auth.users'::regclass
        and c.conkey @> array[(select attnum from pg_catalog.pg_attribute
          where attrelid=c.conrelid and attname=required.column_name)]::smallint[]
    )
  ) then raise exception 'RBAC verification failed: created_by auth.users foreign key missing'; end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint c
    where c.conrelid = 'public.approved_app_users'::regclass and c.contype = 'c'
      and pg_catalog.pg_get_constraintdef(c.oid) ~ 'normalized_email'
  ) or not exists (
    select 1 from pg_catalog.pg_constraint c
    where c.conrelid = 'public.app_users'::regclass and c.contype = 'c'
      and pg_catalog.pg_get_constraintdef(c.oid) ~ 'lower.*btrim'
  ) then raise exception 'RBAC verification failed: normalized email constraints missing'; end if;

  if not exists (select 1 from pg_catalog.pg_indexes where schemaname='public' and tablename='approved_app_users' and indexdef like 'CREATE UNIQUE INDEX%normalized_email%')
    or not exists (select 1 from pg_catalog.pg_indexes where schemaname='public' and tablename='app_users' and indexdef like 'CREATE UNIQUE INDEX%user_id%')
    or not exists (select 1 from pg_catalog.pg_indexes where schemaname='public' and tablename='app_users' and indexdef like 'CREATE UNIQUE INDEX%email%') then
    raise exception 'RBAC verification failed: required identity indexes missing';
  end if;

  if exists (
    select 1 from (values
      ('approved_app_users'),('app_users'),('source_folders'),('source_files'),
      ('assets'),('asset_sources'),('asset_destinations'),('sync_runs'),
      ('scan_runs'),('migration_events')
    ) required(table_name)
    left join pg_catalog.pg_class c on c.oid = pg_catalog.to_regclass('public.' || required.table_name)
    where c.oid is null or not c.relrowsecurity
  ) then raise exception 'RBAC verification failed: protected table without RLS'; end if;

  if not exists (
    select 1 from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
    where n.nspname='public' and c.relname='source_folder_summary' and c.relkind='v'
      and coalesce(c.reloptions, '{}'::text[]) @> array['security_invoker=true']
      and coalesce(c.reloptions, '{}'::text[]) @> array['security_barrier=true']
  ) then raise exception 'RBAC verification failed: source_folder_summary is not security_invoker'; end if;
  if not exists (
    select 1 from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
    where n.nspname='public' and c.relname='source_folder_summary' and c.relkind='v'
      and pg_catalog.pg_get_viewdef(c.oid,true) ~ '\mapp_users\M'
      and pg_catalog.pg_get_viewdef(c.oid,true) ~ 'auth\.uid\(\)'
      and pg_catalog.pg_get_viewdef(c.oid,true) ~ 'is_active'
  ) then raise exception 'RBAC verification failed: source_folder_summary explicit active-user gate missing'; end if;

  if exists (
    select 1 from (values
      ('app_users_select_self'),('source_folders_individual_read'),
      ('source_files_individual_read'),('assets_individual_read'),
      ('asset_sources_individual_read'),('asset_destinations_individual_read'),
      ('sync_runs_admin_read'),('scan_runs_admin_read'),('migration_events_admin_read')
    ) required(policy_name)
    left join pg_catalog.pg_policies p on p.schemaname='public' and p.policyname=required.policy_name
    where p.policyname is null or p.cmd <> 'SELECT' or p.roles <> array['authenticated']::name[]
  ) then raise exception 'RBAC verification failed: expected authenticated SELECT policy missing'; end if;

  if exists (
    select 1 from pg_catalog.pg_policies
    where schemaname='public'
      and tablename in ('source_folders','source_files','assets','asset_sources',
        'asset_destinations','sync_runs','scan_runs','migration_events')
      and (coalesce(qual,'') ~ 'kdi_media' or coalesce(qual,'')='true')
  ) then
    raise exception 'RBAC verification failed: broad/shared-reader policy bypass remains';
  end if;

  if exists (
    select 1 from (values
      ('private','is_active_app_user'),('private','has_app_role'),
      ('private','can_view_clinical_media'),('private','can_download_media'),
      ('public','link_current_app_user')
    ) required(schema_name,function_name)
    left join pg_catalog.pg_namespace n on n.nspname=required.schema_name
    left join pg_catalog.pg_proc p on p.pronamespace=n.oid and p.proname=required.function_name
    where p.oid is null or not p.prosecdef or not exists (
      select 1 from unnest(coalesce(p.proconfig, '{}'::text[])) setting
      where setting ~ '^search_path=(""|)$'
    )
  ) then raise exception 'RBAC verification failed: missing or unsafe SECURITY DEFINER helper'; end if;

  if exists (
    select 1 from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
    where ((n.nspname='private' and p.proname in ('is_active_app_user','has_app_role','can_view_clinical_media','can_download_media'))
       or (n.nspname='public' and p.proname='link_current_app_user'))
      and pg_catalog.has_function_privilege('anon',p.oid,'EXECUTE')
  ) then raise exception 'RBAC verification failed: unsafe helper execute grant'; end if;

  if exists (
    select 1 from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname in (
      'claim_source_file_hash','renew_source_file_hash_claim','claim_asset_destinations',
      'renew_asset_destination_claim','release_asset_destination_claim',
      'set_step10_migration_event_legacy_status'
    ) and (pg_catalog.has_function_privilege('anon',p.oid,'EXECUTE')
      or pg_catalog.has_function_privilege('authenticated',p.oid,'EXECUTE'))
  ) then raise exception 'RBAC verification failed: privileged migration RPC exposed'; end if;

  insert into rbac_verification_results values
    ('A_SCHEMA_CATALOG','PASS','Types, columns, constraints, indexes, RLS, policies, view security, helper safety, and RPC grants verified');
end;
$$;

-- Capture read-only production baselines. They are used only to prove RLS
-- visibility; no names, identifiers, or media metadata are emitted.
insert into rbac_baselines values
  ('source_folders',(select count(*) from public.source_folders)),
  ('source_files',(select count(*) from public.source_files)),
  ('assets',(select count(*) from public.assets)),
  ('asset_sources',(select count(*) from public.asset_sources)),
  ('asset_destinations',(select count(*) from public.asset_destinations)),
  ('verified_media',(select count(*) from public.source_files sf join public.asset_destinations ad on ad.selected_source_file_id=sf.id where ad.upload_status='VERIFIED')),
  ('sync_runs',(select count(*) from public.sync_runs)),
  ('scan_runs',(select count(*) from public.scan_runs)),
  ('migration_events',(select count(*) from public.migration_events));

do $$
begin
  if not exists (select 1 from rbac_baselines where relation_name='source_folders' and row_count > 0) then
    raise exception 'RBAC verification failed: Staff read behavior cannot be proved against an empty source_folders table';
  end if;
end;
$$;

insert into rbac_test_identities(scenario,user_id,email) values
  ('unapproved',gen_random_uuid(),'rbac-unapproved-' || gen_random_uuid() || '@example.invalid'),
  ('staff_allowed',gen_random_uuid(),'rbac-staff-allowed-' || gen_random_uuid() || '@example.invalid'),
  ('staff_restricted',gen_random_uuid(),'rbac-staff-restricted-' || gen_random_uuid() || '@example.invalid'),
  ('admin',gen_random_uuid(),'rbac-admin-' || gen_random_uuid() || '@example.invalid'),
  ('disabled_staff',gen_random_uuid(),'rbac-disabled-staff-' || gen_random_uuid() || '@example.invalid'),
  ('disabled_admin',gen_random_uuid(),'rbac-disabled-admin-' || gen_random_uuid() || '@example.invalid');

insert into auth.users(id,aud,role,email,email_confirmed_at,raw_app_meta_data,raw_user_meta_data,created_at,updated_at)
select user_id,'authenticated','authenticated',email,now(),'{}'::jsonb,'{}'::jsonb,now(),now()
from rbac_test_identities;

insert into public.approved_app_users(normalized_email,role,is_active,can_view_clinical,can_download)
select email,
  case when scenario='admin' then 'ADMIN'::public.app_role else 'STAFF'::public.app_role end,
  true,
  scenario in ('staff_allowed','admin'),
  scenario in ('staff_allowed','admin')
from rbac_test_identities
where scenario in ('staff_allowed','staff_restricted','admin');

-- Link active approved identities through the same protected function used by
-- the OAuth callback. This also verifies that no auth.users row is fabricated
-- by application code.
set local role authenticated;
select pg_temp.set_test_claims(user_id) from rbac_test_identities where scenario='staff_allowed';
select public.link_current_app_user();
select pg_temp.set_test_claims(user_id) from rbac_test_identities where scenario='staff_restricted';
select public.link_current_app_user();
select pg_temp.set_test_claims(user_id) from rbac_test_identities where scenario='admin';
select public.link_current_app_user();
reset role;

insert into public.app_users(user_id,email,role,is_active,can_view_clinical,can_download,disabled_at)
select user_id,email,
  case when scenario='disabled_admin' then 'ADMIN'::public.app_role else 'STAFF'::public.app_role end,
  false,false,false,now()
from rbac_test_identities where scenario in ('disabled_staff','disabled_admin');

-- B. Anonymous identity.
set local role anon;
select pg_temp.set_test_claims('00000000-0000-0000-0000-000000000000'::uuid,'anon');
select pg_temp.assert_visible_count('select 1 from public.source_folder_summary',0,'public.source_folder_summary','anonymous');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.source_files)','anonymous source_files');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.assets)','anonymous assets');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.asset_sources)','anonymous asset_sources');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.asset_destinations)','anonymous media destinations');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.sync_runs)','anonymous sync_runs');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.scan_runs)','anonymous scan_runs');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.migration_events)','anonymous migration_events');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.approved_app_users)','anonymous approved_app_users');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.app_users)','anonymous app_users');
select pg_temp.assert_permission_denied('select private.is_active_app_user()','anonymous private authorization helper');
select pg_temp.assert_permission_denied('select public.link_current_app_user()','anonymous account linker');
insert into rbac_verification_results values ('B_ANONYMOUS','PASS','Anonymous library, Admin, identity-table, helper, media-resolution, write-grant, and migration-RPC access denied');
reset role;

-- C. Authenticated identity without approved_app_users/app_users membership.
set local role authenticated;
select pg_temp.set_test_claims(user_id) from rbac_test_identities where scenario='unapproved';
select pg_temp.assert_visible_count('select 1 from public.source_folder_summary',0,'public.source_folder_summary','unapproved_authenticated');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.source_files)','unapproved source_files');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.asset_destinations)','unapproved media resolution');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.source_files sf join public.asset_destinations ad on ad.selected_source_file_id=sf.id where ad.upload_status=''VERIFIED'')','unapproved verified-media resolution');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.sync_runs)','unapproved sync_runs');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.scan_runs)','unapproved scan_runs');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.migration_events)','unapproved migration_events');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.app_users)','unapproved app_users');
select pg_temp.assert_query_true('select not private.is_active_app_user()','unapproved helper returned active');
select pg_temp.assert_query_true('select not private.has_app_role(''STAFF''::public.app_role)','unapproved helper returned STAFF');
select pg_temp.assert_query_true('select not private.has_app_role(''ADMIN''::public.app_role)','unapproved helper returned ADMIN');
select pg_temp.assert_query_true('select not private.can_view_clinical_media()','unapproved clinical helper allowed');
select pg_temp.assert_query_true('select not private.can_download_media()','unapproved download helper allowed');
select pg_temp.assert_permission_denied('select public.link_current_app_user()','unapproved account linking');
insert into rbac_verification_results values ('C_UNAPPROVED','PASS','Authenticated identity without an active profile receives no library, Admin, media, helper, or write access');
reset role;

-- D. Active STAFF identities: one allowed and one permission-restricted.
set local role authenticated;
select pg_temp.set_test_claims(
  user_id,'authenticated','{"role":"ADMIN"}'::jsonb,'{"role":"ADMIN"}'::jsonb
) from rbac_test_identities where scenario='staff_allowed';
select pg_temp.assert_query_true('select private.is_active_app_user()','active STAFF not recognized');
select pg_temp.assert_query_true('select private.has_app_role(''STAFF''::public.app_role)','STAFF role denied');
select pg_temp.assert_query_true('select not private.has_app_role(''ADMIN''::public.app_role)','STAFF metadata spoof granted ADMIN');
select pg_temp.assert_query_true('select private.can_view_clinical_media()','allowed STAFF clinical helper denied');
select pg_temp.assert_query_true('select private.can_download_media()','allowed STAFF download helper denied');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''source_folders'') from public.source_folders','STAFF source_folders visibility mismatch');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''source_files'') from public.source_files','STAFF source_files visibility mismatch');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''assets'') from public.assets','STAFF assets visibility mismatch');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''asset_sources'') from public.asset_sources','STAFF asset_sources visibility mismatch');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''asset_destinations'') from public.asset_destinations','STAFF media destination visibility mismatch');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''verified_media'') from public.source_files sf join public.asset_destinations ad on ad.selected_source_file_id=sf.id where ad.upload_status=''VERIFIED''','STAFF verified-media resolution mismatch');
select pg_temp.assert_visible_count(
  'select 1 from public.source_folder_summary',
  (select row_count from rbac_baselines where relation_name='source_folders'),
  'public.source_folder_summary',
  'active_staff'
);
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.sync_runs)','STAFF sync_runs');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.scan_runs)','STAFF scan_runs');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.migration_events)','STAFF migration_events');
select pg_temp.assert_query_true('select count(*)=1 and bool_and(user_id=auth.uid()) from public.app_users','STAFF can see another profile');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.approved_app_users)','STAFF approved-user management records');

select pg_temp.set_test_claims(user_id) from rbac_test_identities where scenario='staff_restricted';
select pg_temp.assert_query_true('select private.is_active_app_user()','restricted STAFF not active');
select pg_temp.assert_query_true('select not private.can_view_clinical_media()','restricted STAFF clinical helper allowed');
select pg_temp.assert_query_true('select not private.can_download_media()','restricted STAFF download helper allowed');
insert into rbac_verification_results values ('D_STAFF','PASS','STAFF library/view access, Admin denial, self-profile isolation, metadata-spoof resistance, and permission helpers verified');
insert into rbac_verification_results values ('D_CLINICAL_ROW_FILTER','NOT_APPLICABLE','No clinical-classification column or protected clinical-media resolver exists in the deployed repository schema; can_view_clinical helper behavior is verified');
reset role;

-- E. Active ADMIN identity.
set local role authenticated;
select pg_temp.set_test_claims(user_id) from rbac_test_identities where scenario='admin';
select pg_temp.assert_query_true('select private.is_active_app_user()','active ADMIN not recognized');
select pg_temp.assert_query_true('select private.has_app_role(''ADMIN''::public.app_role)','ADMIN role denied');
select pg_temp.assert_query_true('select private.has_app_role(''STAFF''::public.app_role)','ADMIN Staff capability denied');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''source_folders'') from public.source_folders','ADMIN Staff library visibility mismatch');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''source_files'') from public.source_files','ADMIN source_files visibility mismatch');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''sync_runs'') from public.sync_runs','ADMIN sync_runs visibility mismatch');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''scan_runs'') from public.scan_runs','ADMIN scan_runs visibility mismatch');
select pg_temp.assert_query_true('select count(*)=(select row_count from pg_temp.rbac_baselines where relation_name=''migration_events'') from public.migration_events','ADMIN migration_events visibility mismatch');
select pg_temp.assert_query_true('select count(*)=1 and bool_and(user_id=auth.uid()) from public.app_users','ADMIN can see another profile');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.approved_app_users)','ADMIN approved-user management records');
insert into rbac_verification_results values ('E_ADMIN','PASS','ADMIN Staff-library and operational visibility, self-profile isolation, active status, and permission helpers verified');
reset role;

-- F. Disabled STAFF and ADMIN identities.
set local role authenticated;
select pg_temp.set_test_claims(user_id) from rbac_test_identities where scenario='disabled_staff';
select pg_temp.assert_query_true('select not private.is_active_app_user()','disabled STAFF active helper allowed');
select pg_temp.assert_query_true('select not private.has_app_role(''STAFF''::public.app_role)','disabled STAFF role helper allowed');
select pg_temp.assert_query_true('select not private.can_download_media()','disabled STAFF download helper allowed');
select pg_temp.assert_query_true('select not private.can_view_clinical_media()','disabled STAFF clinical helper allowed');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.source_files)','disabled STAFF source_files');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.asset_destinations)','disabled STAFF media resolution');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.sync_runs)','disabled STAFF Admin records');
select pg_temp.set_test_claims(user_id) from rbac_test_identities where scenario='disabled_admin';
select pg_temp.assert_query_true('select not private.is_active_app_user()','disabled ADMIN active helper allowed');
select pg_temp.assert_query_true('select not private.has_app_role(''ADMIN''::public.app_role)','disabled ADMIN role helper allowed');
select pg_temp.assert_query_true('select not private.can_download_media()','disabled ADMIN download helper allowed');
select pg_temp.assert_query_true('select not private.can_view_clinical_media()','disabled ADMIN clinical helper allowed');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.source_files)','disabled ADMIN source_files');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.asset_destinations)','disabled ADMIN media resolution');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.sync_runs)','disabled ADMIN sync_runs');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.scan_runs)','disabled ADMIN scan_runs');
select pg_temp.assert_no_visible_rows('select exists(select 1 from public.migration_events)','disabled ADMIN migration_events');
insert into rbac_verification_results values ('F_DISABLED','PASS','Disabled STAFF and ADMIN helpers, library, operational, media-resolution, and write access denied');
reset role;

-- G. Role spoofing. The active STAFF scenario deliberately carries ADMIN in
-- both editable user_metadata and client-supplied app_metadata.role; protected
-- app_users remains authoritative. The unapproved scenario proves a JWT alone
-- is insufficient. Legacy kdi_media_* flags are deliberately absent.
insert into rbac_verification_results values
  ('G_ROLE_SPOOFING','PASS','STAFF remained non-ADMIN despite supplied metadata; JWT without app_users membership had no access; auth.uid() profile lookup remained authoritative');

-- H. Write denial and privileged migration mutation denial. Catalog checks are
-- used instead of issuing production-table DML, so this verifier contains no
-- source/media/migration mutation statement, even one intended to be denied.
do $$
declare
  protected_table text;
begin
  foreach protected_table in array array[
    'approved_app_users','app_users','source_folders','source_files','assets',
    'asset_sources','asset_destinations','sync_runs','scan_runs','migration_events'
  ] loop
    if pg_catalog.has_table_privilege('anon','public.' || protected_table,'INSERT')
      or pg_catalog.has_table_privilege('anon','public.' || protected_table,'UPDATE')
      or pg_catalog.has_table_privilege('anon','public.' || protected_table,'DELETE')
      or pg_catalog.has_table_privilege('anon','public.' || protected_table,'TRUNCATE')
      or pg_catalog.has_table_privilege('authenticated','public.' || protected_table,'INSERT')
      or pg_catalog.has_table_privilege('authenticated','public.' || protected_table,'UPDATE')
      or pg_catalog.has_table_privilege('authenticated','public.' || protected_table,'DELETE')
      or pg_catalog.has_table_privilege('authenticated','public.' || protected_table,'TRUNCATE') then
      raise exception 'RBAC verification failed: write privilege exists on %', protected_table;
    end if;
    if exists (
      select 1 from pg_catalog.pg_policies
      where schemaname='public' and tablename=protected_table
        and cmd in ('INSERT','UPDATE','DELETE','ALL')
        and roles && array['anon','authenticated']::name[]
    ) then raise exception 'RBAC verification failed: write policy exists on %', protected_table; end if;
  end loop;
  insert into rbac_verification_results values
    ('H_WRITE_DENIAL','PASS','STAFF/ADMIN write grants and write policies absent; privileged migration RPC execution denied to anon/authenticated');
end;
$$;

insert into rbac_verification_results values
  ('MEDIA_RESOLVER_RPC','NOT_APPLICABLE','Preview/download use server authorization plus RLS joins on source_files and verified asset_destinations; no database media-resolution RPC exists');
insert into rbac_verification_results values
  ('TRANSACTION_ISOLATION','PASS','Synthetic auth.users, approved_app_users, and app_users rows are transaction-scoped and removed by the final ROLLBACK; production media tables are read only');

select category, status, detail
from rbac_verification_results
order by category;

select 'INDIVIDUAL_APP_USER_AUTH_BEHAVIOR_VERIFIED' as verification_marker;

rollback;
