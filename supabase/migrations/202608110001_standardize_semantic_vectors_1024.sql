-- Standardize the empty semantic-search deployment on the approved local
-- qwen3-embedding:0.6b 1024-dimensional vector space. The original
-- 202608070001 migration is deployed history and is intentionally unchanged.

begin;

-- Prevent an indexer from racing the zero-row checks. This migration must
-- fail closed rather than delete, transform, truncate, or overwrite data.
lock table public.asset_semantic_index in access exclusive mode;
lock table public.asset_embeddings in access exclusive mode;

do $$
declare
  semantic_count bigint;
  embedding_count bigint;
begin
  select count(*) into semantic_count from public.asset_semantic_index;
  select count(*) into embedding_count from public.asset_embeddings;

  if semantic_count <> 0 or embedding_count <> 0 then
    raise exception using
      errcode = '55000',
      message = format(
        'KDI semantic vector transition requires empty tables (asset_semantic_index=%s, asset_embeddings=%s)',
        semantic_count,
        embedding_count
      );
  end if;
end;
$$;

-- The SQL function depends on asset_embeddings.embedding. Remove only that
-- dependent object, then restore it below in the same transaction with the
-- identical authorization, filters, ranking, diagnostics, grants, and locked
-- search_path.
drop function public.hybrid_search_assets(
  text, public.vector, text, text, text, text, text, integer, integer
);

alter table public.asset_embeddings
  drop constraint asset_embeddings_dimensions_check;

alter table public.asset_embeddings
  alter column embedding type public.vector(1024)
  using embedding::public.vector(1024);

alter table public.asset_embeddings
  add constraint asset_embeddings_dimensions_check
  check (embedding_dimensions = 1024);

comment on column public.asset_embeddings.embedding is
  'Fixed at 1024 dimensions for the approved local qwen3-embedding:0.6b model. Never truncated or padded; provider adapters must reject incompatible responses.';

-- Ranking remains unchanged:
--   45% semantic vector similarity
--   20% PostgreSQL full-text relevance
--    8% treatment field match
--    7% subject field match
--   10% doctor_name field match
--   10% filename match
create function public.hybrid_search_assets(
  search_query text,
  query_embedding public.vector(1024) default null,
  query_embedding_provider text default null,
  query_embedding_model text default null,
  query_embedding_version text default null,
  filter_category text default null,
  filter_extension text default null,
  result_limit integer default 25,
  result_offset integer default 0
)
returns table (
  asset_id uuid,
  match_score numeric,
  content_type text,
  treatment text,
  subject text,
  doctor_name text,
  short_caption text,
  ai_description text,
  semantic_score numeric,
  text_score numeric,
  structured_score numeric,
  filename_score numeric,
  total_count bigint
)
language sql
security definer
set search_path = ''
stable
as $$
  with authorization_check as (
    select private.is_active_app_user() as is_authorized
  ),
  bounded as (
    select
      nullif(btrim(search_query), '') as q,
      greatest(1, least(coalesce(result_limit, 25), 100)) as bounded_limit,
      greatest(0, coalesce(result_offset, 0)) as bounded_offset
  ),
  weights as (
    select
      0.45::numeric as semantic_weight,
      0.20::numeric as fulltext_weight,
      0.08::numeric as treatment_weight,
      0.07::numeric as subject_weight,
      0.10::numeric as doctor_weight,
      0.10::numeric as filename_weight
  ),
  scored as (
    select
      a.id as scored_asset_id,
      si.content_type as scored_content_type,
      si.treatment as scored_treatment,
      si.subject as scored_subject,
      si.doctor_name as scored_doctor_name,
      si.short_caption as scored_short_caption,
      si.ai_description as scored_ai_description,
      coalesce(
        1 - (ae.embedding OPERATOR(public.<=>) query_embedding),
        0
      ) as component_semantic,
      coalesce(ts_rank(si.search_vector, plainto_tsquery('english', b.q)), 0) as component_text,
      (
        case when b.q is not null and si.treatment OPERATOR(public.%) b.q then w.treatment_weight else 0 end
        + case when b.q is not null and si.subject OPERATOR(public.%) b.q then w.subject_weight else 0 end
        + case when b.q is not null and si.doctor_name OPERATOR(public.%) b.q then w.doctor_weight else 0 end
      ) as component_structured,
      case when b.q is not null and a.file_name ilike ('%' || b.q || '%')
        then w.filename_weight else 0 end as component_filename,
      (
        coalesce(
          w.semantic_weight
            * (1 - (ae.embedding OPERATOR(public.<=>) query_embedding)),
          0
        )
        + coalesce(
          w.fulltext_weight
            * ts_rank(si.search_vector, plainto_tsquery('english', b.q)),
          0
        )
        + case
            when b.q is not null and si.treatment OPERATOR(public.%) b.q
            then w.treatment_weight else 0
          end
        + case
            when b.q is not null and si.subject OPERATOR(public.%) b.q
            then w.subject_weight else 0
          end
        + case
            when b.q is not null and si.doctor_name OPERATOR(public.%) b.q
            then w.doctor_weight else 0
          end
        + case
            when b.q is not null and a.file_name ilike ('%' || b.q || '%')
            then w.filename_weight else 0
          end
      ) as raw_score
    from public.assets a
    join public.asset_semantic_index si on si.asset_id = a.id
    left join public.asset_embeddings ae
      on ae.asset_id = a.id
      and (query_embedding_provider is null or ae.embedding_provider = query_embedding_provider)
      and (query_embedding_model is null or ae.embedding_model = query_embedding_model)
      and (query_embedding_version is null or ae.embedding_version = query_embedding_version)
    cross join bounded b
    cross join weights w
    cross join authorization_check auth
    where auth.is_authorized
      and si.indexing_status = 'INDEXED'
      and exists (
        select 1 from public.asset_destinations ad
        where ad.asset_id = a.id
          and ad.upload_status = 'VERIFIED'
          and ad.destination_google_file_id is not null
      )
      and (b.q is not null or query_embedding is not null)
      and exists (
        select 1
        from public.asset_sources link
        join public.source_files sf on sf.id = link.source_file_id
        join public.source_folders sfo on sfo.id = sf.source_folder_id
        where link.asset_id = a.id
          and coalesce(sf.is_missing, false) = false
          and sf.sync_classification is distinct from 'REMOVED_FROM_SOURCE'
          and sfo.active = true
      )
      and (
        filter_extension is null
        or a.file_extension ilike filter_extension
      )
      and (
        filter_category is null
        or (
          filter_category = 'image'
          and (
            lower(coalesce(a.mime_type, '')) like 'image/%'
            or lower(coalesce(a.file_extension, ''))
              in ('jpg', 'jpeg', 'png', 'webp')
          )
        )
        or (
          filter_category = 'video'
          and (
            lower(coalesce(a.mime_type, '')) like 'video/%'
            or lower(coalesce(a.file_extension, '')) in ('mp4', 'mov')
          )
        )
        or (
          filter_category = 'document'
          and (
            a.mime_type in (
              'application/pdf',
              'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            )
            or lower(coalesce(a.mime_type, '')) like '%presentation%'
            or lower(coalesce(a.file_extension, '')) in ('pdf', 'pptx')
          )
        )
        or (
          filter_category = 'other'
          and not (
            lower(coalesce(a.mime_type, '')) like 'image/%'
            or lower(coalesce(a.mime_type, '')) like 'video/%'
            or lower(coalesce(a.mime_type, '')) like '%presentation%'
            or a.mime_type in (
              'application/pdf',
              'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            )
            or lower(coalesce(a.file_extension, ''))
              in ('jpg', 'jpeg', 'png', 'webp', 'mp4', 'mov', 'pdf', 'pptx')
          )
        )
      )
  )
  select
    scored.scored_asset_id,
    round(
      (
        least(scored.raw_score, 1::double precision)
        * 100::double precision
      )::numeric,
      2
    ) as match_score,
    scored.scored_content_type,
    scored.scored_treatment,
    scored.scored_subject,
    scored.scored_doctor_name,
    scored.scored_short_caption,
    scored.scored_ai_description,
    round((scored.component_semantic * 100)::numeric, 2),
    round((scored.component_text * 100)::numeric, 2),
    round((scored.component_structured * 100)::numeric, 2),
    round((scored.component_filename * 100)::numeric, 2),
    count(*) over () as total_count
  from scored
  order by scored.raw_score desc, scored.scored_asset_id asc
  limit (select bounded_limit from bounded)
  offset (select bounded_offset from bounded);
$$;

revoke all on function public.hybrid_search_assets(
  text, public.vector, text, text, text, text, text, integer, integer
) from public, anon;
grant execute on function public.hybrid_search_assets(
  text, public.vector, text, text, text, text, text, integer, integer
) to authenticated;

comment on function public.hybrid_search_assets(
  text, public.vector, text, text, text, text, text, integer, integer
) is 'Permission-filtered KDI hybrid semantic search using the approved 1024-dimensional local embedding space; raw vectors are never returned.';

commit;
