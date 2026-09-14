-- KDI AI Search V3 Job 5: one authoritative permission decision layer.
-- Privileged readers live outside the exposed schema; public wrappers are
-- SECURITY INVOKER and reveal only a boolean for the current caller.

create function private.can_user_view_asset_for(p_user_id uuid,p_asset_id uuid)
returns boolean language sql stable security definer set search_path='' as $$
 select exists(
  select 1 from public.app_users u
  join public.assets a on a.id=p_asset_id
  join public.asset_access_control ac on ac.asset_id=a.id
  where u.user_id=p_user_id and u.is_active
    and a.upload_status not in ('FAILED','MISSING')
    and ac.internal_usage_status <> 'NOT_ALLOWED'
    and ac.sensitivity_level is not null
    and (
      (ac.sensitivity_level in ('GENERAL','INTERNAL') and ac.is_clinical is not true)
      or u.can_view_clinical
    )
 );
$$;

create function private.can_user_view_asset(p_asset_id uuid)
returns boolean language sql stable security definer set search_path='' as $$
 select private.can_user_view_asset_for(private.current_app_user_id(),p_asset_id);
$$;

create function private.authorized_asset_ids()
returns table(asset_id uuid) language sql stable security definer set search_path='' as $$
 select ac.asset_id
 from public.app_users u
 join public.asset_access_control ac on true
 join public.assets a on a.id=ac.asset_id
 where u.user_id=private.current_app_user_id() and u.is_active
   and a.upload_status not in ('FAILED','MISSING')
   and ac.internal_usage_status <> 'NOT_ALLOWED'
   and ac.sensitivity_level is not null
   and ((ac.sensitivity_level in ('GENERAL','INTERNAL') and ac.is_clinical is not true) or u.can_view_clinical);
$$;

create function private.can_user_download_asset_for(p_user_id uuid,p_asset_id uuid)
returns boolean language sql stable security definer set search_path='' as $$
 select private.can_user_view_asset_for(p_user_id,p_asset_id)
   and exists(select 1 from public.app_users u where u.user_id=p_user_id and u.is_active and u.can_download)
   and exists(select 1 from public.asset_access_control ac where ac.asset_id=p_asset_id and ac.download_allowed is true);
$$;

create function private.can_user_download_asset(p_asset_id uuid)
returns boolean language sql stable security definer set search_path='' as $$
 select private.can_user_download_asset_for(private.current_app_user_id(),p_asset_id);
$$;

create function private.can_asset_use_external_ai(p_asset_id uuid)
returns boolean language sql stable security definer set search_path='' as $$
 select exists(
  select 1 from public.assets a join public.asset_access_control ac on ac.asset_id=a.id
  where a.id=p_asset_id and a.upload_status not in ('FAILED','MISSING') and ac.external_ai_status='ALLOWED'
 );
$$;

create function private.is_search_session_owner(p_session_id uuid)
returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.search_sessions s where s.id=p_session_id and s.user_id=private.current_app_user_id());
$$;

revoke all on function private.can_user_view_asset_for(uuid,uuid),private.can_user_view_asset(uuid),private.authorized_asset_ids(),private.can_user_download_asset_for(uuid,uuid),private.can_user_download_asset(uuid),private.can_asset_use_external_ai(uuid),private.is_search_session_owner(uuid) from public,anon,authenticated,service_role;
grant execute on function private.can_user_view_asset(uuid),private.authorized_asset_ids(),private.can_user_download_asset(uuid),private.is_search_session_owner(uuid) to authenticated;
grant execute on function private.can_user_view_asset_for(uuid,uuid),private.can_user_view_asset(uuid),private.authorized_asset_ids(),private.can_user_download_asset_for(uuid,uuid),private.can_user_download_asset(uuid),private.can_asset_use_external_ai(uuid),private.is_search_session_owner(uuid) to service_role;

create function public.can_user_view_asset(p_asset_id uuid) returns boolean
language sql stable security invoker set search_path='' as $$ select private.can_user_view_asset(p_asset_id); $$;
create function public.can_user_download_asset(p_asset_id uuid) returns boolean
language sql stable security invoker set search_path='' as $$ select private.can_user_download_asset(p_asset_id); $$;
create function public.can_user_download_asset_for(p_user_id uuid,p_asset_id uuid) returns boolean
language sql stable security invoker set search_path='' as $$ select private.can_user_download_asset_for(p_user_id,p_asset_id); $$;
create function public.can_asset_use_external_ai(p_asset_id uuid) returns boolean
language sql stable security invoker set search_path='' as $$ select private.can_asset_use_external_ai(p_asset_id); $$;

revoke all on function public.can_user_view_asset(uuid),public.can_user_download_asset(uuid),public.can_user_download_asset_for(uuid,uuid),public.can_asset_use_external_ai(uuid) from public,anon,authenticated,service_role;
grant execute on function public.can_user_view_asset(uuid),public.can_user_download_asset(uuid) to authenticated;
grant execute on function public.can_user_view_asset(uuid),public.can_user_download_asset(uuid),public.can_user_download_asset_for(uuid,uuid),public.can_asset_use_external_ai(uuid) to service_role;
