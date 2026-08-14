begin;

-- Natural-language search powered by hybrid semantic search. Adds AI
-- metadata (asset_semantic_index) and embeddings (asset_embeddings) as two
-- separate tables plus a secure hybrid ranking function. Purely additive:
-- no existing table is altered destructively, no existing asset row is
-- touched.
--
-- Metadata and embeddings are split so a future embedding model/version can
-- be rebuilt (a new asset_embeddings row per asset/provider/model/version)
-- without rewriting AI-generated metadata, and so raw embedding vectors can
-- be sealed off from any direct client access independently of metadata
-- readability (see the RLS/grant notes below).
--
-- Rollback: drop the objects created below in reverse order, e.g.
--   drop function if exists public.hybrid_search_assets(text, public.vector, text, text, text, text, text, integer, integer);
--   drop function if exists public.claim_semantic_index_batch(text, integer, integer, uuid[]);
--   drop table if exists public.asset_embeddings;
--   drop table if exists public.asset_semantic_index;
--   drop extension if exists vector;  -- only if nothing else depends on it
--   drop extension if exists pg_trgm; -- only if nothing else depends on it

-- The production project resolves pgvector as public.vector. Keep the type,
-- cosine operator, and operator classes in that same extension schema. SQL
-- functions below intentionally use search_path='', so extension operators
-- must be schema-qualified rather than made visible through a broader path.
create extension if not exists vector with schema public;
create extension if not exists pg_trgm with schema public;

do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_extension extension_row
    join pg_catalog.pg_namespace namespace_row
      on namespace_row.oid = extension_row.extnamespace
    where extension_row.extname = 'vector'
      and namespace_row.nspname = 'public'
  ) then
    raise exception 'pgvector must be installed in schema public for this migration';
  end if;
  if pg_catalog.to_regoperator('public.<=>(public.vector,public.vector)') is null then
    raise exception 'pgvector cosine-distance operator public.<=> is unavailable';
  end if;
end
$$;

-- AI-generated business metadata for one canonical asset. Restricted to the
-- approved five-field contract plus a display caption; everything else
-- (provider/model/version, status, cost) is internal processing state.
create table if not exists public.asset_semantic_index (
  asset_id uuid primary key references public.assets(id) on delete cascade,
  content_type text not null default 'Other',
  treatment text,
  subject text,
  doctor_name text,
  short_caption text not null default '',
  ai_description text not null default '',
  searchable_text text not null default '',
  search_vector tsvector generated always as (
    to_tsvector('english', searchable_text)
  ) stored,
  description_provider text,
  description_model text,
  description_version text,
  source_fingerprint text,
  indexing_status text not null default 'PENDING',
  attempt_count integer not null default 0,
  indexed_at timestamptz,
  last_error text,
  last_cost_usd numeric(10, 6),
  claim_owner text,
  claimed_at timestamptz,
  claim_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_semantic_index_content_type_check check (
    content_type in (
      'Before & After',
      'Treatment Result',
      'Patient Testimonial',
      'Doctor Explanation',
      'Treatment Procedure',
      'Consultation',
      'Educational Video',
      'Clinic Environment',
      'Promotional Content',
      'Doctor Talking',
      'Patient Interview',
      'Other'
    )
  ),
  constraint asset_semantic_index_short_caption_len_check
    check (indexing_status <> 'INDEXED' or char_length(btrim(short_caption)) between 1 and 200),
  constraint asset_semantic_index_ai_description_len_check
    check (indexing_status <> 'INDEXED' or char_length(btrim(ai_description)) between 1 and 1000),
  constraint asset_semantic_index_searchable_text_len_check
    check (char_length(searchable_text) <= 4000),
  constraint asset_semantic_index_status_check check (
    indexing_status in (
      'PENDING',
      'QUEUED',
      'PROCESSING',
      'INDEXED',
      'FAILED_RETRYABLE',
      'FAILED_PERMANENT',
      'SKIPPED_INELIGIBLE'
    )
  ),
  constraint asset_semantic_index_attempt_count_check
    check (attempt_count between 0 and 5),
  constraint asset_semantic_index_claim_check check (
    (
      claim_owner is null
      and claimed_at is null
      and claim_expires_at is null
    )
    or (
      claim_owner is not null
      and claimed_at is not null
      and claim_expires_at > claimed_at
    )
  )
);

comment on table public.asset_semantic_index is
  'AI-generated search metadata for natural-language search. One row per canonical asset. No embedding column - see asset_embeddings.';
comment on column public.asset_semantic_index.short_caption is
  'One concise display sentence for grid cards. Not a medical/marketing claim.';

-- Embedding vectors, kept separate from asset_semantic_index so a model
-- upgrade can add a new row per asset/provider/model/version without
-- rewriting AI metadata, and so raw vectors can be denied direct client
-- access independently (see the grants below - no policy is added for
-- `authenticated` on this table on purpose).
create table if not exists public.asset_embeddings (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  embedding_provider text not null,
  embedding_model text not null,
  embedding_dimensions integer not null,
  embedding_version text not null,
  embedding public.vector(1536) not null,
  searchable_text_hash text not null,
  embedded_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint asset_embeddings_dimensions_check check (embedding_dimensions = 1536),
  constraint asset_embeddings_provider_model_version_unique
    unique (asset_id, embedding_provider, embedding_model, embedding_version)
);

comment on table public.asset_embeddings is
  'Embedding vectors for natural-language search. One row per asset/provider/model/version combination, so a future model can be added without touching asset_semantic_index. Internal technical data - never expose raw values in the UI or API responses.';
comment on column public.asset_embeddings.embedding is
  'Fixed at 1536 dimensions for the currently approved provider/model (OpenAI text-embedding-3-small). Never truncated/padded - a provider adapter must reject an incompatible response instead.';

drop trigger if exists asset_semantic_index_set_updated_at
  on public.asset_semantic_index;
create trigger asset_semantic_index_set_updated_at
before update on public.asset_semantic_index
for each row execute function public.set_updated_at();

drop trigger if exists asset_embeddings_set_updated_at
  on public.asset_embeddings;
create trigger asset_embeddings_set_updated_at
before update on public.asset_embeddings
for each row execute function public.set_updated_at();

create index if not exists asset_semantic_index_search_vector_idx
  on public.asset_semantic_index using gin (search_vector);
create index if not exists asset_semantic_index_status_idx
  on public.asset_semantic_index (indexing_status, attempt_count);
create index if not exists asset_semantic_index_claim_expiry_idx
  on public.asset_semantic_index (claim_expires_at)
  where claim_expires_at is not null;
create index if not exists asset_semantic_index_content_type_idx
  on public.asset_semantic_index (content_type);

create index if not exists asset_embeddings_asset_id_idx
  on public.asset_embeddings (asset_id);
create index if not exists asset_embeddings_provider_model_version_idx
  on public.asset_embeddings (embedding_provider, embedding_model, embedding_version);
-- No vector-similarity index (ivfflat/hnsw) yet: repository evidence does
-- not show a need for one at pilot scale, and these index types need a
-- representative amount of real data to tune (lists/m) sensibly. A
-- brute-force `<=>` scan over a handful of pilot rows is fine; add a tuned
-- index in a follow-up migration once real embeddings exist.

-- Accelerates today's filename ilike search too (previously a seq scan).
create index if not exists assets_file_name_trgm_idx
  on public.assets using gin (file_name gin_trgm_ops);

alter table public.asset_semantic_index enable row level security;

drop policy if exists asset_semantic_index_individual_read
  on public.asset_semantic_index;
create policy asset_semantic_index_individual_read
on public.asset_semantic_index for select
to authenticated
using ((select private.is_active_app_user()));

revoke all on table public.asset_semantic_index from public, anon;
revoke insert, update, delete, truncate
  on table public.asset_semantic_index from authenticated;
grant select on table public.asset_semantic_index to authenticated;
grant select, insert, update, delete
  on table public.asset_semantic_index to service_role;

-- asset_embeddings: RLS enabled, but deliberately NO select policy for
-- `authenticated`/`anon` - raw embedding values must never be selectable
-- directly by a client role, only through hybrid_search_assets below
-- (security definer, which manually re-checks private.is_active_app_user()
-- before touching this table). Only service_role (the indexing worker)
-- reads/writes it directly.
alter table public.asset_embeddings enable row level security;
revoke all on table public.asset_embeddings from public, anon, authenticated;
grant select, insert, update, delete on table public.asset_embeddings to service_role;

-- Atomic bounded claim for the semantic-indexing worker, mirroring
-- claim_asset_destinations. Operates on asset_semantic_index only -
-- embeddings are written by the worker directly (service_role) once
-- description+embedding generation for a claimed asset completes.
-- service_role only.
create or replace function public.claim_semantic_index_batch(
  requested_claim_owner text,
  requested_limit integer default 1,
  requested_lease_seconds integer default 900,
  requested_asset_ids uuid[] default null
)
returns table (
  asset_id uuid,
  attempt_count integer,
  indexing_status text
)
language sql
security invoker
set search_path = ''
as $$
  with candidates as (
    select candidate_source.asset_id
    from public.asset_semantic_index as candidate_source
    where candidate_source.attempt_count < 5
      and (
        requested_asset_ids is null
        or candidate_source.asset_id = any(requested_asset_ids)
      )
      and (
        candidate_source.indexing_status in ('PENDING', 'QUEUED', 'FAILED_RETRYABLE')
        or (
          candidate_source.indexing_status = 'PROCESSING'
          and candidate_source.claim_expires_at <= now()
        )
      )
      and requested_limit between 1 and 200
      and requested_lease_seconds between 30 and 3600
      and nullif(btrim(requested_claim_owner), '') is not null
    order by
      case candidate_source.indexing_status
        when 'FAILED_RETRYABLE' then 0
        else 1
      end,
      candidate_source.created_at,
      candidate_source.asset_id
    for update skip locked
    limit requested_limit
  )
  update public.asset_semantic_index as target
  set
    indexing_status = 'PROCESSING',
    attempt_count = target.attempt_count + 1,
    claim_owner = nullif(btrim(requested_claim_owner), ''),
    claimed_at = now(),
    claim_expires_at = now() + make_interval(secs => requested_lease_seconds),
    last_error = null
  from candidates
  where target.asset_id = candidates.asset_id
  returning target.asset_id, target.attempt_count, target.indexing_status;
$$;

revoke all on function public.claim_semantic_index_batch(text, integer, integer, uuid[])
  from public, anon, authenticated;
grant execute on function public.claim_semantic_index_batch(text, integer, integer, uuid[])
  to service_role;

-- Secure server-side hybrid search.
--
-- security definer (not invoker): this function is the ONLY path through
-- which asset_embeddings may ever be read, and that table intentionally
-- grants no SELECT to `authenticated` (see above). A definer function runs
-- with the function owner's privileges, so it must - and does - manually
-- re-check private.is_active_app_user() itself; that check reads auth.uid()
-- from the caller's own JWT regardless of the function's security context,
-- so this is equivalent to (not weaker than) the RLS check every sibling
-- table already applies. assets/asset_semantic_index/asset_sources/
-- source_files/source_folders are read under the same elevated privilege
-- inside this function for consistency, but nothing beyond the single
-- is_active_app_user() gate is bypassed - that is the only authorization
-- rule those tables' own RLS policies encode today.
--
-- Ranking weights are centralized here (nowhere else in the codebase
-- hardcodes them) and documented: pilot defaults, to be tuned after the
-- 20-query evaluation (see the evaluation report format used elsewhere in
-- this project).
--   45% semantic vector similarity (asset_embeddings.embedding <=> query)
--   20% PostgreSQL full-text relevance (asset_semantic_index.search_vector)
--    8% treatment field match
--    7% subject field match
--   10% doctor_name field match
--   10% filename match
-- Never returns the embedding column. Match percentage is computed
-- per-query here and is never stored on the asset.
create or replace function public.hybrid_search_assets(
  search_query text,
  query_embedding public.vector(1536) default null,
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
  -- Centralized ranking weights. Change here only.
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

commit;
