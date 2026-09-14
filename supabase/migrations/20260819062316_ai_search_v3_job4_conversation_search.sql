-- KDI AI Search V3 Job 4: backend-controlled conversational search history.

create table public.search_sessions (
 id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete cascade,
 status text not null default 'ACTIVE' check(status in ('ACTIVE','COMPLETED','EXPIRED')),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), last_activity_at timestamptz not null default now(),
 metadata jsonb not null default '{}'::jsonb check(jsonb_typeof(metadata)='object')
);
create index search_sessions_user_activity_idx on public.search_sessions(user_id,last_activity_at desc) where user_id is not null;
create index search_sessions_status_idx on public.search_sessions(status,last_activity_at desc);

create table public.search_queries (
 id uuid primary key default gen_random_uuid(), session_id uuid not null references public.search_sessions(id) on delete cascade,
 parent_query_id uuid references public.search_queries(id) on delete set null, sequence_number integer not null check(sequence_number >= 0),
 raw_query text not null check(btrim(raw_query)<>''), resolved_query text,
 query_type text not null check(query_type in ('NEW_SEARCH','REFINEMENT','COUNT_CHANGE','NEXT_RESULTS','SORT_CHANGE','FILTER_CHANGE')),
 requested_count integer not null default 5 check(requested_count > 0 and requested_count <= 10000),
 count_explicit boolean not null default false, result_offset integer not null default 0 check(result_offset >= 0), media_type text,
 parsed_intent jsonb not null default '{}'::jsonb check(jsonb_typeof(parsed_intent)='object'),
 structured_filters jsonb not null default '{}'::jsonb check(jsonb_typeof(structured_filters)='object'),
 semantic_intent jsonb not null default '{}'::jsonb check(jsonb_typeof(semantic_intent)='object'),
 sort_mode text not null default 'RELEVANCE', minimum_relevance numeric(5,4) check(minimum_relevance between 0 and 1),
 status text not null default 'PENDING' check(status in ('PENDING','RESOLVED','SEARCHING','COMPLETED','FAILED','CANCELLED')),
 created_at timestamptz not null default now(), resolved_at timestamptz,
 constraint search_queries_session_sequence_key unique(session_id,sequence_number),
 constraint search_queries_id_session_key unique(id,session_id)
);
create index search_queries_parent_idx on public.search_queries(parent_query_id) where parent_query_id is not null;
create index search_queries_session_created_idx on public.search_queries(session_id,created_at);

create table public.search_results (
 id uuid primary key default gen_random_uuid(), search_query_id uuid not null references public.search_queries(id) on delete cascade,
 asset_id uuid not null references public.assets(id) on delete cascade, scene_id uuid, keyframe_id uuid, transcript_chunk_id bigint,
 rank integer not null check(rank > 0), overall_score numeric(5,4) not null check(overall_score between 0 and 1),
 structured_score numeric(5,4), semantic_score numeric(5,4), visual_score numeric(5,4), transcript_score numeric(5,4), action_score numeric(5,4), relationship_score numeric(5,4), clinical_score numeric(5,4), marketing_score numeric(5,4), filename_score numeric(5,4),
 matched_start_seconds numeric(14,3), matched_end_seconds numeric(14,3), match_reason text, matched_features jsonb not null default '{}'::jsonb check(jsonb_typeof(matched_features)='object'), result_group_key text,
 created_at timestamptz not null default now(),
 constraint search_results_component_scores check(structured_score between 0 and 1 and semantic_score between 0 and 1 and visual_score between 0 and 1 and transcript_score between 0 and 1 and action_score between 0 and 1 and relationship_score between 0 and 1 and clinical_score between 0 and 1 and marketing_score between 0 and 1 and filename_score between 0 and 1),
 constraint search_results_time check((matched_start_seconds is null and matched_end_seconds is null) or (matched_start_seconds >= 0 and matched_end_seconds > matched_start_seconds)),
 constraint search_results_keyframe_requires_scene check(keyframe_id is null or scene_id is not null),
 constraint search_results_query_rank_key unique(search_query_id,rank),
 constraint search_results_query_asset_key unique(search_query_id,asset_id),
 constraint search_results_id_query_key unique(id,search_query_id),
 constraint search_results_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 constraint search_results_keyframe_fkey foreign key(keyframe_id,scene_id,asset_id) references public.asset_keyframes(id,scene_id,asset_id) on delete cascade,
 constraint search_results_transcript_asset_fkey foreign key(transcript_chunk_id,asset_id) references public.asset_transcript_chunks(id,asset_id) on delete cascade
);
create index search_results_asset_idx on public.search_results(asset_id);
create index search_results_scene_idx on public.search_results(scene_id) where scene_id is not null;

create table public.search_feedback (
 id uuid primary key default gen_random_uuid(), search_query_id uuid not null references public.search_queries(id) on delete cascade,
 search_result_id uuid, asset_id uuid, scene_id uuid, user_id uuid references auth.users(id) on delete set null,
 feedback_type text not null check(feedback_type in ('GOOD_MATCH','BAD_MATCH','MISSING_RESULT','WRONG_RANK','WRONG_TIMESTAMP','WRONG_PERSON','WRONG_TREATMENT','OTHER')),
 comment text, created_at timestamptz not null default now(),
 constraint search_feedback_result_query_fkey foreign key(search_result_id,search_query_id) references public.search_results(id,search_query_id) on delete cascade,
 constraint search_feedback_asset_fkey foreign key(asset_id) references public.assets(id) on delete cascade,
 constraint search_feedback_scene_asset_fkey foreign key(scene_id,asset_id) references public.asset_scenes(id,asset_id) on delete cascade,
 constraint search_feedback_scene_requires_asset check(scene_id is null or asset_id is not null)
);
create index search_feedback_query_idx on public.search_feedback(search_query_id);
create index search_feedback_result_idx on public.search_feedback(search_result_id) where search_result_id is not null;
create index search_feedback_user_idx on public.search_feedback(user_id,created_at desc) where user_id is not null;

create function public.validate_job4_parent_query_scope() returns trigger
language plpgsql security invoker set search_path='' as $$
begin
 if new.parent_query_id is not null and not exists(select 1 from public.search_queries p where p.id=new.parent_query_id and p.session_id=new.session_id) then raise exception using errcode='23514',message='parent query must belong to session'; end if;
 return new;
end $$;
create function public.validate_job4_search_result_scope() returns trigger
language plpgsql security invoker set search_path='' as $$
declare v_scene_start numeric; v_scene_end numeric; v_transcript_scene uuid;
begin
 if new.transcript_chunk_id is not null then select t.scene_id into v_transcript_scene from public.asset_transcript_chunks t where t.id=new.transcript_chunk_id and t.asset_id=new.asset_id; if not found or (new.scene_id is not null and new.scene_id is distinct from v_transcript_scene) then raise exception using errcode='23514',message='transcript scope mismatch'; end if; end if;
 if new.scene_id is not null and new.matched_start_seconds is not null then select s.start_seconds,s.end_seconds into v_scene_start,v_scene_end from public.asset_scenes s where s.id=new.scene_id and s.asset_id=new.asset_id; if new.matched_start_seconds<v_scene_start or new.matched_end_seconds>v_scene_end then raise exception using errcode='23514',message='matched timestamps outside scene'; end if; end if;
 return new;
end $$;
create function public.validate_job4_search_feedback_scope() returns trigger
language plpgsql security invoker set search_path='' as $$
declare v_result_asset uuid; v_result_scene uuid;
begin
 if new.search_result_id is not null then select r.asset_id,r.scene_id into v_result_asset,v_result_scene from public.search_results r where r.id=new.search_result_id and r.search_query_id=new.search_query_id; if (new.asset_id is not null and new.asset_id is distinct from v_result_asset) or (new.scene_id is not null and new.scene_id is distinct from v_result_scene) then raise exception using errcode='23514',message='feedback scope mismatch'; end if; end if;
 return new;
end $$;
revoke all on function public.validate_job4_parent_query_scope(),public.validate_job4_search_result_scope(),public.validate_job4_search_feedback_scope() from public,anon,authenticated,service_role;
create trigger search_queries_scope before insert or update on public.search_queries for each row execute function public.validate_job4_parent_query_scope();
create trigger search_results_scope before insert or update on public.search_results for each row execute function public.validate_job4_search_result_scope();
create trigger search_feedback_scope before insert or update on public.search_feedback for each row execute function public.validate_job4_search_feedback_scope();

alter table public.search_sessions enable row level security; alter table public.search_queries enable row level security; alter table public.search_results enable row level security; alter table public.search_feedback enable row level security;
revoke all on table public.search_sessions,public.search_queries,public.search_results,public.search_feedback from public,anon,authenticated;
grant all on table public.search_sessions,public.search_queries,public.search_results,public.search_feedback to service_role;
create trigger search_sessions_set_updated_at before update on public.search_sessions for each row execute function public.set_updated_at();

;
