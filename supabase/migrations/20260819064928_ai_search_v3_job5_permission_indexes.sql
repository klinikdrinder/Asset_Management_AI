-- KDI AI Search V3 Job 5: only indexes used by set-based permission paths.
create index asset_access_control_view_eligibility_idx
 on public.asset_access_control(sensitivity_level,internal_usage_status,is_clinical,asset_id);
create index asset_access_control_download_allowed_idx
 on public.asset_access_control(asset_id) where download_allowed is true;
create index asset_access_control_external_ai_allowed_idx
 on public.asset_access_control(asset_id) where external_ai_status='ALLOWED';

;
