import {readFileSync} from "node:fs";
import path from "node:path";

function loadEnv(file:string){
  try{return Object.fromEntries(readFileSync(file,"utf8").replace(/^\uFEFF/,"").split(/\r?\n/).flatMap(line=>{
    const match=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    return match?[[match[1],match[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[];
  }))}catch{return{}}
}

const root=path.resolve(process.cwd(),"..");
const rootEnv=loadEnv(path.join(root,".env.local"));
const dashboardEnv=loadEnv(path.join(process.cwd(),".env.local"));
const url=dashboardEnv.NEXT_PUBLIC_SUPABASE_URL||rootEnv.NEXT_PUBLIC_SUPABASE_URL;
const token=[rootEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN,dashboardEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN]
  .find(value=>value?.startsWith("sbp_"));
if(!url||!token)throw new Error("Supabase management configuration unavailable");
const ref=new URL(url).hostname.split(".")[0];

const sql=`
select json_build_object(
  'search_functions',(
    select json_agg(json_build_object(
      'name',p.proname,
      'authenticated_execute',has_function_privilege('authenticated',p.oid,'EXECUTE'),
      'anon_execute',has_function_privilege('anon',p.oid,'EXECUTE'),
      'service_role_execute',has_function_privilege('service_role',p.oid,'EXECUTE')
    ) order by p.proname)
    from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname in (
      'hybrid_search_assets','hybrid_search_assets_v2','hybrid_search_assets_v3',
      'match_phase17_semantic_embeddings','match_kdi_search_v4_embeddings',
      'match_kdi_semantic_search_embeddings'
    )
  ),
  'fully_indexed_assets',(select count(*) from public.kdi_search_ready_assets_v1 where search_ready),
  'videos',(select count(*) from public.kdi_search_ready_assets_v1 where search_ready and mime_type like 'video/%'),
  'images',(select count(*) from public.kdi_search_ready_assets_v1 where search_ready and mime_type like 'image/%'),
  'canonical_scenes',(select count(*) from public.asset_scenes where canonical_active),
  'canonical_keyframes',(select count(*) from public.asset_keyframes k join public.asset_scenes s on s.id=k.scene_id where s.canonical_active),
  'asset_documents',(select count(*) from public.search_document_builds where active and not stale and status='READY' and document_type='ASSET'),
  'scene_documents',(select count(*) from public.search_document_builds where active and not stale and status='READY' and document_type='SCENE'),
  'active_layer_duplicates',(select count(*) from (select 1 from public.asset_semantic_layers where active group by asset_id,layer_id,semantic_spec_version having count(*)>1) d),
  'active_embedding_duplicates',(select count(*) from (select 1 from public.semantic_embeddings where active and not stale group by asset_id,coalesce(scene_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(event_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(keyframe_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(transcript_chunk_id,-1),coalesce(ocr_observation_id,'00000000-0000-0000-0000-000000000000'::uuid),representation_type,embedding_version,model_version having count(*)>1) d)
) as deployment;
`;
const response=await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`,{
  method:"POST",headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},
  body:JSON.stringify({query:sql}),
});
if(!response.ok)throw new Error(`CANONICAL_SEARCH_VERIFICATION_FAILED:${response.status}:${await response.text()}`);
console.log(JSON.stringify(await response.json(),null,2));
