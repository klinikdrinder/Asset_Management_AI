-- KDI AI Search V3 Job 4: mixed-dimension, multi-level embedding storage.
-- Additive only. No rows are populated and no ANN indexes are created.

alter table public.asset_transcript_chunks
  add constraint asset_transcript_chunks_id_asset_key unique (id, asset_id);

create table public.scene_embeddings (
  id uuid primary key default gen_random_uuid(),
  scene_id uuid not null,
  asset_id uuid not null references public.assets(id) on delete cascade,
  embedding_type text not null check (embedding_type in ('VISUAL','SEMANTIC_TEXT','CLINICAL','ACTION','MARKETING')),
  provider text not null check (btrim(provider) <> ''),
  model_name text not null check (btrim(model_name) <> ''),
  model_version text not null check (btrim(model_version) <> ''),
  embedding_dimensions integer not null check (embedding_dimensions > 0 and embedding_dimensions <= 2000),
  embedding public.vector not null,
  source_text_hash text,
  source_fingerprint text,
  analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
  is_active boolean not null default true,
  embedded_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint scene_embeddings_dimensions_match check (vector_dims(embedding) = embedding_dimensions),
  constraint scene_embeddings_scene_asset_fkey foreign key (scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade
);
create unique index scene_embeddings_one_active_version_idx on public.scene_embeddings(scene_id,embedding_type,provider,model_name,model_version) where is_active;
create index scene_embeddings_asset_idx on public.scene_embeddings(asset_id);
create index scene_embeddings_model_idx on public.scene_embeddings(embedding_type,provider,model_name,model_version,embedding_dimensions) where is_active;
create index scene_embeddings_run_idx on public.scene_embeddings(analysis_run_id) where analysis_run_id is not null;

create table public.keyframe_embeddings (
  id uuid primary key default gen_random_uuid(),
  keyframe_id uuid not null,
  scene_id uuid not null,
  asset_id uuid not null references public.assets(id) on delete cascade,
  embedding_type text not null check (embedding_type in ('VISUAL','SEMANTIC_TEXT','CLINICAL','ACTION','MARKETING')),
  provider text not null check (btrim(provider) <> ''),
  model_name text not null check (btrim(model_name) <> ''),
  model_version text not null check (btrim(model_version) <> ''),
  embedding_dimensions integer not null check (embedding_dimensions > 0 and embedding_dimensions <= 2000),
  embedding public.vector not null,
  source_fingerprint text,
  analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
  is_active boolean not null default true,
  embedded_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint keyframe_embeddings_dimensions_match check (vector_dims(embedding) = embedding_dimensions),
  constraint keyframe_embeddings_keyframe_scene_asset_fkey foreign key (keyframe_id,scene_id,asset_id) references public.asset_keyframes(id,scene_id,asset_id) on delete cascade
);
create unique index keyframe_embeddings_one_active_version_idx on public.keyframe_embeddings(keyframe_id,embedding_type,provider,model_name,model_version) where is_active;
create index keyframe_embeddings_scene_idx on public.keyframe_embeddings(scene_id);
create index keyframe_embeddings_asset_idx on public.keyframe_embeddings(asset_id);
create index keyframe_embeddings_model_idx on public.keyframe_embeddings(embedding_type,provider,model_name,model_version,embedding_dimensions) where is_active;
create index keyframe_embeddings_run_idx on public.keyframe_embeddings(analysis_run_id) where analysis_run_id is not null;

create table public.transcript_embeddings (
  id uuid primary key default gen_random_uuid(),
  transcript_chunk_id bigint not null,
  asset_id uuid not null references public.assets(id) on delete cascade,
  scene_id uuid,
  embedding_type text not null check (embedding_type in ('SEMANTIC_TEXT','CLINICAL','ACTION','MARKETING')),
  provider text not null check (btrim(provider) <> ''),
  model_name text not null check (btrim(model_name) <> ''),
  model_version text not null check (btrim(model_version) <> ''),
  embedding_dimensions integer not null check (embedding_dimensions > 0 and embedding_dimensions <= 2000),
  embedding public.vector not null,
  source_text_hash text not null check (btrim(source_text_hash) <> ''),
  analysis_run_id uuid references public.ai_analysis_runs(id) on delete set null,
  is_active boolean not null default true,
  embedded_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint transcript_embeddings_dimensions_match check (vector_dims(embedding) = embedding_dimensions),
  constraint transcript_embeddings_chunk_asset_fkey foreign key (transcript_chunk_id,asset_id) references public.asset_transcript_chunks(id,asset_id) on delete cascade,
  constraint transcript_embeddings_scene_asset_fkey foreign key (scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade
);
create unique index transcript_embeddings_one_active_version_idx on public.transcript_embeddings(transcript_chunk_id,embedding_type,provider,model_name,model_version) where is_active;
create index transcript_embeddings_scene_idx on public.transcript_embeddings(scene_id) where scene_id is not null;
create index transcript_embeddings_asset_idx on public.transcript_embeddings(asset_id);
create index transcript_embeddings_model_idx on public.transcript_embeddings(embedding_type,provider,model_name,model_version,embedding_dimensions) where is_active;
create index transcript_embeddings_run_idx on public.transcript_embeddings(analysis_run_id) where analysis_run_id is not null;

create function public.validate_job4_transcript_embedding_scope() returns trigger
language plpgsql security invoker set search_path = '' as $$
declare v_scene uuid;
begin
  select t.scene_id into v_scene from public.asset_transcript_chunks t
  where t.id=new.transcript_chunk_id and t.asset_id=new.asset_id;
  if not found then raise exception using errcode='23503', message='transcript chunk does not belong to asset'; end if;
  if new.scene_id is distinct from v_scene then raise exception using errcode='23514', message='embedding scene must match transcript scene'; end if;
  return new;
end $$;
revoke all on function public.validate_job4_transcript_embedding_scope() from public,anon,authenticated,service_role;
create trigger transcript_embeddings_scope before insert or update on public.transcript_embeddings for each row execute function public.validate_job4_transcript_embedding_scope();

alter table public.scene_embeddings enable row level security;
alter table public.keyframe_embeddings enable row level security;
alter table public.transcript_embeddings enable row level security;
revoke all on table public.scene_embeddings,public.keyframe_embeddings,public.transcript_embeddings from public,anon,authenticated;
grant all on table public.scene_embeddings,public.keyframe_embeddings,public.transcript_embeddings to service_role;
create trigger scene_embeddings_set_updated_at before update on public.scene_embeddings for each row execute function public.set_updated_at();
create trigger keyframe_embeddings_set_updated_at before update on public.keyframe_embeddings for each row execute function public.set_updated_at();
create trigger transcript_embeddings_set_updated_at before update on public.transcript_embeddings for each row execute function public.set_updated_at();

;
