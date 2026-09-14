begin;

-- Promote the already validated dimension-safe matcher to the unversioned canonical name. This is
-- an architecture-only change: it neither writes semantic truth nor indexes any asset.
alter function public.match_kdi_search_v4_embeddings(
  public.vector,text,text,text,text,integer,integer,real
) rename to match_kdi_semantic_search_embeddings;

comment on function public.match_kdi_semantic_search_embeddings(
  public.vector,text,text,text,text,integer,integer,real
) is 'Internal vector channel for KDI_CANONICAL_SEMANTIC_SEARCH. Enforces representation, provider, model, version and dimension before independently scoring an embedding family.';

-- Low-level retrieval is an implementation detail of the server-side canonical orchestrator.
-- Browser roles cannot invoke it directly and therefore cannot turn it into a competing product.
revoke all on function public.match_kdi_semantic_search_embeddings(
  public.vector,text,text,text,text,integer,integer,real
) from public,anon,authenticated;
grant execute on function public.match_kdi_semantic_search_embeddings(
  public.vector,text,text,text,text,integer,integer,real
) to service_role;

revoke select on public.kdi_search_ready_assets_v1 from anon,authenticated;
grant select on public.kdi_search_ready_assets_v1 to service_role;

-- Historical search RPCs stay available only to trusted regression/developer tooling. Ordinary
-- authenticated clients can no longer call a numbered search authority through PostgREST.
do $block$
declare
  fn record;
begin
  for fn in
    select p.oid::regprocedure as signature
    from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public'
      and p.proname in (
        'hybrid_search_assets',
        'hybrid_search_assets_v2',
        'hybrid_search_assets_v3',
        'match_phase17_semantic_embeddings'
      )
  loop
    execute format('revoke all on function %s from public, anon, authenticated',fn.signature);
    execute format('grant execute on function %s to service_role',fn.signature);
  end loop;
end
$block$;

comment on view public.kdi_search_ready_assets_v1 is 'Internal SEARCH_READY authority for KDI_CANONICAL_SEMANTIC_SEARCH; not exposed to browser roles.';

commit;
