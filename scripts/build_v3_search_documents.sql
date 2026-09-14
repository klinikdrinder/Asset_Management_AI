-- Build v3 ASSET search documents for the 104 completed assets of run
-- 5b2060ee-ef8d-4553-9db5-426b7785fdad, from asset_search_concepts_v2.
--
-- Design decisions (agreed):
--  * Target the live table search_document_builds under a NEW version so existing docs stay intact.
--  * positive_concepts: structured objects with per-hit lineage = confidence only. The v3 source
--    (contract v2) never persists assertion_id/evidence_ids, so those are null/[] here, honestly.
--  * negative_concepts: []  -- the v2 contract only persists OBSERVED concepts; no FALSE-state source.
--  * primary_treatment_id/anatomy_id/location_id: resolved from the highest-confidence TREATMENT /
--    ANATOMY / ENVIRONMENT concept -> ontology id. search_document_builds has no such columns, so
--    they are carried in normalized_document (queryable via jsonb).
--  * STAGED: active=false so the ready-view (which requires exactly one active ASSET doc per asset)
--    is untouched and live search is unaffected until an explicit go-live.
-- Idempotent: removes any prior v3 rows for this version first.

delete from public.search_document_builds where search_document_version = 'kdi_search_document_v3';

with run as (select '5b2060ee-ef8d-4553-9db5-426b7785fdad'::uuid as id),
c as (  -- dedupe to one row per (asset, concept_type, canonical_code), keeping the strongest confidence
  select distinct on (sc.asset_id, sc.concept_type, sc.canonical_code)
    sc.asset_id, sc.concept_type, sc.canonical_code, sc.display_text, sc.confidence,
    sc.review_state, sc.search_critical
  from public.asset_search_concepts_v2 sc, run
  where sc.analysis_run_id = run.id
  order by sc.asset_id, sc.concept_type, sc.canonical_code, sc.confidence desc nulls last
),
prim_t as (select distinct on (c.asset_id) c.asset_id, t.id tid
           from c join public.treatments t on upper(t.code)=upper(c.canonical_code)
           where c.concept_type='TREATMENT' order by c.asset_id, c.confidence desc nulls last),
prim_a as (select distinct on (c.asset_id) c.asset_id, an.id aid
           from c join public.anatomy_terms an on upper(an.code)=upper(c.canonical_code)
           where c.concept_type='ANATOMY' order by c.asset_id, c.confidence desc nulls last),
prim_l as (select distinct on (c.asset_id) c.asset_id, l.id lid
           from c join public.locations l on upper(l.code)=upper(c.canonical_code)
           where c.concept_type='ENVIRONMENT' order by c.asset_id, c.confidence desc nulls last),
agg as (
  select c.asset_id,
    jsonb_agg(jsonb_build_object(
      'concept_type', c.concept_type, 'canonical_code', c.canonical_code, 'display_text', c.display_text,
      'semantic_state', 'OBSERVED', 'confidence', c.confidence, 'search_critical', c.search_critical,
      'review_state', c.review_state, 'assertion_id', null, 'evidence_ids', '[]'::jsonb,
      'resolution_source', 'UNVERIFIED_AI', 'origin', 'AI_MODEL'
    ) order by c.confidence desc nulls last, c.canonical_code) as positive_concepts,
    string_agg(distinct c.display_text, '. ' order by c.display_text) as concept_text,
    count(*) as n_concepts,
    md5(string_agg(c.concept_type||':'||c.canonical_code, '|' order by c.concept_type, c.canonical_code)) as concept_blob
  from c group by c.asset_id
)
insert into public.search_document_builds
 (asset_id, search_document_version, source_semantic_version, source_fingerprint, document_fingerprint,
  status, document_type, filename, media_type, normalized_document, search_text,
  positive_concepts, negative_concepts, builder_version, configuration_version, semantic_spec_version,
  ontology_version, source_semantic_fingerprint, review_status, active, stale, generated_at)
select
  agg.asset_id, 'kdi_search_document_v3', 'kdi-extraction-contract-v2',
  agg.concept_blob, agg.concept_blob, 'READY', 'ASSET', a.file_name,
  case when a.mime_type like 'video/%' then 'VIDEO' else 'IMAGE' end,
  jsonb_build_object(
    'filename', a.file_name, 'analysis_run_id', (select id::text from run),
    'primary_treatment_id', pt.tid, 'primary_anatomy_id', pa.aid, 'primary_location_id', pl.lid,
    'concept_count', agg.n_concepts, 'lineage', 'confidence_only', 'negatives', 'none_in_v3_source'),
  a.file_name || '. ' || agg.concept_text,
  agg.positive_concepts, '[]'::jsonb, 'kdi_v3_concept_builder_v1', 'kdi_v3_concept_builder_v1',
  'kdi-extraction-contract-v2', 'KDI_SEMANTIC_V2', (select id::text from run), 'AI_UNREVIEWED',
  false, false, now()
from agg
join public.assets a on a.id = agg.asset_id
left join prim_t pt on pt.asset_id = agg.asset_id
left join prim_a pa on pa.asset_id = agg.asset_id
left join prim_l pl on pl.asset_id = agg.asset_id;
-- search_vector is a generated column (derived from search_text) and populates automatically.
