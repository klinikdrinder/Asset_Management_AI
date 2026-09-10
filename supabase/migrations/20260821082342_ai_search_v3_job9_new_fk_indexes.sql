create index if not exists asset_context_location_idx on public.asset_context(location_id);
create index if not exists asset_layer_status_analysis_run_idx on public.asset_layer_status(analysis_run_id);
create index if not exists asset_layer_status_layer_code_idx on public.asset_layer_status(layer_code);
create index if not exists asset_technical_metadata_analysis_run_idx on public.asset_technical_metadata(analysis_run_id);
create index if not exists person_identity_embeddings_reference_asset_idx on public.person_identity_embeddings(reference_asset_id);
create index if not exists person_reference_assets_asset_idx on public.person_reference_assets(asset_id);;
