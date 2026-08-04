-- Final, read-only verification of the KDI foundation database.
-- Source of truth:
--   202607280001_create_foundation_schema.sql
--   202607280002_seed_three_source_folders.sql
--
-- This statement returns only MISSING/MISMATCH findings, followed by OVERALL.
-- It intentionally does not depend on supabase_migrations.schema_migrations.

with
expected_tables(table_name) as (
  values
    ('source_folders'), ('sync_runs'), ('scan_runs'), ('source_files'),
    ('assets'), ('asset_sources'), ('migration_events')
),
expected_columns(table_name, column_name, data_type, nullable, default_re) as (
  values
    ('source_folders','id','uuid',false,'gen_random_uuid\(\)'),
    ('source_folders','source_name','text',false,null),
    ('source_folders','account_name','text',false,null),
    ('source_folders','folder_url','text',false,null),
    ('source_folders','google_folder_id','text',false,null),
    ('source_folders','active','boolean',false,'true'),
    ('source_folders','access_status','text',false,'''PENDING''::text'),
    ('source_folders','permission_role','text',false,'''UNKNOWN''::text'),
    ('source_folders','last_access_checked_at','timestamp with time zone',true,null),
    ('source_folders','last_scan_at','timestamp with time zone',true,null),
    ('source_folders','last_successful_scan_at','timestamp with time zone',true,null),
    ('source_folders','notes','text',true,null),
    ('source_folders','created_at','timestamp with time zone',false,'now\(\)'),
    ('source_folders','updated_at','timestamp with time zone',false,'now\(\)'),
    ('sync_runs','id','uuid',false,'gen_random_uuid\(\)'),
    ('sync_runs','run_type','text',false,'''MANUAL''::text'),
    ('sync_runs','status','text',false,'''QUEUED''::text'),
    ('sync_runs','started_at','timestamp with time zone',true,null),
    ('sync_runs','completed_at','timestamp with time zone',true,null),
    ('sync_runs','folders_total','integer',false,'0'),
    ('sync_runs','folders_succeeded','integer',false,'0'),
    ('sync_runs','folders_failed','integer',false,'0'),
    ('sync_runs','files_discovered','integer',false,'0'),
    ('sync_runs','files_taken','integer',false,'0'),
    ('sync_runs','files_skipped','integer',false,'0'),
    ('sync_runs','files_uploaded','integer',false,'0'),
    ('sync_runs','duplicates_found','integer',false,'0'),
    ('sync_runs','files_failed','integer',false,'0'),
    ('sync_runs','error_message','text',true,null),
    ('sync_runs','metadata','jsonb',false,'''{}''::jsonb'),
    ('sync_runs','created_at','timestamp with time zone',false,'now\(\)'),
    ('sync_runs','updated_at','timestamp with time zone',false,'now\(\)'),
    ('scan_runs','id','uuid',false,'gen_random_uuid\(\)'),
    ('scan_runs','sync_run_id','uuid',true,null),
    ('scan_runs','source_folder_id','uuid',false,null),
    ('scan_runs','run_mode','text',false,'''DRY_RUN''::text'),
    ('scan_runs','status','text',false,'''QUEUED''::text'),
    ('scan_runs','started_at','timestamp with time zone',true,null),
    ('scan_runs','completed_at','timestamp with time zone',true,null),
    ('scan_runs','files_discovered','integer',false,'0'),
    ('scan_runs','files_taken','integer',false,'0'),
    ('scan_runs','files_skipped','integer',false,'0'),
    ('scan_runs','files_uploaded','integer',false,'0'),
    ('scan_runs','duplicates_found','integer',false,'0'),
    ('scan_runs','files_failed','integer',false,'0'),
    ('scan_runs','next_page_token','text',true,null),
    ('scan_runs','error_message','text',true,null),
    ('scan_runs','metadata','jsonb',false,'''{}''::jsonb'),
    ('scan_runs','created_at','timestamp with time zone',false,'now\(\)'),
    ('scan_runs','updated_at','timestamp with time zone',false,'now\(\)'),
    ('source_files','id','uuid',false,'gen_random_uuid\(\)'),
    ('source_files','source_folder_id','uuid',false,null),
    ('source_files','last_scan_run_id','uuid',true,null),
    ('source_files','google_file_id','text',false,null),
    ('source_files','file_name','text',false,null),
    ('source_files','mime_type','text',true,null),
    ('source_files','file_extension','text',true,null),
    ('source_files','size_bytes','bigint',true,null),
    ('source_files','md5_checksum','text',true,null),
    ('source_files','drive_created_at','timestamp with time zone',true,null),
    ('source_files','drive_modified_at','timestamp with time zone',true,null),
    ('source_files','web_view_link','text',true,null),
    ('source_files','thumbnail_link','text',true,null),
    ('source_files','parent_google_folder_id','text',true,null),
    ('source_files','relative_path','text',true,null),
    ('source_files','decision','text',false,'''PENDING''::text'),
    ('source_files','processing_status','text',false,'''DISCOVERED''::text'),
    ('source_files','processing_error','text',true,null),
    ('source_files','skip_reason','text',true,null),
    ('source_files','destination_file_id','text',true,null),
    ('source_files','destination_web_view_link','text',true,null),
    ('source_files','duplicate_of_source_file_id','uuid',true,null),
    ('source_files','uploaded_at','timestamp with time zone',true,null),
    ('source_files','trashed','boolean',false,'false'),
    ('source_files','is_missing','boolean',false,'false'),
    ('source_files','first_seen_at','timestamp with time zone',false,'now\(\)'),
    ('source_files','last_seen_at','timestamp with time zone',false,'now\(\)'),
    ('source_files','metadata','jsonb',false,'''{}''::jsonb'),
    ('source_files','created_at','timestamp with time zone',false,'now\(\)'),
    ('source_files','updated_at','timestamp with time zone',false,'now\(\)'),
    ('assets','id','uuid',false,'gen_random_uuid\(\)'),
    ('assets','content_hash','text',true,null),
    ('assets','file_name','text',false,null),
    ('assets','mime_type','text',true,null),
    ('assets','file_extension','text',true,null),
    ('assets','size_bytes','bigint',true,null),
    ('assets','storage_bucket','text',true,null),
    ('assets','storage_path','text',true,null),
    ('assets','upload_status','text',false,'''PENDING''::text'),
    ('assets','uploaded_at','timestamp with time zone',true,null),
    ('assets','last_verified_at','timestamp with time zone',true,null),
    ('assets','upload_error','text',true,null),
    ('assets','metadata','jsonb',false,'''{}''::jsonb'),
    ('assets','created_at','timestamp with time zone',false,'now\(\)'),
    ('assets','updated_at','timestamp with time zone',false,'now\(\)'),
    ('asset_sources','id','uuid',false,'gen_random_uuid\(\)'),
    ('asset_sources','asset_id','uuid',false,null),
    ('asset_sources','source_file_id','uuid',false,null),
    ('asset_sources','relationship_type','text',false,'''ORIGINAL''::text'),
    ('asset_sources','created_at','timestamp with time zone',false,'now\(\)'),
    ('asset_sources','updated_at','timestamp with time zone',false,'now\(\)'),
    ('migration_events','id','uuid',false,'gen_random_uuid\(\)'),
    ('migration_events','sync_run_id','uuid',true,null),
    ('migration_events','scan_run_id','uuid',true,null),
    ('migration_events','source_folder_id','uuid',true,null),
    ('migration_events','source_file_id','uuid',true,null),
    ('migration_events','asset_id','uuid',true,null),
    ('migration_events','event_type','text',false,null),
    ('migration_events','event_status','text',false,'''INFO''::text'),
    ('migration_events','message','text',true,null),
    ('migration_events','details','jsonb',false,'''{}''::jsonb'),
    ('migration_events','occurred_at','timestamp with time zone',false,'now\(\)'),
    ('migration_events','created_at','timestamp with time zone',false,'now\(\)'),
    ('migration_events','updated_at','timestamp with time zone',false,'now\(\)')
),
expected_constraints(table_name, constraint_name, kind, definition_re) as (
  values
    ('source_folders','source_folders_pkey','PRIMARY KEY','PRIMARY KEY \(id\)'),
    ('sync_runs','sync_runs_pkey','PRIMARY KEY','PRIMARY KEY \(id\)'),
    ('scan_runs','scan_runs_pkey','PRIMARY KEY','PRIMARY KEY \(id\)'),
    ('source_files','source_files_pkey','PRIMARY KEY','PRIMARY KEY \(id\)'),
    ('assets','assets_pkey','PRIMARY KEY','PRIMARY KEY \(id\)'),
    ('asset_sources','asset_sources_pkey','PRIMARY KEY','PRIMARY KEY \(id\)'),
    ('migration_events','migration_events_pkey','PRIMARY KEY','PRIMARY KEY \(id\)'),
    ('scan_runs','scan_runs_sync_run_id_fkey','FOREIGN KEY','FOREIGN KEY \(sync_run_id\) REFERENCES sync_runs\(id\) ON DELETE SET NULL'),
    ('scan_runs','scan_runs_source_folder_id_fkey','FOREIGN KEY','FOREIGN KEY \(source_folder_id\) REFERENCES source_folders\(id\) ON DELETE CASCADE'),
    ('source_files','source_files_source_folder_id_fkey','FOREIGN KEY','FOREIGN KEY \(source_folder_id\) REFERENCES source_folders\(id\) ON DELETE CASCADE'),
    ('source_files','source_files_last_scan_run_id_fkey','FOREIGN KEY','FOREIGN KEY \(last_scan_run_id\) REFERENCES scan_runs\(id\) ON DELETE SET NULL'),
    ('source_files','source_files_duplicate_of_source_file_id_fkey','FOREIGN KEY','FOREIGN KEY \(duplicate_of_source_file_id\) REFERENCES source_files\(id\) ON DELETE SET NULL'),
    ('asset_sources','asset_sources_asset_id_fkey','FOREIGN KEY','FOREIGN KEY \(asset_id\) REFERENCES assets\(id\) ON DELETE CASCADE'),
    ('asset_sources','asset_sources_source_file_id_fkey','FOREIGN KEY','FOREIGN KEY \(source_file_id\) REFERENCES source_files\(id\) ON DELETE CASCADE'),
    ('migration_events','migration_events_sync_run_id_fkey','FOREIGN KEY','FOREIGN KEY \(sync_run_id\) REFERENCES sync_runs\(id\) ON DELETE SET NULL'),
    ('migration_events','migration_events_scan_run_id_fkey','FOREIGN KEY','FOREIGN KEY \(scan_run_id\) REFERENCES scan_runs\(id\) ON DELETE SET NULL'),
    ('migration_events','migration_events_source_folder_id_fkey','FOREIGN KEY','FOREIGN KEY \(source_folder_id\) REFERENCES source_folders\(id\) ON DELETE SET NULL'),
    ('migration_events','migration_events_source_file_id_fkey','FOREIGN KEY','FOREIGN KEY \(source_file_id\) REFERENCES source_files\(id\) ON DELETE SET NULL'),
    ('migration_events','migration_events_asset_id_fkey','FOREIGN KEY','FOREIGN KEY \(asset_id\) REFERENCES assets\(id\) ON DELETE SET NULL'),
    ('source_files','source_files_folder_google_file_unique','UNIQUE','UNIQUE \(source_folder_id, google_file_id\)'),
    ('asset_sources','asset_sources_asset_source_unique','UNIQUE','UNIQUE \(asset_id, source_file_id\)'),
    ('asset_sources','asset_sources_source_file_unique','UNIQUE','UNIQUE \(source_file_id\)'),
    ('source_folders','source_folders_access_status_check','CHECK','access_status.*PENDING.*ACCESSIBLE.*INACCESSIBLE.*ERROR.*DISABLED'),
    ('source_folders','source_folders_permission_role_check','CHECK','permission_role.*UNKNOWN.*VIEWER.*COMMENTER.*EDITOR.*OWNER'),
    ('sync_runs','sync_runs_run_type_check','CHECK','run_type.*MANUAL.*INITIAL_MIGRATION.*DAILY_SYNC.*RETRY'),
    ('sync_runs','sync_runs_status_check','CHECK','status.*QUEUED.*RUNNING.*COMPLETED.*COMPLETED_WITH_ERRORS.*FAILED.*CANCELLED'),
    ('sync_runs','sync_runs_counts_check','CHECK','folders_total >= 0.*folders_succeeded >= 0.*folders_failed >= 0.*files_discovered >= 0.*files_taken >= 0.*files_skipped >= 0.*files_uploaded >= 0.*duplicates_found >= 0.*files_failed >= 0'),
    ('sync_runs','sync_runs_timestamps_check','CHECK','completed_at IS NULL.*started_at IS NULL.*completed_at >= started_at'),
    ('sync_runs','sync_runs_metadata_object_check','CHECK','jsonb_typeof\(metadata\).*object'),
    ('scan_runs','scan_runs_run_mode_check','CHECK','run_mode.*DRY_RUN.*MIGRATION'),
    ('scan_runs','scan_runs_status_check','CHECK','status.*QUEUED.*RUNNING.*COMPLETED.*COMPLETED_WITH_ERRORS.*FAILED.*CANCELLED'),
    ('scan_runs','scan_runs_counts_check','CHECK','files_discovered >= 0.*files_taken >= 0.*files_skipped >= 0.*files_uploaded >= 0.*duplicates_found >= 0.*files_failed >= 0'),
    ('scan_runs','scan_runs_timestamps_check','CHECK','completed_at IS NULL.*started_at IS NULL.*completed_at >= started_at'),
    ('scan_runs','scan_runs_metadata_object_check','CHECK','jsonb_typeof\(metadata\).*object'),
    ('source_files','source_files_size_bytes_check','CHECK','size_bytes IS NULL.*size_bytes >= 0'),
    ('source_files','source_files_md5_checksum_check','CHECK','md5_checksum IS NULL.*\^\[0-9A-Fa-f\]\{32\}\$'),
    ('source_files','source_files_decision_check','CHECK','decision.*PENDING.*TAKE.*SKIP'),
    ('source_files','source_files_processing_status_check','CHECK','processing_status.*DISCOVERED.*QUEUED.*HASHING.*READY.*DUPLICATE.*UPLOADING.*UPLOADED.*SKIPPED.*FAILED.*INACCESSIBLE'),
    ('source_files','source_files_seen_timestamps_check','CHECK','last_seen_at >= first_seen_at'),
    ('source_files','source_files_metadata_object_check','CHECK','jsonb_typeof\(metadata\).*object'),
    ('assets','assets_content_hash_check','CHECK','content_hash IS NULL.*\^\[0-9A-Fa-f\]\{64\}\$'),
    ('assets','assets_size_bytes_check','CHECK','size_bytes IS NULL.*size_bytes >= 0'),
    ('assets','assets_upload_status_check','CHECK','upload_status.*PENDING.*UPLOADING.*UPLOADED.*FAILED.*MISSING.*VERIFICATION_REQUIRED'),
    ('assets','assets_storage_location_check','CHECK','storage_bucket IS NULL.*storage_path IS NULL.*storage_bucket IS NOT NULL.*storage_path IS NOT NULL'),
    ('assets','assets_metadata_object_check','CHECK','jsonb_typeof\(metadata\).*object'),
    ('asset_sources','asset_sources_relationship_type_check','CHECK','relationship_type.*ORIGINAL.*DUPLICATE'),
    ('migration_events','migration_events_event_status_check','CHECK','event_status.*INFO.*SUCCESS.*WARNING.*ERROR'),
    ('migration_events','migration_events_details_object_check','CHECK','jsonb_typeof\(details\).*object')
),
expected_indexes(table_name, index_name, unique_index, definition_re) as (
  values
    ('source_folders','source_folders_google_folder_id_unique',true,'\(google_folder_id\)$'),
    ('source_folders','source_folders_active_access_status_idx',false,'\(active, access_status\)$'),
    ('source_folders','source_folders_account_name_idx',false,'\(account_name\)$'),
    ('source_folders','source_folders_last_scan_at_idx',false,'\(last_scan_at DESC\)$'),
    ('sync_runs','sync_runs_status_created_at_idx',false,'\(status, created_at DESC\)$'),
    ('sync_runs','sync_runs_run_type_created_at_idx',false,'\(run_type, created_at DESC\)$'),
    ('scan_runs','scan_runs_sync_run_id_idx',false,'\(sync_run_id\)$'),
    ('scan_runs','scan_runs_source_folder_created_at_idx',false,'\(source_folder_id, created_at DESC\)$'),
    ('scan_runs','scan_runs_status_created_at_idx',false,'\(status, created_at DESC\)$'),
    ('source_files','source_files_last_scan_run_id_idx',false,'\(last_scan_run_id\)$'),
    ('source_files','source_files_google_file_id_idx',false,'\(google_file_id\)$'),
    ('source_files','source_files_folder_decision_status_idx',false,'\(source_folder_id, decision, processing_status\)$'),
    ('source_files','source_files_exact_duplicate_idx',false,'\(md5_checksum, size_bytes\) WHERE .*md5_checksum IS NOT NULL.*size_bytes IS NOT NULL'),
    ('source_files','source_files_destination_file_id_idx',false,'\(destination_file_id\) WHERE .*destination_file_id IS NOT NULL'),
    ('assets','assets_content_hash_unique',true,'\(content_hash\) WHERE .*content_hash IS NOT NULL'),
    ('assets','assets_storage_location_unique',true,'\(storage_bucket, storage_path\) WHERE .*storage_bucket IS NOT NULL.*storage_path IS NOT NULL'),
    ('assets','assets_upload_status_created_at_idx',false,'\(upload_status, created_at DESC\)$'),
    ('asset_sources','asset_sources_asset_id_idx',false,'\(asset_id\)$'),
    ('asset_sources','asset_sources_relationship_type_idx',false,'\(relationship_type\)$'),
    ('migration_events','migration_events_sync_run_occurred_at_idx',false,'\(sync_run_id, occurred_at DESC\)$'),
    ('migration_events','migration_events_scan_run_occurred_at_idx',false,'\(scan_run_id, occurred_at DESC\)$'),
    ('migration_events','migration_events_source_folder_occurred_at_idx',false,'\(source_folder_id, occurred_at DESC\)$'),
    ('migration_events','migration_events_source_file_occurred_at_idx',false,'\(source_file_id, occurred_at DESC\)$'),
    ('migration_events','migration_events_asset_occurred_at_idx',false,'\(asset_id, occurred_at DESC\)$'),
    ('migration_events','migration_events_type_status_occurred_at_idx',false,'\(event_type, event_status, occurred_at DESC\)$')
),
expected_view_columns(ordinal_position, column_name, data_type) as (
  values
    (1,'id','uuid'), (2,'source_name','text'), (3,'account_name','text'),
    (4,'folder_url','text'), (5,'google_folder_id','text'), (6,'active','boolean'),
    (7,'access_status','text'), (8,'permission_role','text'),
    (9,'last_access_checked_at','timestamp with time zone'),
    (10,'last_scan_at','timestamp with time zone'),
    (11,'last_successful_scan_at','timestamp with time zone'), (12,'notes','text'),
    (13,'created_at','timestamp with time zone'), (14,'updated_at','timestamp with time zone'),
    (15,'total_files','bigint'), (16,'take_files','bigint'), (17,'skip_files','bigint'),
    (18,'uploaded_files','bigint'), (19,'duplicate_files','bigint'), (20,'failed_files','bigint'),
    (21,'asset_count','bigint'), (22,'latest_scan_run_id','uuid'),
    (23,'latest_scan_status','text'), (24,'latest_scan_started_at','timestamp with time zone'),
    (25,'latest_scan_completed_at','timestamp with time zone')
),
expected_folders(source_name, account_name, folder_url, google_folder_id, active, access_status, permission_role, notes) as (
  values
    ('Nushad Raw Video','kdimktgsubang@gmail.com','https://drive.google.com/drive/folders/1J7rUY-n4oVFqwY07jXOwwu_wFo8jeCsI?usp=drive_link','1J7rUY-n4oVFqwY07jXOwwu_wFo8jeCsI',true,'PENDING','UNKNOWN','Initial approved Google Drive source folder.'),
    ('ALL PATIENT REVIEW','kdisubang@gmail.com','https://drive.google.com/drive/folders/1kYX3KIEFkerRMrTvZk2zPpVaFQoCLE4v','1kYX3KIEFkerRMrTvZk2zPpVaFQoCLE4v',true,'PENDING','UNKNOWN','Initial approved Google Drive source folder.'),
    ('Photo/Video for Marketing (Consented by patient)','kdisubang@gmail.com','https://drive.google.com/drive/folders/1TkV6WEH5ymgqZmU7WgYFwYeZUxGYkEUt','1TkV6WEH5ymgqZmU7WgYFwYeZUxGYkEUt',true,'PENDING','UNKNOWN','Patient media source. Consent status must still be verified at asset level.')
),
live_constraints as (
  select c.conname, c.convalidated, n.nspname, r.relname,
         pg_get_constraintdef(c.oid, true) definition
  from pg_catalog.pg_constraint c
  join pg_catalog.pg_class r on r.oid = c.conrelid
  join pg_catalog.pg_namespace n on n.oid = r.relnamespace
  where n.nspname = 'public'
),
live_indexes as (
  select r.relname table_name, i.relname index_name, x.indisunique,
         pg_get_indexdef(i.oid) definition
  from pg_catalog.pg_index x
  join pg_catalog.pg_class i on i.oid = x.indexrelid
  join pg_catalog.pg_class r on r.oid = x.indrelid
  join pg_catalog.pg_namespace n on n.oid = r.relnamespace
  where n.nspname = 'public'
),
findings(category, object_name, expected, actual, status, recommendation) as (
  select 'table', 'public.' || e.table_name, 'BASE TABLE', coalesce(c.relkind::text, 'absent'),
         'MISSING', 'Apply the foundation schema migration.'
  from expected_tables e
  left join pg_catalog.pg_namespace n on n.nspname = 'public'
  left join pg_catalog.pg_class c on c.relnamespace = n.oid and c.relname = e.table_name and c.relkind in ('r','p')
  where c.oid is null

  union all
  select 'column', e.table_name || '.' || e.column_name,
         e.data_type || '; nullable=' || e.nullable || '; default=' || coalesce(e.default_re,'NULL'),
         coalesce(c.data_type || '; nullable=' || (c.is_nullable = 'YES') || '; default=' || coalesce(c.column_default,'NULL'),'absent'),
         case when c.column_name is null then 'MISSING' else 'MISMATCH' end,
         'Align the column type, nullability, and default with the foundation migration.'
  from expected_columns e
  left join information_schema.columns c on c.table_schema='public' and c.table_name=e.table_name and c.column_name=e.column_name
  where c.column_name is null
     or c.data_type <> e.data_type
     or (c.is_nullable = 'YES') <> e.nullable
     or (e.default_re is null and c.column_default is not null)
     or (e.default_re is not null and coalesce(c.column_default,'') !~ ('^' || e.default_re || '$'))

  union all
  select 'constraint', e.table_name || '.' || e.constraint_name,
         e.kind || ': ' || e.definition_re || '; validated=true',
         coalesce(l.definition || '; validated=' || l.convalidated,'absent'),
         case when l.conname is null then 'MISSING' else 'MISMATCH' end,
         'Create or correct and validate the required constraint.'
  from expected_constraints e
  left join live_constraints l on l.nspname='public' and l.relname=e.table_name and l.conname=e.constraint_name
  where l.conname is null or not l.convalidated or l.definition !~ e.definition_re

  union all
  select 'index', e.table_name || '.' || e.index_name,
         'unique=' || e.unique_index || '; ' || e.definition_re,
         coalesce('unique=' || l.indisunique || '; ' || l.definition,'absent'),
         case when l.index_name is null then 'MISSING' else 'MISMATCH' end,
         'Create or correct the required index.'
  from expected_indexes e
  left join live_indexes l on l.table_name=e.table_name and l.index_name=e.index_name
  where l.index_name is null or l.indisunique <> e.unique_index or l.definition !~ e.definition_re

  union all
  select 'function', 'public.set_updated_at()', 'trigger function; PL/pgSQL; NEW.updated_at = now()',
         coalesce(pg_get_functiondef(p.oid),'absent'),
         case when p.oid is null then 'MISSING' else 'MISMATCH' end,
         'Create or correct public.set_updated_at() from the foundation migration.'
  from (values (1)) seed(x)
  left join pg_catalog.pg_namespace n on n.nspname='public'
  left join pg_catalog.pg_proc p on p.pronamespace=n.oid and p.proname='set_updated_at' and p.pronargs=0
  where p.oid is null or p.prorettype <> 'trigger'::regtype
     or pg_get_functiondef(p.oid) !~* 'new\.updated_at\s*:=\s*now\(\)'

  union all
  select 'trigger', e.table_name || '.' || e.table_name || '_set_updated_at',
         'enabled BEFORE UPDATE FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()',
         coalesce(pg_get_triggerdef(t.oid,true) || '; enabled=' || t.tgenabled::text,'absent'),
         case when t.oid is null then 'MISSING' else 'MISMATCH' end,
         'Create or enable the required updated_at trigger.'
  from expected_tables e
  left join pg_catalog.pg_namespace n on n.nspname='public'
  left join pg_catalog.pg_class r on r.relnamespace=n.oid and r.relname=e.table_name
  left join pg_catalog.pg_trigger t on t.tgrelid=r.oid and t.tgname=e.table_name || '_set_updated_at' and not t.tgisinternal
  where t.oid is null or t.tgenabled = 'D'
     or pg_get_triggerdef(t.oid,true) !~* 'BEFORE UPDATE.*FOR EACH ROW EXECUTE FUNCTION set_updated_at\(\)'

  union all
  select 'rls', e.table_name, 'enabled', coalesce(r.relrowsecurity::text,'table absent'),
         case when r.oid is null then 'MISSING' else 'MISMATCH' end,
         'Enable Row Level Security on the table.'
  from expected_tables e
  left join pg_catalog.pg_namespace n on n.nspname='public'
  left join pg_catalog.pg_class r on r.relnamespace=n.oid and r.relname=e.table_name and r.relkind in ('r','p')
  where r.oid is null or not r.relrowsecurity

  union all
  select 'policy', e.table_name || '.' || e.table_name || '_authorized_read',
         'PERMISSIVE SELECT to authenticated; kdi_media_reader=true',
         coalesce(p.cmd || ' roles=' || p.roles::text || ' using=' || p.qual,'absent'),
         case when p.policyname is null then 'MISSING' else 'MISMATCH' end,
         'Create or correct the authenticated authorized-read policy.'
  from expected_tables e
  left join pg_catalog.pg_policies p on p.schemaname='public' and p.tablename=e.table_name
    and p.policyname=e.table_name || '_authorized_read'
  where p.policyname is null or p.cmd <> 'SELECT' or p.permissive <> 'PERMISSIVE'
     or not ('authenticated' = any(p.roles))
     or coalesce(p.qual,'') !~ 'kdi_media_reader'
     or coalesce(p.qual,'') !~ '''true'''

  union all
  select 'view', 'public.source_folder_summary', 'view exists with security_invoker=true',
         coalesce('relkind=' || r.relkind::text || '; options=' || coalesce(r.reloptions::text,'NULL'),'absent'),
         case when r.oid is null then 'MISSING' else 'MISMATCH' end,
         'Create or replace the security-invoker summary view.'
  from (values (1)) seed(x)
  left join pg_catalog.pg_namespace n on n.nspname='public'
  left join pg_catalog.pg_class r on r.relnamespace=n.oid and r.relname='source_folder_summary' and r.relkind='v'
  where r.oid is null or not (coalesce(r.reloptions,array[]::text[]) @> array['security_invoker=true'])

  union all
  select 'view definition', 'public.source_folder_summary',
         'foundation source-folder fields, file/asset totals, and latest scan',
         coalesce(pg_get_viewdef(r.oid,true),'absent'),
         case when r.oid is null then 'MISSING' else 'MISMATCH' end,
         'Recreate source_folder_summary from the foundation migration.'
  from (values (1)) seed(x)
  left join pg_catalog.pg_namespace n on n.nspname='public'
  left join pg_catalog.pg_class r on r.relnamespace=n.oid and r.relname='source_folder_summary' and r.relkind='v'
  where r.oid is null
     or regexp_replace(pg_get_viewdef(r.oid,true),'\s+',' ','g') !~* 'FROM source_folders sf'
     or regexp_replace(pg_get_viewdef(r.oid,true),'\s+',' ','g') !~* 'count\(\*\).*total_files'
     or regexp_replace(pg_get_viewdef(r.oid,true),'\s+',' ','g') !~* 'decision.*TAKE.*take_files'
     or regexp_replace(pg_get_viewdef(r.oid,true),'\s+',' ','g') !~* 'decision.*SKIP.*skip_files'
     or regexp_replace(pg_get_viewdef(r.oid,true),'\s+',' ','g') !~* 'processing_status.*UPLOADED.*uploaded_files'
     or regexp_replace(pg_get_viewdef(r.oid,true),'\s+',' ','g') !~* 'processing_status.*DUPLICATE.*duplicate_files'
     or regexp_replace(pg_get_viewdef(r.oid,true),'\s+',' ','g') !~* 'processing_status.*FAILED.*failed_files'
     or regexp_replace(pg_get_viewdef(r.oid,true),'\s+',' ','g') !~* 'count\(DISTINCT.*asset_id.*asset_count'
     or regexp_replace(pg_get_viewdef(r.oid,true),'\s+',' ','g') !~* 'ORDER BY scan.created_at DESC, scan.id DESC'

  union all
  select 'view column', 'source_folder_summary.' || e.column_name,
         'position=' || e.ordinal_position || '; type=' || e.data_type,
         coalesce('position=' || c.ordinal_position || '; type=' || c.data_type,'absent'),
         case when c.column_name is null then 'MISSING' else 'MISMATCH' end,
         'Recreate source_folder_summary with the intended column contract.'
  from expected_view_columns e
  left join information_schema.columns c on c.table_schema='public' and c.table_name='source_folder_summary'
    and c.column_name=e.column_name
  where c.column_name is null or c.ordinal_position <> e.ordinal_position or c.data_type <> e.data_type

  union all
  select 'seed record', e.google_folder_id,
         concat_ws(' | ',e.source_name,e.account_name,
                   regexp_replace(e.folder_url,'\?usp=drive_link$',''),



                   e.google_folder_id,e.active,e.access_status,e.permission_role,
                   'notes: non-null and non-empty'),
         coalesce(concat_ws(' | ',s.source_name,s.account_name,s.folder_url,s.google_folder_id,s.active,s.access_status,s.permission_role,s.notes),'absent'),
         case when s.id is null then 'MISSING' else 'MISMATCH' end,
         'Insert or align this approved source-folder record using the seed migration.'
  from expected_folders e
  left join public.source_folders s on s.google_folder_id=e.google_folder_id
  where s.id is null
     or (s.source_name,s.account_name,s.google_folder_id,s.active,s.access_status,s.permission_role)
        is distinct from
        (e.source_name,e.account_name,e.google_folder_id,e.active,e.access_status,e.permission_role)
     or regexp_replace(s.folder_url,'\?usp=drive_link$','')
        is distinct from regexp_replace(e.folder_url,'\?usp=drive_link$','')
     or nullif(btrim(s.notes),'') is null

  union all
  select 'data integrity', 'source_folders.google_folder_id=' || s.google_folder_id,
         'exactly 1 row', count(*)::text, 'MISMATCH',
         'Resolve duplicate source-folder rows; retain one approved record per Google folder ID.'
  from public.source_folders s
  where s.google_folder_id is not null
  group by s.google_folder_id
  having count(*) > 1

  union all
  select 'asset_sources relationship contract', 'asset_sources.relationship_type',
         'default ORIGINAL; allowed ORIGINAL,DUPLICATE',
         coalesce('default=' || c.column_default || '; check=' || l.definition,'absent'),
         case when c.column_name is null or l.conname is null then 'MISSING' else 'MISMATCH' end,
         'Restore the relationship_type default and allowed-values check.'
  from (values (1)) seed(x)
  left join information_schema.columns c on c.table_schema='public' and c.table_name='asset_sources' and c.column_name='relationship_type'
  left join live_constraints l on l.relname='asset_sources' and l.conname='asset_sources_relationship_type_check'
  where c.column_name is null or c.column_default !~ '^''ORIGINAL''::text$'
     or l.conname is null or not l.convalidated
     or l.definition !~ 'relationship_type.*ORIGINAL.*DUPLICATE'
),
reported as (
  select * from findings
  union all
  select 'OVERALL', 'foundation_database',
         'all required foundation objects and records match',
         case when exists (select 1 from findings)
              then count(*)::text || ' issue(s)' else 'complete' end,
         case when exists (select 1 from findings) then 'MISMATCH' else 'PASS' end,
         case when exists (select 1 from findings)
              then 'Resolve every MISSING/MISMATCH row, then run this check again.'
              else 'No action required.' end
  from findings
)
select category, object_name, expected, actual, status, recommendation
from reported
order by case when category='OVERALL' then 1 else 0 end,
         category, object_name;
