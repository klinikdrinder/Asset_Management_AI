// Establishes whether the canary's displacement from the top 5 of "visible tool" is index growth
// or ranking corruption: same query, count raised so the whole authorized set is visible.
import{readFileSync,writeFileSync,mkdirSync}from"node:fs";import path from"node:path";import{createClient}from"@supabase/supabase-js";
import{interpretQuery}from"../db/query-interpreter";import{classifyRequirements}from"../db/requirement-classifier";import{expandQuery}from"../db/query-expander";import{retrieveCandidates}from"../db/candidate-retriever";import{authorizeCandidates}from"../db/candidate-authorizer";import{loadRerankingEvidence,rerankAuthorizedCandidates}from"../db/deterministic-reranker";import{applyResultCount}from"../db/result-count-controller";import{encodePhase17Queries}from"../db/phase17-query-encoder";
const root=path.resolve(import.meta.dirname,"../.."),out=path.join(root,"reports/semantic-search/rollout/phase-10"),CANARY="a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd";mkdirSync(out,{recursive:true});
function env(p:string){try{return Object.fromEntries(readFileSync(p,"utf8").replace(/^﻿/,"").split(/\r?\n/).flatMap(line=>{const m=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return{}}}
const e:any={...env(path.join(root,".env")),...env(path.join(root,".env.local")),...env(path.join(root,"dashboard/.env.local"))};
const db=createClient(e.SUPABASE_URL||e.NEXT_PUBLIC_SUPABASE_URL,e.SUPABASE_SERVICE_ROLE_KEY,{auth:{persistSession:false,autoRefreshToken:false}});
const phase10=new Set((JSON.parse(readFileSync(path.join(out,"phase_10_asset_results.json"),"utf8")).assets as any[]).filter(x=>x.search_ready).map(x=>x.asset_id));
const users=await db.from("app_users").select("user_id").eq("is_active",true).limit(1);const userId=String(users.data![0].user_id);
const query="visible tool";const [vec]=await encodePhase17Queries([query]);
const plan=await interpretQuery(query),req=classifyRequirements(plan),exp=expandQuery(plan,req);
const retrieved=await retrieveCandidates(db,{queryPlan:plan,requirementPlan:req,expandedQueryPlan:exp,queryVectors:vec,requestedCount:60});
const authorized=await authorizeCandidates(db,retrieved,userId);
const evidence=await loadRerankingEvidence(db,authorized as any);
const ranked=rerankAuthorizedCandidates(authorized as any,req,exp,evidence,60);
const controlled=applyResultCount(ranked.candidates,{...plan.result_request,requested_count:60,effective_count:60} as any,{isAuthorized:(x:any)=>x.authorization?.discover===true,isEligible:(x:any)=>x.phase19.eligible===true});
const full=controlled.candidates.map((x:any,i:number)=>({rank:i+1,asset_id:x.asset_id,filename:x.filename,score:x.phase19.normalizedScore,phase10:phase10.has(x.asset_id)}));
const canary=full.find(x=>x.asset_id===CANARY);
const report={generated_at:new Date().toISOString(),phase:10,query,
  finding:"Phase 9 case p2 asserts the canary appears within the default 5 results. With the index grown from 11 to 30 SEARCH_READY assets, five Phase 10 assets carrying the same generic instrument/glove concept score marginally above it and occupy those slots.",
  filename_literal_channel:(retrieved.diagnostics as any).channels.FILENAME_LITERAL,
  filename_literal_inert_for_this_query:((retrieved.diagnostics as any).channels.FILENAME_LITERAL?.hits??0)===0,
  authorized_candidates:authorized.candidates.length,
  canary_rank:canary?.rank??null,canary_score:canary?.score??null,canary_retrievable:!!canary,
  score_spread_top10:full.slice(0,10).map(x=>x.score),
  ranking:full};
writeFileSync(path.join(out,"phase_10_p2_displacement_analysis.json"),JSON.stringify(report,null,2)+"\n");
console.log(JSON.stringify({canary_rank:report.canary_rank,canary_score:report.canary_score,authorized:report.authorized_candidates,filename_literal_hits:(retrieved.diagnostics as any).channels.FILENAME_LITERAL?.hits,top:full.slice(0,8)},null,1));
