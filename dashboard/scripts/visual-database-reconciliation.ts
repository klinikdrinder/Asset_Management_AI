import { readFileSync, readdirSync, statSync, existsSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
function load(file:string){try{return Object.fromEntries(readFileSync(file,"utf8").split(/\r?\n/).flatMap(line=>{const m=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return {}}}
const root=path.resolve(process.cwd(),"..");const rootEnv={...load(path.join(root,".env")),...load(path.join(root,".env.local"))};const local=load(path.join(process.cwd(),".env.local"));
const url=local.NEXT_PUBLIC_SUPABASE_URL||rootEnv.NEXT_PUBLIC_SUPABASE_URL||rootEnv.SUPABASE_URL;const token=[process.env.SUPABASE_DASHBOARD_ACCESS_TOKEN,local.SUPABASE_DASHBOARD_ACCESS_TOKEN,rootEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN].find(v=>v?.startsWith("sbp_"));
if(!url||!token)throw new Error("Supabase management configuration unavailable");const ref=new URL(url).hostname.split(".")[0];
const query=`with base as (select
 (select count(*) from public.assets) total_assets,
 (select count(*) from public.assets where lower(coalesce(mime_type,'')) like 'image/%') images,
 (select count(*) from public.assets where lower(coalesce(mime_type,'')) like 'video/%') videos,
 (select count(*) from public.assets where lower(coalesce(mime_type,'')) not like 'image/%' and lower(coalesce(mime_type,'')) not like 'video/%') documents,
 (select count(*) from public.asset_semantic_index) semantic_rows,
 (select count(*) from public.asset_embeddings) qwen_embeddings,
 (select count(*) from public.asset_visual_embeddings) visual_embeddings,
 (select count(*) from public.asset_visual_embeddings ve join public.assets a on a.id=ve.asset_id where lower(coalesce(a.mime_type,'')) like 'image/%') indexed_images,
 (select count(*) from public.asset_visual_embeddings ve join public.assets a on a.id=ve.asset_id where lower(coalesce(a.mime_type,'')) like 'video/%') indexed_videos,
 (select count(*) from public.asset_visual_index_jobs where status='FAILED') failed,
 (select count(*) from public.asset_visual_index_jobs where status='PROCESSING' and claim_expires_at<now()) stuck,
 (select count(*) from public.asset_visual_index_jobs where status='NOT_APPLICABLE' and failure_code='CORRUPT_IMAGE') corrupt_not_applicable,
 (select count(*) from public.asset_visual_index_jobs where status='NOT_APPLICABLE' and failure_code is null) documents_not_applicable,
 (select count(*) from (select asset_id,model_provider,model_name,model_version,source_fingerprint,count(*) from public.asset_visual_embeddings group by 1,2,3,4,5 having count(*)>1)d) duplicates,
 (select count(*) from public.asset_visual_embeddings where embedding_dimensions<>512 or public.vector_dims(embedding)<>512) wrong_dimensions,
 (select count(*) from public.asset_visual_embeddings where abs((1-(embedding OPERATOR(public.<=>) embedding))-1)>0.00001) invalid_self_cosine)
select *,((images+videos)-corrupt_not_applicable)-visual_embeddings missing_eligible_visuals from base`;
const response=await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`,{method:"POST",headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},body:JSON.stringify({query})});
if(!response.ok)throw new Error(`Reconciliation failed (${response.status}): ${(await response.text()).slice(0,500)}`);
const temp=path.join(tmpdir(),"kdi_semantic_visual");let tempFiles=0;if(existsSync(temp)){for(const item of readdirSync(temp)){const p=path.join(temp,item);if(statSync(p).isDirectory())tempFiles+=readdirSync(p).length;}}
const report={generated_at:new Date().toISOString(),database:await response.json(),temporary_kdi_media_files:tempFiles,external_ai_calls:0};
mkdirSync(path.join(process.cwd(),"reports"),{recursive:true});writeFileSync(path.join(process.cwd(),"reports","visual-search-final-reconciliation-2026-08-13.json"),`${JSON.stringify(report,null,2)}\n`);
console.log(JSON.stringify(report,null,2));
