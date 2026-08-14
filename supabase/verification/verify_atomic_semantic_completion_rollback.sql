begin;

do $$
declare
  test_asset uuid;
  original_semantic_count bigint;
  original_embedding_count bigint;
  zero_vector jsonb;
  success_value boolean;
begin
  select count(*) into original_semantic_count from public.asset_semantic_index;
  select count(*) into original_embedding_count from public.asset_embeddings;
  select asset_id into test_asset
  from public.asset_semantic_index
  order by asset_id
  limit 1;
  if test_asset is null then
    raise exception 'verification requires at least one semantic index row';
  end if;

  select jsonb_agg(0.0) into zero_vector from generate_series(1, 1024);

  update public.asset_semantic_index set indexing_status='PROCESSING',
    claim_owner='atomic-success-test', claimed_at=now(), claim_expires_at=now()+interval '5 minutes'
  where asset_id=test_asset;
  select public.complete_semantic_index_atomically(
    test_asset, 'atomic-success-test',
    jsonb_build_object('content_type','Other','short_caption','Synthetic transaction test',
      'ai_description','Synthetic transaction test.','searchable_text','Synthetic transaction test',
      'description_provider','transaction-test','description_model','synthetic','description_version','rollback-v1',
      'source_fingerprint',repeat('0',64),'last_cost_usd',null),
    jsonb_build_object('embedding_provider','transaction-test','embedding_model','synthetic-1024',
      'embedding_dimensions',1024,'embedding_version','rollback-success-v1','embedding',zero_vector,
      'searchable_text_hash',repeat('0',64))
  ) into success_value;
  if not success_value or not exists (
    select 1 from public.asset_semantic_index where asset_id=test_asset and indexing_status='INDEXED'
  ) or not exists (
    select 1 from public.asset_embeddings where asset_id=test_asset and embedding_provider='transaction-test'
      and embedding_version='rollback-success-v1'
  ) then raise exception 'atomic success assertion failed'; end if;

  update public.asset_semantic_index set indexing_status='PROCESSING',
    claim_owner='atomic-failure-test', claimed_at=now(), claim_expires_at=now()+interval '5 minutes'
  where asset_id=test_asset;
  begin
    perform public.complete_semantic_index_atomically(
      test_asset, 'wrong-owner',
      jsonb_build_object('content_type','Other','short_caption','Must roll back',
        'ai_description','Must roll back.','searchable_text','Must roll back',
        'description_provider','transaction-test','description_model','synthetic','description_version','rollback-v1',
        'source_fingerprint',repeat('1',64),'last_cost_usd',null),
      jsonb_build_object('embedding_provider','transaction-test','embedding_model','synthetic-1024',
        'embedding_dimensions',1024,'embedding_version','rollback-failure-v1','embedding',zero_vector,
        'searchable_text_hash',repeat('1',64))
    );
    raise exception 'forced failure unexpectedly succeeded';
  exception when others then
    if sqlerrm = 'forced failure unexpectedly succeeded' then raise; end if;
  end;
  if exists (
    select 1 from public.asset_embeddings where asset_id=test_asset and embedding_provider='transaction-test'
      and embedding_version='rollback-failure-v1'
  ) then raise exception 'forced failure left an embedding behind'; end if;
  if (select count(*) from public.asset_semantic_index) <> original_semantic_count
    or (select count(*) from public.asset_embeddings) <> original_embedding_count + 1
  then raise exception 'transaction test changed unexpected row counts'; end if;
  raise notice 'ATOMIC_SUCCESS_AND_ROLLBACK_VERIFIED';
end;
$$;

rollback;

select count(*) as semantic_rows from public.asset_semantic_index;
select count(*) as embedding_rows from public.asset_embeddings;
