begin;

-- One transaction commits the validated metadata, exact vector, and INDEXED
-- state. JSON inputs keep the REST/RPC signature stable without changing the
-- existing tables or search surface.
create or replace function public.complete_semantic_index_atomically(
  requested_asset_id uuid,
  requested_claim_owner text,
  requested_metadata jsonb,
  requested_embedding jsonb
) returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  updated_count integer;
  vector_values public.vector(1024);
begin
  if jsonb_array_length(requested_embedding->'embedding') <> 1024 then
    raise exception 'embedding must contain exactly 1024 values';
  end if;
  if (requested_embedding->>'embedding_dimensions')::integer <> 1024 then
    raise exception 'embedding_dimensions must be exactly 1024';
  end if;
  vector_values := (requested_embedding->'embedding')::text::public.vector(1024);

  insert into public.asset_embeddings (
    asset_id, embedding_provider, embedding_model, embedding_dimensions,
    embedding_version, embedding, searchable_text_hash, embedded_at
  ) values (
    requested_asset_id,
    requested_embedding->>'embedding_provider',
    requested_embedding->>'embedding_model',
    (requested_embedding->>'embedding_dimensions')::integer,
    requested_embedding->>'embedding_version', vector_values,
    requested_embedding->>'searchable_text_hash',
    coalesce((requested_embedding->>'embedded_at')::timestamptz, now())
  ) on conflict (asset_id, embedding_provider, embedding_model, embedding_version)
  do update set embedding = excluded.embedding,
    embedding_dimensions = excluded.embedding_dimensions,
    searchable_text_hash = excluded.searchable_text_hash,
    embedded_at = excluded.embedded_at;

  update public.asset_semantic_index set
    content_type = requested_metadata->>'content_type',
    treatment = nullif(requested_metadata->>'treatment', ''),
    subject = nullif(requested_metadata->>'subject', ''),
    doctor_name = nullif(requested_metadata->>'doctor_name', ''),
    short_caption = requested_metadata->>'short_caption',
    ai_description = requested_metadata->>'ai_description',
    searchable_text = requested_metadata->>'searchable_text',
    description_provider = requested_metadata->>'description_provider',
    description_model = requested_metadata->>'description_model',
    description_version = requested_metadata->>'description_version',
    source_fingerprint = requested_metadata->>'source_fingerprint',
    indexing_status = 'INDEXED', indexed_at = now(), last_error = null,
    last_cost_usd = (requested_metadata->>'last_cost_usd')::numeric,
    claim_owner = null, claimed_at = null, claim_expires_at = null
  where asset_id = requested_asset_id and indexing_status = 'PROCESSING'
    and claim_owner = requested_claim_owner;
  get diagnostics updated_count = row_count;
  if updated_count <> 1 then
    raise exception 'semantic claim lost';
  end if;
  return true;
end;
$$;

revoke all on function public.complete_semantic_index_atomically(uuid, text, jsonb, jsonb)
  from public, anon, authenticated;
grant execute on function public.complete_semantic_index_atomically(uuid, text, jsonb, jsonb)
  to service_role;

commit;
