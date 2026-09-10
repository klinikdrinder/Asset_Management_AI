begin;

create or replace function private.is_asset_source_available(p_asset_id uuid)
returns boolean language sql stable security definer set search_path='' as $function$
  select exists(
    select 1 from public.asset_sources s
    join public.source_files sf on sf.id=s.source_file_id
    join public.source_folders f on f.id=sf.source_folder_id
    where s.asset_id=p_asset_id and f.active
      and not coalesce(sf.is_missing,true)
      and not coalesce(sf.trashed,true)
      and sf.sync_classification is distinct from 'REMOVED_FROM_SOURCE'
  );
$function$;

create or replace function private.can_user_view_asset_for(p_user_id uuid,p_asset_id uuid)
returns boolean language sql stable security definer set search_path='' as $function$
  select exists(
    select 1 from public.app_users u
    join public.assets a on a.id=p_asset_id
    join public.asset_access_control ac on ac.asset_id=a.id
    where u.user_id=p_user_id and u.is_active
      and a.upload_status not in ('FAILED','MISSING')
      and private.is_asset_source_available(a.id)
      and ac.internal_usage_status='ALLOWED'
      and ac.sensitivity_level is not null
      and ac.is_clinical is not null
      and (
        (ac.is_clinical=false
          and coalesce(ac.requires_clinical_permission,false)=false
          and ac.sensitivity_level in ('GENERAL','INTERNAL'))
        or
        (u.can_view_clinical=true and (
          ac.is_clinical=true
          or ac.requires_clinical_permission=true
          or ac.sensitivity_level in ('RESTRICTED','CLINICAL','HIGHLY_RESTRICTED')
        ))
      )
  );
$function$;

create or replace function private.authorized_asset_ids()
returns table(asset_id uuid) language sql stable security definer set search_path='' as $function$
  select a.id from public.assets a
  where private.can_user_view_asset_for(private.current_app_user_id(),a.id);
$function$;

create or replace function private.can_user_download_asset_for(p_user_id uuid,p_asset_id uuid)
returns boolean language sql stable security definer set search_path='' as $function$
  select private.can_user_view_asset_for(p_user_id,p_asset_id)
    and exists(select 1 from public.app_users u where u.user_id=p_user_id and u.is_active and u.can_download=true)
    and exists(select 1 from public.asset_access_control ac where ac.asset_id=p_asset_id and ac.download_allowed=true);
$function$;

create or replace function private.phase18_authorize_candidates_for(p_user_id uuid,p_asset_ids uuid[])
returns table(
  ordinal bigint,asset_id uuid,discover boolean,view_metadata boolean,preview boolean,download boolean,
  marketing_approved boolean,consent_confirmed boolean,external_ai_eligible boolean,denial_code text
)
language sql stable security definer set search_path='' as $function$
  with requested as (
    select x.asset_id,x.ordinality ordinal from unnest(coalesce(p_asset_ids,'{}'::uuid[])) with ordinality x(asset_id,ordinality)
  ), decision as (
    select r.*,a.id is not null asset_exists,
      coalesce(a.upload_status not in ('FAILED','MISSING'),false) asset_available,
      private.is_asset_source_available(r.asset_id) source_available,
      u.user_id is not null and u.is_active user_available,
      ac.asset_id is not null auth_exists,
      private.can_user_view_asset_for(p_user_id,r.asset_id) can_view,
      private.can_user_download_asset_for(p_user_id,r.asset_id) can_download,
      ac.internal_usage_status,ac.is_clinical,ac.requires_clinical_permission,ac.sensitivity_level,
      ac.marketing_usage_status,ac.consent_status,ac.external_ai_status
    from requested r left join public.assets a on a.id=r.asset_id
    left join public.asset_access_control ac on ac.asset_id=r.asset_id
    left join public.app_users u on u.user_id=p_user_id
  )
  select ordinal,asset_id,can_view,can_view,can_view,can_download,
    marketing_usage_status='APPROVED',consent_status='CONFIRMED',external_ai_status='ALLOWED',
    case when can_view then 'ALLOWED'
      when not user_available then 'INVALID_USER'
      when not asset_exists then 'ASSET_NOT_FOUND'
      when not asset_available then 'ASSET_UNAVAILABLE'
      when not source_available then 'SOURCE_UNAVAILABLE'
      when not auth_exists then 'MISSING_AUTHORIZATION'
      when internal_usage_status is distinct from 'ALLOWED' then 'INTERNAL_NOT_ALLOWED'
      when is_clinical is null then 'AMBIGUOUS_CLINICAL_STATE'
      when is_clinical or coalesce(requires_clinical_permission,false) or sensitivity_level in ('RESTRICTED','CLINICAL','HIGHLY_RESTRICTED') then 'CLINICAL_PERMISSION_REQUIRED'
      else 'DENIED' end
  from decision order by ordinal;
$function$;

create or replace function public.phase18_authorize_candidates_for(p_user_id uuid,p_asset_ids uuid[])
returns table(
  ordinal bigint,asset_id uuid,discover boolean,view_metadata boolean,preview boolean,download boolean,
  marketing_approved boolean,consent_confirmed boolean,external_ai_eligible boolean,denial_code text
)
language sql stable security invoker set search_path='' as $function$
  select * from private.phase18_authorize_candidates_for(p_user_id,p_asset_ids);
$function$;

revoke all on function private.is_asset_source_available(uuid),private.phase18_authorize_candidates_for(uuid,uuid[]) from public,anon,authenticated,service_role;
grant execute on function private.is_asset_source_available(uuid),private.phase18_authorize_candidates_for(uuid,uuid[]) to service_role;
revoke all on function public.phase18_authorize_candidates_for(uuid,uuid[]) from public,anon,authenticated,service_role;
grant execute on function public.phase18_authorize_candidates_for(uuid,uuid[]) to service_role;

comment on function public.phase18_authorize_candidates_for(uuid,uuid[]) is
'Backend-only Phase 18 batch authorization. Denial diagnostics must never be exposed to ordinary clients.';

commit;
