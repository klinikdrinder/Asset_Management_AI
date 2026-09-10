import{readFileSync}from"node:fs";import path from"node:path";import{createClient}from"@supabase/supabase-js";
import{interpretQuery}from"../db/query-interpreter";import{classifyRequirements}from"../db/requirement-classifier";import{expandQuery}from"../db/query-expander";import{retrieveCandidates}from"../db/candidate-retriever";import{encodePhase17Queries}from"../db/phase17-query-encoder";
const root=path.resolve(import.meta.dirname,"../..");
function env(p:string){try{return Object.fromEntries(readFileSync(p,"utf8").replace(/^﻿/,"").split(/\r?\n/).flatMap(line=>{const m=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return{}}}
const e:any={...env(path.join(root,".env")),...env(path.join(root,".env.local")),...env(path.join(root,"dashboard/.env.local"))};
const db=createClient(e.SUPABASE_URL||e.NEXT_PUBLIC_SUPABASE_URL,e.SUPABASE_SERVICE_ROLE_KEY,{auth:{persistSession:false,autoRefreshToken:false}});
const queries=["25.01 (18).jpeg","25.01 (18)","IMG_2933.MP4","25.01","2 MONTH 22.03 (11).jpeg"];
const vecs=await encodePhase17Queries(queries);
for(let i=0;i<queries.length;i++){const q=queries[i];const plan=await interpretQuery(q);const req=classifyRequirements(plan);const exp=expandQuery(plan,req);
 const ret=await retrieveCandidates(db,{queryPlan:plan,requirementPlan:req,expandedQueryPlan:exp,queryVectors:vecs[i],requestedCount:plan.result_request.effective_count});
 console.log(JSON.stringify({query:q,intent:plan.intent,requested_count:plan.result_request.requested_count,effective_count:plan.result_request.effective_count,
  filename_fields:Object.entries(plan).filter(([k,v])=>/file|name|literal|text/i.test(k)&&v).map(([k,v])=>[k,v]),
  literal_search_terms:exp.literal_search_terms,
  requirement_fields:["response_controls","hard_constraints","hard_exclusions","strong_requirements","preferences","negative_preferences","context","unresolved","conflicts"].flatMap(b=>((req as any)[b]??[]).map((r:any)=>({bucket:b,field:r.field,value:r.value,classification:r.classification,raw:r.raw_text}))),
  candidates:ret.candidates.length,channels:ret.diagnostics},null,1))}
