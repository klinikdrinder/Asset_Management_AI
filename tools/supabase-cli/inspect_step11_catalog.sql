create temporary table live_migration_history(version text, name text) on commit drop;
do $$
begin
  if to_regclass('supabase_migrations.schema_migrations') is not null then
    execute 'insert into live_migration_history(version,name) select version,name from supabase_migrations.schema_migrations';
  end if;
end;
$$;
select 'migration_history' as section,
  jsonb_build_object(
    'history_table_exists',to_regclass('supabase_migrations.schema_migrations') is not null,
    'entries',coalesce(jsonb_agg(jsonb_build_object('version',version,'name',name) order by version),'[]'::jsonb)
  ) as evidence
from live_migration_history;

select 'relations' as section,
  jsonb_agg(jsonb_build_object(
    'name',n.nspname||'.'||c.relname,
    'kind',c.relkind,
    'rls',c.relrowsecurity,
    'owner',pg_get_userbyid(c.relowner),
    'options',coalesce(to_jsonb(c.reloptions),'[]'::jsonb)
  ) order by n.nspname,c.relname) as evidence
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname in ('public','private') and c.relname in (
  'source_folders','sync_runs','scan_runs','source_files','assets','asset_sources',
  'asset_destinations','migration_events','source_folder_summary','approved_app_users','app_users'
);

select 'app_role' as section,
  coalesce(jsonb_agg(e.enumlabel order by e.enumsortorder),'[]'::jsonb) as evidence
from pg_type t join pg_namespace n on n.oid=t.typnamespace
left join pg_enum e on e.enumtypid=t.oid
where n.nspname='public' and t.typname='app_role';

select 'columns' as section,
  jsonb_agg(jsonb_build_object('table',table_name,'column',column_name,'type',data_type,'nullable',is_nullable) order by table_name,ordinal_position) as evidence
from information_schema.columns
where table_schema='public' and table_name in ('source_files','asset_destinations','migration_events','approved_app_users','app_users');

select 'constraints' as section,
  jsonb_agg(jsonb_build_object('table',c.relname,'name',con.conname,'type',con.contype,'definition',pg_get_constraintdef(con.oid)) order by c.relname,con.conname) as evidence
from pg_constraint con join pg_class c on c.oid=con.conrelid join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relname in ('source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','asset_destinations','migration_events','approved_app_users','app_users');

select 'indexes' as section,
  coalesce(jsonb_agg(jsonb_build_object('table',tablename,'name',indexname) order by tablename,indexname),'[]'::jsonb) as evidence
from pg_indexes where schemaname='public' and tablename in (
  'source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','asset_destinations','migration_events','approved_app_users','app_users'
);

select 'policies' as section,
  coalesce(jsonb_agg(jsonb_build_object('table',tablename,'name',policyname,'command',cmd,'roles',roles,'using',qual,'check',with_check) order by tablename,policyname),'[]'::jsonb) as evidence
from pg_policies where schemaname='public' and tablename in (
  'source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','asset_destinations','migration_events','approved_app_users','app_users'
);

select 'functions' as section,
  coalesce(jsonb_agg(jsonb_build_object(
    'schema',n.nspname,'name',p.proname,'identity_args',pg_get_function_identity_arguments(p.oid),
    'security_definer',p.prosecdef,'config',p.proconfig,
    'anon_execute',has_function_privilege('anon',p.oid,'EXECUTE'),
    'authenticated_execute',has_function_privilege('authenticated',p.oid,'EXECUTE'),
    'service_execute',has_function_privilege('service_role',p.oid,'EXECUTE')
  ) order by n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)),'[]'::jsonb) as evidence
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname in ('public','private') and p.proname in (
  'set_updated_at','claim_source_file_hash','renew_source_file_hash_claim',
  'claim_asset_destinations','renew_asset_destination_claim','release_asset_destination_claim',
  'log_asset_destination_initialized','set_step10_migration_event_legacy_status',
  'is_active_app_user','has_app_role','can_view_clinical_media','can_download_media','link_current_app_user'
);

select 'triggers' as section,
  coalesce(jsonb_agg(jsonb_build_object('table',c.relname,'name',t.tgname,'function',p.proname) order by c.relname,t.tgname),'[]'::jsonb) as evidence
from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace join pg_proc p on p.oid=t.tgfoid
where not t.tgisinternal and n.nspname='public' and c.relname in (
  'source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','asset_destinations','migration_events'
);

select 'view_grants' as section,
  coalesce(jsonb_agg(jsonb_build_object('grantee',grantee,'privilege',privilege_type) order by grantee,privilege_type),'[]'::jsonb) as evidence
from information_schema.role_table_grants
where table_schema='public' and table_name='source_folder_summary';

select 'view_definition' as section,
  jsonb_build_object('definition',pg_get_viewdef('public.source_folder_summary'::regclass,true)) as evidence;

select 'production_counts' as section, jsonb_build_object(
  'source_folders',(select count(*) from public.source_folders),
  'source_files',(select count(*) from public.source_files),
  'assets',(select count(*) from public.assets),
  'asset_sources',(select count(*) from public.asset_sources),
  'asset_destinations',(select count(*) from public.asset_destinations),
  'migration_events',(select count(*) from public.migration_events),
  'scan_runs',(select count(*) from public.scan_runs),
  'sync_runs',(select count(*) from public.sync_runs),
  'app_users',(select count(*) from public.app_users),
  'approved_app_users',(select count(*) from public.approved_app_users)
) as evidence;

select 'pilot_folders' as section,
  jsonb_build_object(
    'count',count(*),
    'expected_labels_present',count(*) filter(where source_name in (
      'Nushad Raw Video','ALL PATIENT REVIEW','Photo/Video for Marketing (Consented by patient)'
    ))
  ) as evidence
from public.source_folders;

select 'catalog_bundle' as section, jsonb_build_object(
  'history_table_exists',to_regclass('supabase_migrations.schema_migrations') is not null,
  'relations',(select jsonb_agg(jsonb_build_object('name',n.nspname||'.'||c.relname,'kind',c.relkind,'rls',c.relrowsecurity,'owner',pg_get_userbyid(c.relowner),'options',c.reloptions) order by n.nspname,c.relname)
    from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('public','private') and c.relname in ('source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','asset_destinations','migration_events','source_folder_summary','approved_app_users','app_users')),
  'app_role',(select jsonb_agg(e.enumlabel order by e.enumsortorder) from pg_type t join pg_namespace n on n.oid=t.typnamespace join pg_enum e on e.enumtypid=t.oid where n.nspname='public' and t.typname='app_role'),
  'policies',(select jsonb_agg(jsonb_build_object('table',tablename,'name',policyname,'command',cmd,'roles',roles,'using',qual) order by tablename,policyname) from pg_policies where schemaname='public' and tablename in ('source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','asset_destinations','migration_events','approved_app_users','app_users')),
  'functions',(select jsonb_agg(jsonb_build_object('schema',n.nspname,'name',p.proname,'args',pg_get_function_identity_arguments(p.oid),'definer',p.prosecdef,'config',p.proconfig,'anon_exec',has_function_privilege('anon',p.oid,'EXECUTE'),'auth_exec',has_function_privilege('authenticated',p.oid,'EXECUTE')) order by n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname in ('public','private') and p.proname in ('set_updated_at','claim_source_file_hash','renew_source_file_hash_claim','claim_asset_destinations','renew_asset_destination_claim','release_asset_destination_claim','log_asset_destination_initialized','set_step10_migration_event_legacy_status','is_active_app_user','has_app_role','can_view_clinical_media','can_download_media','link_current_app_user')),
  'indexes',(select jsonb_agg(jsonb_build_object('table',tablename,'name',indexname) order by tablename,indexname) from pg_indexes where schemaname='public' and tablename in ('source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','asset_destinations','migration_events','approved_app_users','app_users')),
  'triggers',(select jsonb_agg(jsonb_build_object('table',c.relname,'name',t.tgname,'function',p.proname) order by c.relname,t.tgname) from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace join pg_proc p on p.oid=t.tgfoid where not t.tgisinternal and n.nspname='public' and c.relname in ('source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','asset_destinations','migration_events')),
  'columns',(select jsonb_agg(jsonb_build_object('table',table_name,'column',column_name) order by table_name,ordinal_position) from information_schema.columns where table_schema='public' and table_name in ('source_files','asset_destinations','migration_events','approved_app_users','app_users')),
  'constraints',(select jsonb_agg(jsonb_build_object('table',c.relname,'name',con.conname,'type',con.contype,'definition',pg_get_constraintdef(con.oid)) order by c.relname,con.conname) from pg_constraint con join pg_class c on c.oid=con.conrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in ('source_folders','sync_runs','scan_runs','source_files','assets','asset_sources','asset_destinations','migration_events','approved_app_users','app_users')),
  'view_grants',(select jsonb_agg(jsonb_build_object('grantee',grantee,'privilege',privilege_type) order by grantee,privilege_type) from information_schema.role_table_grants where table_schema='public' and table_name='source_folder_summary'),
  'view_definition',pg_get_viewdef('public.source_folder_summary'::regclass,true),
  'counts',jsonb_build_object('source_folders',(select count(*) from public.source_folders),'source_files',(select count(*) from public.source_files),'assets',(select count(*) from public.assets),'asset_sources',(select count(*) from public.asset_sources),'asset_destinations',(select count(*) from public.asset_destinations),'migration_events',(select count(*) from public.migration_events),'scan_runs',(select count(*) from public.scan_runs),'sync_runs',(select count(*) from public.sync_runs),'app_users',(select count(*) from public.app_users),'approved_app_users',(select count(*) from public.approved_app_users)),
  'pilot_folders',jsonb_build_object('count',(select count(*) from public.source_folders),'expected_labels_present',(select count(*) from public.source_folders where source_name in ('Nushad Raw Video','ALL PATIENT REVIEW','Photo/Video for Marketing (Consented by patient)')))
) as evidence;
