import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";

function envFile(file:string){try{return Object.fromEntries(readFileSync(file,"utf8").replace(/^\uFEFF/,"").split(/\r?\n/).flatMap(line=>{const m=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return {}}}
const root=path.resolve(process.cwd(),".."), local=envFile(path.join(process.cwd(),".env.local")), parent={...envFile(path.join(root,".env")),...envFile(path.join(root,".env.local"))};
const url=local.NEXT_PUBLIC_SUPABASE_URL||parent.NEXT_PUBLIC_SUPABASE_URL;const token=[parent.SUPABASE_DASHBOARD_ACCESS_TOKEN,local.SUPABASE_DASHBOARD_ACCESS_TOKEN].find(v=>v?.startsWith("sbp_"));
if(!url||!token)throw new Error("Supabase management configuration unavailable");const ref=new URL(url).hostname.split(".")[0];
async function sql<T=unknown>(query:string):Promise<T>{const response=await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`,{method:"POST",headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},body:JSON.stringify({query})});if(!response.ok)throw new Error(`SQL failed ${response.status}: ${(await response.text()).slice(0,1000)}`);return response.json() as Promise<T>}
const out=path.join(process.cwd(),"reports","semantic-search","database");mkdirSync(out,{recursive:true});const stamp=new Date().toISOString().replace(/[:.]/g,"-");
const label=process.argv[2]||"pre_reconciliation";
const countsSql=`select t.table_name,(xpath('/row/c/text()',query_to_xml(format('select count(*) c from public.%I',t.table_name),false,true,'')))[1]::text::bigint row_count from (values ${["assets","asset_access_control","asset_sources","asset_destinations","source_files","asset_visual_embeddings","asset_embeddings","asset_ai_profiles","asset_search_documents","scene_search_documents","asset_scenes","asset_keyframes","asset_transcript_chunks","ocr_observations","scene_narratives","app_users"].map(x=>`('${x}')`).join(",")})t(table_name) order by 1`;
const schemaSql=`select jsonb_build_object(
 'tables',(select jsonb_agg(x order by schema_name,object_name) from (select n.nspname schema_name,c.relname object_name,c.relkind,c.relrowsecurity,c.relforcerowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('public','private') and c.relkind in('r','p','v','m'))x),
 'columns',(select jsonb_agg(x order by table_schema,table_name,ordinal_position) from (select table_schema,table_name,column_name,ordinal_position,data_type,udt_name,is_nullable,column_default from information_schema.columns where table_schema in('public','private'))x),
 'constraints',(select jsonb_agg(x order by schema_name,table_name,constraint_name) from (select n.nspname schema_name,c.relname table_name,k.conname constraint_name,k.contype,pg_get_constraintdef(k.oid,true) definition from pg_constraint k join pg_class c on c.oid=k.conrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname in('public','private'))x),
 'indexes',(select jsonb_agg(x order by schemaname,tablename,indexname) from (select schemaname,tablename,indexname,indexdef from pg_indexes where schemaname in('public','private'))x),
 'functions',(select jsonb_agg(x order by schema_name,function_name,arguments) from (select n.nspname schema_name,p.proname function_name,pg_get_function_identity_arguments(p.oid) arguments,pg_get_functiondef(p.oid) definition,coalesce(array_to_string(p.proacl,','),'DEFAULT') acl from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname in('public','private') and p.prokind in('f','p'))x),
 'triggers',(select jsonb_agg(x order by schema_name,table_name,trigger_name) from (select n.nspname schema_name,c.relname table_name,t.tgname trigger_name,pg_get_triggerdef(t.oid,true) definition from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname in('public','private') and not t.tgisinternal)x),
 'policies',(select jsonb_agg(to_jsonb(x) order by schemaname,tablename,policyname) from pg_policies x where schemaname in('public','private')),
 'extensions',(select jsonb_agg(jsonb_build_object('name',e.extname,'version',e.extversion,'schema',n.nspname) order by e.extname) from pg_extension e join pg_namespace n on n.oid=e.extnamespace)
) snapshot`;
const [counts,migrations,schema,manualChecks,semanticValidation]=await Promise.all([
 sql(countsSql),sql(`select version,name,created_by,idempotency_key,array_length(statements,1) statement_count from supabase_migrations.schema_migrations order by version`),sql(schemaSql),
 sql(`select
  to_regprocedure('public.complete_semantic_index_atomically(uuid,text,jsonb,jsonb)') is not null atomic_semantic_present,
  to_regclass('public.asset_visual_embeddings') is not null and to_regclass('public.asset_visual_index_jobs') is not null visual_schema_present,
  to_regclass('public.admin_accounts') is not null and to_regclass('public.admin_sessions') is not null and to_regclass('public.admin_auth_audit') is not null admin_schema_present,
  to_regclass('public.user_invitations') is not null and to_regclass('public.user_management_audit') is not null user_management_present,
  not exists(select 1 from public.asset_visual_index_jobs j join public.assets a on a.id=j.asset_id where j.status='FAILED' and a.file_name in('step14-retry.png','step14-unique.png') and a.mime_type='image/png' and a.size_bytes between 1 and 100) corrupt_fixture_migration_effect_present`),
 sql(`select
  (select count(*) from public.semantic_layer_definitions) layer_definitions,
  (select count(*) from public.semantic_layer_definitions where active and spec_version='semantic_index_v1') active_v1_layers,
  (select array_agg(layer_id order by layer_number) from public.semantic_layer_definitions) ordered_layer_ids,
  (select count(*) from public.semantic_review_decisions) human_review_decisions,
  (select count(*) from public.gold_standard_assets where status='SIGNED_OFF') signed_gold_assets,
  (select count(*) from public.semantic_embeddings) new_semantic_embeddings,
  (select count(*) from public.semantic_analysis_runs) semantic_analysis_runs,
  (select count(*) from public.semantic_assertions) semantic_assertions,
  (select count(*) from public.semantic_assertion_evidence) semantic_evidence,
  (select count(*) from public.asset_events) asset_events,
  (select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in('semantic_analysis_runs','asset_semantic_layers','asset_events','semantic_assertions','semantic_assertion_evidence','semantic_narratives','narrative_claims','narrative_claim_evidence','semantic_review_sessions','semantic_review_decisions','semantic_review_revisions','gold_standard_sets','gold_standard_assets','gold_standard_assertions','asset_search_concepts_v2','search_document_builds','semantic_embeddings')) expected_tables_present,
  (select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in('effective_semantic_assertions','current_asset_semantic_state') and c.relkind='v' and coalesce(c.reloptions,'{}')@>array['security_invoker=true']) security_invoker_views,
  (select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in('semantic_analysis_runs','asset_semantic_layers','asset_events','semantic_assertions','semantic_assertion_evidence','semantic_narratives','narrative_claims','narrative_claim_evidence','semantic_review_sessions','semantic_review_decisions','semantic_review_revisions','gold_standard_sets','gold_standard_assets','gold_standard_assertions','asset_search_concepts_v2','search_document_builds','semantic_embeddings') and c.relrowsecurity) rls_tables`)
]);
const snapshot=(schema as Array<{snapshot:unknown}>)[0].snapshot;const schemaFingerprint=createHash("sha256").update(JSON.stringify(snapshot)).digest("hex");
const repoFiles=readdirSync(path.join(root,"supabase","migrations")).filter(x=>x.endsWith('.sql')).sort().map(file=>{const content=readFileSync(path.join(root,"supabase","migrations",file),"utf8"),m=file.match(/^(\d+)_?(.*)\.sql$/)!;const normalized=content.replace(/--[^\r\n]*/g,'').replace(/\/\*[\s\S]*?\*\//g,'').replace(/\s+/g,' ').replace(/\s*;\s*/g,';').trim().toLowerCase();return{filename:file,version:m[1],name:m[2],sha256:createHash('sha256').update(content).digest('hex'),sql_fingerprint:createHash('sha256').update(normalized).digest('hex'),bytes:Buffer.byteLength(content),objects:[...content.matchAll(/(?:create|alter|drop)\s+(?:or\s+replace\s+)?(?:table|view|function|index|trigger|policy)\s+(?:if\s+(?:not\s+)?exists\s+)?([^\s(;]+)/ig)].map(x=>x[1])}});
const payload={generated_at:new Date().toISOString(),project_ref:ref,counts,migrations,schema_fingerprint:schemaFingerprint,manual_migration_effects:manualChecks,semantic_validation:semanticValidation,schema:snapshot};
writeFileSync(path.join(out,`phase10_reconciliation_freeze_${stamp}.json`),JSON.stringify(payload,null,2)+'\n');
writeFileSync(path.join(out,`production_counts_${label}.json`),JSON.stringify({generated_at:payload.generated_at,counts},null,2)+'\n');
writeFileSync(path.join(out,`schema_fingerprint_${label}.json`),JSON.stringify({generated_at:payload.generated_at,sha256:schemaFingerprint,snapshot},null,2)+'\n');
writeFileSync(path.join(out,`migration_history_${label}.json`),JSON.stringify({generated_at:payload.generated_at,migrations},null,2)+'\n');
writeFileSync(path.join(out,'live_migration_inventory_final.json'),JSON.stringify({generated_at:payload.generated_at,migrations},null,2)+'\n');
writeFileSync(path.join(out,'repository_migration_inventory_final.json'),JSON.stringify({generated_at:payload.generated_at,migrations:repoFiles},null,2)+'\n');
console.log(JSON.stringify({generated_at:payload.generated_at,schema_fingerprint:schemaFingerprint,counts,migration_count:(migrations as unknown[]).length,repository_count:repoFiles.length,manualChecks,semanticValidation},null,2));
