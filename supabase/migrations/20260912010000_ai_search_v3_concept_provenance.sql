-- AI Search v3 (job 1) — concept provenance + ontology read access.
-- NOT YET APPLIED. Prepared for the Part C test run; apply immediately before it.
--
-- 1. Preserve, per row and queryable, what the model actually emitted alongside
--    the resolved code — including when a concept degraded to UNDETERMINED or
--    failed resolution. asset_search_concepts_v2 has no jsonb column, so these
--    are first-class columns (same pattern as the phase-11.1 backfill ALTERs).
-- 2. Grant the service role SELECT on the ontology tables so the resolver and
--    the coverage report can run through the service-role client (today it is
--    blocked on clinical_observation_definitions with error 42501).

begin;

alter table public.asset_search_concepts_v2
  add column if not exists raw_concept text,
  add column if not exists model_confidence numeric,
  add column if not exists resolution_method text;

comment on column public.asset_search_concepts_v2.raw_concept is
  'Exact code/text the model emitted before ontology resolution; kept even when canonical_code degraded to UNDETERMINED or was unresolved.';
comment on column public.asset_search_concepts_v2.model_confidence is
  'Per-concept confidence the model reported (0-1).';
comment on column public.asset_search_concepts_v2.resolution_method is
  'exact | alias | normalized | undetermined | degraded_named_procedure | unresolved | no_ontology_domain';

create index if not exists search_concepts_v2_resolution_idx
  on public.asset_search_concepts_v2(resolution_method);

grant select on
  public.treatments, public.anatomy_terms, public.actions,
  public.clinical_observation_definitions, public.treatment_aliases,
  public.locations
  to service_role;

commit;
