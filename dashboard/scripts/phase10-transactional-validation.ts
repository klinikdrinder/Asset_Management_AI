import { readFileSync } from "node:fs";
import path from "node:path";
function envFile(file:string){try{return Object.fromEntries(readFileSync(file,"utf8").replace(/^\uFEFF/,"").split(/\r?\n/).flatMap(line=>{const m=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return {}}}
const root=path.resolve(process.cwd(),".."),local=envFile(path.join(process.cwd(),".env.local")),parent=envFile(path.join(root,".env.local"));
const url=local.NEXT_PUBLIC_SUPABASE_URL||parent.NEXT_PUBLIC_SUPABASE_URL,token=[parent.SUPABASE_DASHBOARD_ACCESS_TOKEN,local.SUPABASE_DASHBOARD_ACCESS_TOKEN].find(v=>v?.startsWith('sbp_'));if(!url||!token)throw new Error('configuration unavailable');
const ref=new URL(url).hostname.split('.')[0],source=readFileSync(path.join(root,'supabase','migrations','20260824064838_phase10_semantic_database_v1.sql'),'utf8');
const body=source.replace(/^\s*begin\s*;/i,'').replace(/commit\s*;\s*$/i,'');
const validation=`begin;set local lock_timeout='5s';set local statement_timeout='60s';${body}
do $$ begin
 if (select count(*) from public.semantic_layer_definitions where active and spec_version='semantic_index_v1')<>18 then raise exception 'expected exactly 18 layers'; end if;
 if exists(select 1 from public.semantic_layer_definitions group by layer_number having count(*)>1) then raise exception 'duplicate layer numbers'; end if;
 if exists(select 1 from public.semantic_layer_definitions where layer_id not in ('ASSET_IDENTITY_PROVENANCE','GLOBAL_ASSET_UNDERSTANDING','TEMPORAL_SCENE_STRUCTURE','PEOPLE_ROLES','PERSON_APPEARANCE','ANATOMY','TREATMENT_PROCEDURE','ACTIONS_EVENTS','RELATIONSHIPS','CLINICAL_VISUAL_OBSERVATIONS','ENVIRONMENT','CINEMATOGRAPHY','COMPOSITION','SPEECH_TRANSCRIPT_AUDIO','OCR_VISIBLE_TEXT','MARKETING_CONTENT_USAGE','SEMANTIC_NARRATIVE','SEARCH_EMBEDDINGS')) then raise exception 'unexpected canonical layer'; end if;
end $$;rollback;`;
const response=await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({query:validation})});
if(!response.ok)throw new Error(`transactional migration validation failed ${response.status}: ${(await response.text()).slice(0,2000)}`);
console.log(JSON.stringify({transactional_migration_validation:'PASS',rolled_back:true,production_rows_persisted:0,response:await response.json()},null,2));
