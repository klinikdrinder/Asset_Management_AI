-- KDI AI Search V3 Job 4: rebuildable asset and scene search projections.

create table public.asset_search_documents (
  asset_id uuid primary key references public.assets(id) on delete cascade,
  searchable_text text not null default '',
  search_vector tsvector generated always as (to_tsvector('english',coalesce(searchable_text,''))) stored,
  title text, short_description text, content_type text,
  primary_treatment_id uuid references public.treatments(id) on delete set null,
  primary_anatomy_id uuid references public.anatomy_terms(id) on delete set null,
  primary_location_id uuid references public.locations(id) on delete set null,
  doctor_person_ids uuid[] not null default '{}',
  search_concepts text[] not null default '{}',
  structured_document jsonb not null default '{}'::jsonb check (jsonb_typeof(structured_document)='object'),
  source_hash text not null, document_version text not null,
  build_status text not null default 'PENDING' check(build_status in ('PENDING','BUILDING','READY','FAILED','STALE')),
  built_at timestamptz, last_error text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index asset_search_documents_search_vector_idx on public.asset_search_documents using gin(search_vector);
create index asset_search_documents_status_idx on public.asset_search_documents(build_status);
create index asset_search_documents_treatment_idx on public.asset_search_documents(primary_treatment_id) where primary_treatment_id is not null;
create index asset_search_documents_anatomy_idx on public.asset_search_documents(primary_anatomy_id) where primary_anatomy_id is not null;
create index asset_search_documents_location_idx on public.asset_search_documents(primary_location_id) where primary_location_id is not null;
create index asset_search_documents_doctors_idx on public.asset_search_documents using gin(doctor_person_ids);
create index asset_search_documents_concepts_idx on public.asset_search_documents using gin(search_concepts);

create table public.scene_search_documents (
  scene_id uuid primary key,
  asset_id uuid not null references public.assets(id) on delete cascade,
  searchable_text text not null default '',
  search_vector tsvector generated always as (to_tsvector('english',coalesce(searchable_text,''))) stored,
  short_description text,
  primary_treatment_id uuid references public.treatments(id) on delete set null,
  primary_anatomy_id uuid references public.anatomy_terms(id) on delete set null,
  primary_action_id uuid references public.actions(id) on delete set null,
  primary_location_id uuid references public.locations(id) on delete set null,
  person_ids uuid[] not null default '{}', search_concepts text[] not null default '{}',
  structured_document jsonb not null default '{}'::jsonb check (jsonb_typeof(structured_document)='object'),
  source_hash text not null, document_version text not null,
  build_status text not null default 'PENDING' check(build_status in ('PENDING','BUILDING','READY','FAILED','STALE')),
  built_at timestamptz, last_error text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  constraint scene_search_documents_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade
);
create index scene_search_documents_search_vector_idx on public.scene_search_documents using gin(search_vector);
create index scene_search_documents_asset_idx on public.scene_search_documents(asset_id);
create index scene_search_documents_status_idx on public.scene_search_documents(build_status);
create index scene_search_documents_treatment_idx on public.scene_search_documents(primary_treatment_id) where primary_treatment_id is not null;
create index scene_search_documents_anatomy_idx on public.scene_search_documents(primary_anatomy_id) where primary_anatomy_id is not null;
create index scene_search_documents_action_idx on public.scene_search_documents(primary_action_id) where primary_action_id is not null;
create index scene_search_documents_location_idx on public.scene_search_documents(primary_location_id) where primary_location_id is not null;
create index scene_search_documents_people_idx on public.scene_search_documents using gin(person_ids);
create index scene_search_documents_concepts_idx on public.scene_search_documents using gin(search_concepts);

alter table public.asset_search_documents enable row level security;
alter table public.scene_search_documents enable row level security;
revoke all on table public.asset_search_documents,public.scene_search_documents from public,anon,authenticated;
grant all on table public.asset_search_documents,public.scene_search_documents to service_role;
create trigger asset_search_documents_set_updated_at before update on public.asset_search_documents for each row execute function public.set_updated_at();
create trigger scene_search_documents_set_updated_at before update on public.scene_search_documents for each row execute function public.set_updated_at();
