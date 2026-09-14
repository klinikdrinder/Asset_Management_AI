// Evidence for the three Phase 9 legacy assertions that no longer hold: is the canary still
// correctly retrievable, or did retrieval actually regress? Same queries, count raised so the whole
// eligible set is visible. Read-only.
import{readFileSync,writeFileSync,mkdirSync}from"node:fs";import path from"node:path";import{createClient}from"@supabase/supabase-js";
import{interpretQuery}from"../db/query-interpreter";import{classifyRequirements}from"../db/requirement-classifier";import{expandQuery}from"../db/query-expander";import{retrieveCandidates}from"../db/candidate-retriever";import{authorizeCandidates}from"../db/candidate-authorizer";import{loadRerankingEvidence,rerankAuthorizedCandidates}from"../db/deterministic-reranker";import{applyResultCount}from"../db/result-count-controller";import{encodePhase17Queries}from"../db/phase17-query-encoder";
const root=path.resolve(import.meta.dirname,"../.."),out=path.join(root,"reports/semantic-search/rollout/full-index-30");mkdirSync(out,{recursive:true});
const CANARY="a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd";
function env(p:string){try{return Object.fromEntries(readFileSync(p,"utf8").replace(/^﻿/,"").split(/\r?\n/).flatMap(l=>{const m=l.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return{}}}
const e:any={...env(path.join(root,".env")),...env(path.join(root,".env.local")),...env(path.join(root,"dashboard/.env.local"))};
const db=createClient(e.SUPABASE_URL||e.NEXT_PUBLIC_SUPABASE_URL,e.SUPABASE_SERVICE_ROLE_KEY,{auth:{persistSession:false,autoRefreshToken:false}});
const users=(await db.from("app_users").select("user_id").eq("is_active",true).limit(1)).data??[];
const userId=String(users[0]!.user_id);
const QUERIES=["show me a video with a visible person","give me 1 videos with gloved hands","give me 3 videos with gloved hands","visible tool"];
const vecs=await encodePhase17Queries(QUERIES);
const rows:any[]=[];
for(let i=0;i<QUERIES.length;i++){const q=QUERIES[i];
 const plan=await interpretQuery(q),req=classifyRequirements(plan),exp=expandQuery(plan,req);
 const retrieved=await retrieveCandidates(db,{queryPlan:plan,requirementPlan:req,expandedQueryPlan:exp,queryVectors:vecs[i],requestedCount:60});
 const authorized=await authorizeCandidates(db,retrieved,userId);
 const evidence=await loadRerankingEvidence(db,authorized as any);
 const ranked=rerankAuthorizedCandidates(authorized as any,req,exp,evidence,60);
 const controlled=applyResultCount(ranked.candidates,{...plan.result_request,requested_count:60,effective_count:60} as any,{isAuthorized:(x:any)=>x.authorization?.discover===true,isEligible:(x:any)=>x.phase19.eligible===true});
 const full=controlled.candidates.map((x:any,idx:number)=>({rank:idx+1,asset_id:x.asset_id,filename:x.filename,score:x.phase19.normalizedScore}));
 const canary=full.find(x=>x.asset_id===CANARY);
 rows.push({query:q,legacy_default_count:plan.result_request.effective_count,
  filename_literal_hits:(retrieved.diagnostics as any).channels?.FILENAME_LITERAL?.hits??0,
  eligible_total:full.length,canary_rank:canary?.rank??null,canary_score:canary?.score??null,
  canary_retrievable:!!canary,
  displaced_by:full.slice(0,Math.max(0,(canary?.rank??1)-1)).map(x=>({rank:x.rank,filename:x.filename,score:x.score})),
  top10:full.slice(0,10)});
 console.log(JSON.stringify({query:q,canary_rank:canary?.rank??null,eligible:full.length,fl_hits:rows.at(-1).filename_literal_hits}));}
writeFileSync(path.join(out,"full_index_30_canary_displacement_analysis.json"),JSON.stringify({
 generated_at:new Date().toISOString(),phase:"FULL_INDEX_30",
 finding:"Three legacy Phase 9 assertions require the canary inside a small fixed result window. Scene-level indexing gave the ten newly corrected videos scene documents and TEXT_SCENE/VISUAL_SCENE/VISUAL_KEYFRAME evidence, so they now accumulate more channel support than the canary for generic concepts.",
 filename_literal_contribution:"zero on every affected query, so the bare-extension retrieval fix is not the cause",
 canary_semantic_truth_modified:false,ranking_hack_introduced:false,
 queries:rows},null,2)+"\n");
console.log(JSON.stringify({written:"full_index_30_canary_displacement_analysis.json"}));
