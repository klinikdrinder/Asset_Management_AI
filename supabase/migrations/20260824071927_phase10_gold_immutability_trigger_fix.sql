begin;
create or replace function public.prevent_signed_gold_child_mutation() returns trigger
language plpgsql security invoker set search_path='' as $$
declare v_set_id uuid; v_status text; v_old jsonb:=to_jsonb(old);
begin
 if tg_table_name='gold_standard_assets' then
   v_set_id:=(v_old->>'gold_set_id')::uuid;
 else
   select ga.gold_set_id into v_set_id from public.gold_standard_assets ga where ga.id=(v_old->>'gold_asset_id')::uuid;
 end if;
 select status into v_status from public.gold_standard_sets where id=v_set_id;
 if v_status='SIGNED_OFF' then raise exception 'signed-off gold children are immutable; create a new gold revision'; end if;
 return old;
end $$;
commit;
