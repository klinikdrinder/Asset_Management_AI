begin;

alter table public.semantic_embeddings add column if not exists keyframe_id uuid references public.asset_keyframes(id) on delete cascade;
alter table public.semantic_embeddings add column if not exists representation_type text;
alter table public.semantic_embeddings add column if not exists model_version text;
alter table public.semantic_embeddings add column if not exists source_fingerprint text;
alter table public.semantic_embeddings add column if not exists source_document_fingerprint text;
alter table public.semantic_embeddings add column if not exists semantic_spec_version text not null default 'semantic_index_v1';
alter table public.semantic_embeddings add column if not exists ontology_version text not null default 'KDI_SEMANTIC_V2';
alter table public.semantic_embeddings add column if not exists embedding_version text;
alter table public.semantic_embeddings add column if not exists embedding_bundle_version text;
alter table public.semantic_embeddings add column if not exists vector_fingerprint text;
alter table public.semantic_embeddings add column if not exists preprocessing_version text;
alter table public.semantic_embeddings add column if not exists text_normalization_version text;
alter table public.semantic_embeddings add column if not exists generated_at timestamptz not null default now();
alter table public.semantic_embeddings add column if not exists active boolean not null default true;
alter table public.semantic_embeddings add column if not exists review_status text not null default 'AI_UNREVIEWED';
alter table public.semantic_embeddings add column if not exists metadata jsonb not null default '{}'::jsonb;

alter table public.semantic_embeddings alter column source_text_fingerprint drop not null;

alter table public.semantic_embeddings drop constraint if exists semantic_embeddings_representation_type_check;
alter table public.semantic_embeddings add constraint semantic_embeddings_representation_type_check check(
 representation_type is null or representation_type in(
  'VISUAL_ASSET','VISUAL_SCENE','VISUAL_KEYFRAME','TEXT_ASSET','TEXT_SCENE','TEXT_EVENT','TEXT_TRANSCRIPT','TEXT_OCR'
 )
);
alter table public.semantic_embeddings drop constraint if exists semantic_embeddings_review_status_check;
alter table public.semantic_embeddings add constraint semantic_embeddings_review_status_check check(review_status in('AI_UNREVIEWED','REVIEW_REQUIRED','HUMAN_APPROVED'));
alter table public.semantic_embeddings drop constraint if exists semantic_embeddings_phase12_lineage_check;
alter table public.semantic_embeddings add constraint semantic_embeddings_phase12_lineage_check check(
 representation_type is null or (
  source_fingerprint is not null and model_version is not null and embedding_version is not null and
  embedding_bundle_version is not null and vector_fingerprint is not null
 )
);

create unique index if not exists semantic_embeddings_active_unit_version_idx on public.semantic_embeddings(
 asset_id,
 coalesce(scene_id,'00000000-0000-0000-0000-000000000000'::uuid),
 coalesce(event_id,'00000000-0000-0000-0000-000000000000'::uuid),
 coalesce(keyframe_id,'00000000-0000-0000-0000-000000000000'::uuid),
 coalesce(transcript_chunk_id,-1),
 coalesce(ocr_observation_id,'00000000-0000-0000-0000-000000000000'::uuid),
 representation_type,embedding_version,model_version
) where active and representation_type is not null;

create index if not exists semantic_embeddings_phase12_filter_idx on public.semantic_embeddings(
 representation_type,provider,model,model_version,embedding_version,dimensions,active,stale
);
create index if not exists semantic_embeddings_phase12_asset_idx on public.semantic_embeddings(asset_id,representation_type,active);

comment on table public.semantic_embeddings is 'Versioned mixed-dimension canonical retrieval representations. Query only within a matching provider/model/version/dimension/representation family.';
comment on column public.semantic_embeddings.vector_fingerprint is 'SHA-256 over model/version, dimensions, source fingerprint, and canonical float32 vector bytes.';

revoke insert,update,delete on public.semantic_embeddings from anon,authenticated;
grant select on public.semantic_embeddings to authenticated;
grant select on public.assets,public.asset_destinations,public.asset_scenes,public.asset_events,public.asset_keyframes,
 public.asset_transcript_chunks,public.ocr_observations,public.search_document_builds,public.asset_search_concepts_v2
 to service_role;
grant select,insert,update on public.semantic_analysis_runs,public.semantic_embeddings to service_role;

commit;
