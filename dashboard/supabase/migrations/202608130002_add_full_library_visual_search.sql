begin;

create table if not exists public.asset_visual_embeddings (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  model_provider text not null,
  model_name text not null,
  model_version text not null,
  embedding_dimensions integer not null check (embedding_dimensions = 512),
  embedding public.vector(512) not null,
  source_fingerprint text not null,
  source_method text not null check (source_method in ('DRIVE_THUMBNAIL','DRIVE_IMAGE','VIDEO_FRAMES')),
  frame_count integer not null check (frame_count between 1 and 3),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  indexed_at timestamptz not null default now(),
  unique(asset_id, model_provider, model_name, model_version, source_fingerprint)
);

create table if not exists public.asset_visual_index_jobs (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  model_provider text not null,
  model_name text not null,
  model_version text not null,
  source_fingerprint text not null,
  status text not null check (status in ('QUEUED','PROCESSING','INDEXED','RETRY','FAILED','NOT_APPLICABLE')),
  attempt_count integer not null default 0 check (attempt_count between 0 and 5),
  claim_owner text,
  claimed_at timestamptz,
  claim_expires_at timestamptz,
  next_attempt_at timestamptz,
  failure_code text,
  failure_detail text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  unique(asset_id, model_provider, model_name, model_version, source_fingerprint)
);

create index if not exists asset_visual_embeddings_identity_idx on public.asset_visual_embeddings(model_provider,model_name,model_version);
create index if not exists asset_visual_jobs_claim_idx on public.asset_visual_index_jobs(status,next_attempt_at,created_at);
alter table public.asset_visual_embeddings enable row level security;
alter table public.asset_visual_index_jobs enable row level security;
revoke all on public.asset_visual_embeddings, public.asset_visual_index_jobs from public,anon,authenticated;
grant select,insert,update,delete on public.asset_visual_embeddings, public.asset_visual_index_jobs to service_role;

create or replace function public.queue_new_asset_visual_index() returns trigger language plpgsql security definer set search_path='' as $$
begin
  if new.content_hash is not null then
    insert into public.asset_visual_index_jobs(asset_id,model_provider,model_name,model_version,source_fingerprint,status)
    values(new.id,'open_clip','ViT-B-32','laion2b_s34b_b79k',new.content_hash,
      case when lower(coalesce(new.mime_type,'')) like 'image/%' or lower(coalesce(new.mime_type,'')) like 'video/%' then 'QUEUED' else 'NOT_APPLICABLE' end)
    on conflict do nothing;
  end if;
  return new;
end $$;
drop trigger if exists assets_queue_visual_index on public.assets;
create trigger assets_queue_visual_index after insert or update of content_hash,mime_type on public.assets
for each row execute function public.queue_new_asset_visual_index();

create or replace function public.queue_visual_index_jobs(p_provider text,p_model text,p_version text)
returns table(queued bigint,not_applicable bigint) language plpgsql security invoker set search_path='' as $$
begin
  insert into public.asset_visual_index_jobs(asset_id,model_provider,model_name,model_version,source_fingerprint,status)
  select a.id,p_provider,p_model,p_version,a.content_hash,
    case when lower(coalesce(a.mime_type,'')) like 'image/%' or lower(coalesce(a.mime_type,'')) like 'video/%' then 'QUEUED' else 'NOT_APPLICABLE' end
  from public.assets a
  where a.content_hash is not null
  on conflict(asset_id,model_provider,model_name,model_version,source_fingerprint) do nothing;
  return query select
    count(*) filter(where j.status='QUEUED'),count(*) filter(where j.status='NOT_APPLICABLE')
    from public.asset_visual_index_jobs j where j.model_provider=p_provider and j.model_name=p_model and j.model_version=p_version;
end $$;

create or replace function public.claim_visual_index_job(p_owner text,p_lease_seconds integer default 1800)
returns setof public.asset_visual_index_jobs language plpgsql security invoker set search_path='' as $$
begin
  return query with candidate as (
    select id from public.asset_visual_index_jobs
    where (status in ('QUEUED','RETRY') and coalesce(next_attempt_at,now())<=now())
       or (status='PROCESSING' and claim_expires_at<now())
    order by created_at for update skip locked limit 1
  ) update public.asset_visual_index_jobs j set status='PROCESSING',claim_owner=p_owner,claimed_at=now(),
    claim_expires_at=now()+make_interval(secs=>greatest(60,p_lease_seconds)),attempt_count=j.attempt_count+1,updated_at=now()
  from candidate where j.id=candidate.id returning j.*;
end $$;

create or replace function public.complete_visual_index_job(p_job_id uuid,p_owner text,p_embedding jsonb)
returns boolean language plpgsql security invoker set search_path='' as $$
declare j public.asset_visual_index_jobs; v public.vector(512);
begin
  select * into j from public.asset_visual_index_jobs where id=p_job_id and status='PROCESSING' and claim_owner=p_owner for update;
  if not found then raise exception 'visual claim lost'; end if;
  if jsonb_array_length(p_embedding->'embedding')<>512 then raise exception 'visual embedding must contain 512 values'; end if;
  v := (p_embedding->'embedding')::text::public.vector(512);
  insert into public.asset_visual_embeddings(asset_id,model_provider,model_name,model_version,embedding_dimensions,embedding,source_fingerprint,source_method,frame_count,indexed_at)
  values(j.asset_id,j.model_provider,j.model_name,j.model_version,512,v,j.source_fingerprint,p_embedding->>'source_method',(p_embedding->>'frame_count')::integer,now())
  on conflict(asset_id,model_provider,model_name,model_version,source_fingerprint) do update set embedding=excluded.embedding,
    embedding_dimensions=512,source_method=excluded.source_method,frame_count=excluded.frame_count,updated_at=now(),indexed_at=now();
  update public.asset_visual_index_jobs set status='INDEXED',claim_owner=null,claimed_at=null,claim_expires_at=null,
    failure_code=null,failure_detail=null,completed_at=now(),updated_at=now() where id=p_job_id;
  return true;
end $$;

create or replace function public.fail_visual_index_job(p_job_id uuid,p_owner text,p_code text,p_detail text,p_retryable boolean)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
  update public.asset_visual_index_jobs set status=case when p_retryable and attempt_count<5 then 'RETRY' else 'FAILED' end,
    next_attempt_at=case when p_retryable and attempt_count<5 then now()+interval '5 minutes' else null end,
    failure_code=left(p_code,80),failure_detail=left(p_detail,1000),claim_owner=null,claimed_at=null,claim_expires_at=null,updated_at=now()
  where id=p_job_id and status='PROCESSING' and claim_owner=p_owner;
  return found;
end $$;

revoke all on function public.queue_visual_index_jobs(text,text,text),public.claim_visual_index_job(text,integer),
  public.complete_visual_index_job(uuid,text,jsonb),public.fail_visual_index_job(uuid,text,text,text,boolean) from public,anon,authenticated;
grant execute on function public.queue_visual_index_jobs(text,text,text),public.claim_visual_index_job(text,integer),
  public.complete_visual_index_job(uuid,text,jsonb),public.fail_visual_index_job(uuid,text,text,text,boolean) to service_role;

create or replace function public.hybrid_search_assets_v2(
  search_query text,visual_query_embedding public.vector(512) default null,
  visual_provider text default null,visual_model text default null,visual_version text default null,
  qwen_query_embedding public.vector(1024) default null,qwen_provider text default null,qwen_model text default null,qwen_version text default null,
  filter_category text default null,filter_extension text default null,result_limit integer default 25,result_offset integer default 0)
returns table(asset_id uuid,match_score numeric,content_type text,treatment text,subject text,doctor_name text,short_caption text,
  ai_description text,visual_score numeric,semantic_score numeric,text_score numeric,structured_score numeric,filename_score numeric,total_count bigint)
language sql security definer set search_path='' stable as $$
with b as (select nullif(btrim(search_query),'') q,greatest(1,least(coalesce(result_limit,25),100)) lim,greatest(0,coalesce(result_offset,0)) off),
s as (select a.id,si.content_type,si.treatment,si.subject,si.doctor_name,si.short_caption,si.ai_description,
  coalesce(1-(ve.embedding OPERATOR(public.<=>) visual_query_embedding),0) vs,
  coalesce(1-(qe.embedding OPERATOR(public.<=>) qwen_query_embedding),0) qs,
  coalesce(ts_rank(si.search_vector,plainto_tsquery('english',b.q)),0) ts,
  (case when si.treatment OPERATOR(public.%) b.q then 1 else 0 end+case when si.subject OPERATOR(public.%) b.q then 1 else 0 end+case when si.doctor_name OPERATOR(public.%) b.q then 1 else 0 end)/3.0 ss,
  case when a.file_name ilike('%'||b.q||'%') then 1 else 0 end fs
 from public.assets a cross join b
 left join public.asset_semantic_index si on si.asset_id=a.id and si.indexing_status='INDEXED'
 left join public.asset_visual_embeddings ve on ve.asset_id=a.id and ve.model_provider=visual_provider and ve.model_name=visual_model and ve.model_version=visual_version
 left join public.asset_embeddings qe on qe.asset_id=a.id and qe.embedding_provider=qwen_provider and qe.embedding_model=qwen_model and qe.embedding_version=qwen_version
 where private.is_active_app_user() and exists(select 1 from public.asset_destinations ad where ad.asset_id=a.id and ad.upload_status='VERIFIED' and ad.destination_google_file_id is not null)
 and exists(select 1 from public.asset_sources l join public.source_files sf on sf.id=l.source_file_id join public.source_folders f on f.id=sf.source_folder_id where l.asset_id=a.id and not coalesce(sf.is_missing,false) and sf.sync_classification is distinct from 'REMOVED_FROM_SOURCE' and f.active)
 and (filter_extension is null or a.file_extension ilike filter_extension)
 and (filter_category is null or filter_category='image' and lower(coalesce(a.mime_type,'')) like 'image/%' or filter_category='video' and lower(coalesce(a.mime_type,'')) like 'video/%' or filter_category='document' and lower(coalesce(a.mime_type,'')) not like 'image/%' and lower(coalesce(a.mime_type,'')) not like 'video/%')
 and (b.q is not null or visual_query_embedding is not null or qwen_query_embedding is not null)),
r as(select *,0.65*vs+0.15*qs+0.15*greatest(ts,ss)+0.05*fs final from s)
select id,round((least(greatest(final,0),1)*100)::numeric,2),content_type,treatment,subject,doctor_name,short_caption,ai_description,
 round((vs*100)::numeric,2),round((qs*100)::numeric,2),round((ts*100)::numeric,2),round((ss*100)::numeric,2),round((fs*100)::numeric,2),count(*) over()
from r order by final desc,id limit(select lim from b) offset(select off from b)
$$;
revoke all on function public.hybrid_search_assets_v2(text,public.vector,text,text,text,public.vector,text,text,text,text,text,integer,integer) from public,anon;
grant execute on function public.hybrid_search_assets_v2(text,public.vector,text,text,text,public.vector,text,text,text,text,text,integer,integer) to authenticated;
commit;
