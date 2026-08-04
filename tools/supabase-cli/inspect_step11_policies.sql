select jsonb_build_object(
  'broad_policies',(select jsonb_agg(jsonb_build_object('table',tablename,'name',policyname,'using',qual) order by tablename) from pg_policies where schemaname='public' and policyname like 'Authenticated users can read%'),
  'legacy_policies',(select jsonb_agg(jsonb_build_object('table',tablename,'name',policyname,'using',qual) order by tablename) from pg_policies where schemaname='public' and coalesce(qual,'') ~ 'kdi_media'),
  'event_constraints',(select jsonb_agg(jsonb_build_object('name',con.conname,'definition',pg_get_constraintdef(con.oid)) order by con.conname) from pg_constraint con where con.conrelid='public.migration_events'::regclass and con.contype='c'),
  'step9_columns',(select jsonb_agg(column_name order by ordinal_position) from information_schema.columns where table_schema='public' and table_name='source_files' and column_name in ('content_sha256','hash_status','hash_attempt_count','hash_claim_owner','hash_claim_started_at','hash_claim_expires_at','hash_last_attempt_at','hash_completed_at','hash_error','hash_source_snapshot')),
  'step10_function_args',(select jsonb_agg(jsonb_build_object('name',proname,'args',pg_get_function_identity_arguments(oid)) order by proname) from pg_proc where pronamespace='public'::regnamespace and proname in ('claim_asset_destinations','renew_asset_destination_claim','release_asset_destination_claim','set_step10_migration_event_legacy_status')),
  'repair_gate',(select pg_get_viewdef('public.source_folder_summary'::regclass,true) ~ 'private\.is_active_app_user\(\)')
) as evidence;
