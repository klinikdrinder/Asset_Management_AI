import{readFileSync,mkdirSync,writeFileSync}from"node:fs";import path from"node:path";import{performance}from"node:perf_hooks";import{createClient}from"@supabase/supabase-js";
import{interpretQuery}from"../db/query-interpreter";import{classifyRequirements}from"../db/requirement-classifier";import{expandQuery}from"../db/query-expander";import{retrieveCandidates}from"../db/candidate-retriever";import{authorizeCandidates}from"../db/candidate-authorizer";import{loadRerankingEvidence,rerankAuthorizedCandidates}from"../db/deterministic-reranker";import{applyResultCount}from"../db/result-count-controller";import{encodePhase17Queries}from"../db/phase17-query-encoder";import{buildDatabaseGroundedResponse,SupabaseGroundedResponseRepository}from"../db/database-grounded-search-response";
const root=path.resolve(import.meta.dirname,"../.."),out=path.join(root,"reports/semantic-search/rollout/phase-10"),CANARY="a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd";mkdirSync(out,{recursive:true});
function env(p:string){try{return Object.fromEntries(readFileSync(p,"utf8").replace(/^﻿/,"").split(/\r?\n/).flatMap(line=>{const m=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return{}}}
const e:any={...env(path.join(root,".env")),...env(path.join(root,".env.local")),...env(path.join(root,"dashboard/.env.local"))},url=e.SUPABASE_URL||e.NEXT_PUBLIC_SUPABASE_URL,key=e.SUPABASE_SERVICE_ROLE_KEY;if(!url||!key)throw Error("database config unavailable");const db=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}});

// Phase 10 cohort comes from the committed batch results, never from a fresh selection.
const batch=JSON.parse(readFileSync(path.join(out,"phase_10_asset_results.json"),"utf8")).assets as any[];
const ready=batch.filter(x=>x.semantic_status==="COMPLETE"&&x.search_ready===true).sort((a,b)=>a.rollout_position-b.rollout_position);
const newIds=new Set(ready.map(x=>x.asset_id));
const CONCEPT_QUERY:Record<string,string>={"person or body part visible":"a visible person","handheld object or instrument and protective gloves visible":"gloved hands holding an instrument","exposed body region visible":"an exposed body region","physical contact, holding, or manipulation visible":"physical contact","broad indoor or outdoor environment visible":"a broad indoor or outdoor environment"};
const pilots:Array<[string,string]>=[["IMG_0531.MP4","7f72217d-3839-4920-86b4-ccc33e9e3d95"],["IMG_1238.MP4","babae120-9372-42ad-b535-02a3276ea2be"],["IMG_3429.MP4","c86344e9-5b32-4d86-9205-67952d508651"],["IMG_9871.MOV","444da390-0117-4380-8c87-d7c32f2903ff"],["DSC03753.JPG","37838d30-a0ce-4f90-8cc3-c986db0aaa65"],["DSC08097.JPG","6215ad8b-12be-4a8e-bc49-f6b3dcf55c21"],["IMG_0493.MP4","64712c6a-c02c-46e9-9f73-16786109468b"],["IMG_1148.MP4","47611c6d-7923-42a4-87b6-c2a416a90f5c"],["IMG_2963.MP4","bfae6c51-5d71-47ae-a3e1-6d07092b8896"],["IMG_1160.MP4","753eb5f3-82c7-4148-a226-d5b960fd8619"]];

type Case={id:string;category:string;query:string;target?:string;expectTarget?:boolean;expectRank1?:boolean;expectCount?:number;expectMedia?:string;clinical?:boolean;unsupported?:boolean;note?:string};
const cases:Case[]=[];const add=(category:string,items:Array<[string,string,Partial<Case>?]>)=>items.forEach(([id,query,x])=>cases.push({id,category,query,...x}));

// 20.1 / 20.2 exact filename and stem retrieval for every newly SEARCH_READY asset
for(const a of ready){const stem=String(a.filename).replace(/\.[^.]+$/,"");
 cases.push({id:`p10-exact-${a.rollout_position}`,category:"exact",query:a.filename,target:a.asset_id,expectTarget:true,expectRank1:true});
 cases.push({id:`p10-stem-${a.rollout_position}`,category:"stem",query:stem,target:a.asset_id,expectTarget:true});}
// 20.3 at least one grounded semantic query per asset, built only from its own accepted observations
for(const a of ready){const concepts=(a.accepted_concepts??[]) as string[];const phrase=concepts.map(c=>CONCEPT_QUERY[c]).find(Boolean);
 if(!phrase){cases.push({id:`p10-grounded-${a.rollout_position}`,category:"grounded-none",query:a.filename,target:a.asset_id,expectTarget:true,note:"no accepted visual concept; filename identity is the only grounded retrieval path"});continue;}
 cases.push({id:`p10-grounded-${a.rollout_position}`,category:"grounded",query:`give me 30 files with ${phrase}`,target:a.asset_id,expectTarget:true});}

// Batch-level representative searches across the categories named in the phase brief.
const grounded_batch:Array<[string,string]>=[["people","give me 30 files with a visible person"],["objects","give me 30 files with gloved hands holding an instrument"],["anatomy","give me 30 files with an exposed body region"],["actions","give me 30 files showing physical contact"],["environment","give me 30 files in a broad indoor or outdoor environment"]];
for(const[k,q]of grounded_batch)cases.push({id:`batch-${k}`,category:"batch-grounded",query:q});
// Layers with no grounded truth in this batch: the correct outcome is zero new-batch matches.
const ungrounded_batch:Array<[string,string]>=[["cinematography","give me 30 files with a handheld moving camera"],["composition","give me 30 files with a close-up framing"],["transcript","give me 30 files where someone explains the treatment plan"],["ocr","give me 30 files with readable on-screen text"],["marketing","give me 30 files approved for marketing use"]];
for(const[k,q]of ungrounded_batch)cases.push({id:`batch-${k}`,category:"batch-ungrounded",query:q,note:"no accepted truth for this layer in the Phase 10 batch"});

// 21 clinical false-positive regression against the expanded index
for(const q of["surgery","procedure","treatment","hair transplant","FUE","implantation","extraction"])cases.push({id:`clinical-${q.replace(/\s+/g,"-")}`,category:"clinical",query:q,clinical:true});
// 22 original-11 regression
for(const[f,id]of pilots)cases.push({id:`pilot-${f}`,category:"pilot",query:f,target:id,expectTarget:true,expectRank1:true});
cases.push({id:"canary-IMG_2951.MP4",category:"canary",query:"IMG_2951.MP4",target:CANARY,expectTarget:true,expectRank1:true});
cases.push({id:"canary-grounded",category:"canary",query:"give me 30 files with gloved hands holding an instrument",target:CANARY,expectTarget:true});
// 23 result-count and query-intelligence smoke tests
for(const n of[1,3,5,7,10])cases.push({id:`count-${n}`,category:"count",query:n===7?"give me 7 files":n===10?"show me 10 videos":`give me ${n} files with a visible person`,expectCount:n});
add("number",[["age1","man around 30",{expectCount:5}],["age2","person in his 30s",{expectCount:5}],["age3","30-year-old",{expectCount:5}],["age4","give me 30 results",{expectCount:30}]]);
add("media",[["media-video","show me 30 videos with a visible person",{expectMedia:"VIDEO"}],["media-image","show me 30 images with a visible person",{expectMedia:"IMAGE"}]]);
add("negative",[["neg1","give me 30 files with a visible person but without gloved hands"],["neg2","give me 30 files with an exposed body region but not physical contact"]]);
add("multi",[["multi1","give me 30 files with a visible person and gloved hands"],["multi2","give me 30 files with an exposed body region and physical contact"]]);
for(const q of["food","car","landscape","animal","airplane"])cases.push({id:`unsupported-${q}`,category:"unsupported",query:q,unsupported:true});

const users=await db.from("app_users").select("user_id").eq("is_active",true).limit(1);if(users.error||!users.data?.[0])throw users.error??Error("active user unavailable");const userId=String(users.data[0].user_id);
const uniqueQueries=[...new Set(cases.map(x=>x.query))];const vectors=await encodePhase17Queries(uniqueQueries);const vectorBy=new Map(uniqueQueries.map((q,i)=>[q,vectors[i]]));
const CLINICAL=/surgery|procedure|treatment|hair transplant|fue|implantation|extraction|graft|prp|laser|injection/i;

async function run(c:Case){const started=performance.now(),p0=performance.now(),plan=await interpretQuery(c.query),parser_ms=performance.now()-p0,req=classifyRequirements(plan),expanded=expandQuery(plan,req),rv=vectorBy.get(c.query)!,r0=performance.now(),retrieved=await retrieveCandidates(db,{queryPlan:plan,requirementPlan:req,expandedQueryPlan:expanded,queryVectors:rv,requestedCount:plan.result_request.effective_count}),retrieval_ms=performance.now()-r0,a0=performance.now(),authorized=await authorizeCandidates(db,retrieved,userId),authorization_ms=performance.now()-a0,evidence=await loadRerankingEvidence(db,authorized as any),k0=performance.now(),ranked=rerankAuthorizedCandidates(authorized as any,req,expanded,evidence,plan.result_request.effective_count),ranking_ms=performance.now()-k0,controlled=applyResultCount(ranked.candidates,plan.result_request,{isAuthorized:(x:any)=>x.authorization?.discover===true,isEligible:(x:any)=>x.phase19.eligible===true}),response=await buildDatabaseGroundedResponse({query:c.query,userId,count:controlled.count,candidates:controlled.candidates.map((x:any)=>({asset_id:x.asset_id,score:x.phase19.normalizedScore}))},new SupabaseGroundedResponseRepository(db));
 const ids=controlled.candidates.map((x:any)=>x.asset_id),idx=c.target?ids.indexOf(c.target):-1;
 const ranking=controlled.candidates.map((x:any,i:number)=>({rank:i+1,asset_id:x.asset_id,filename:x.filename,score:x.phase19.normalizedScore,eligible:x.phase19.eligible,phase10_batch:newIds.has(x.asset_id)}));
 const newMatches=ranking.filter(r=>r.phase10_batch);
 const actualCount=controlled.count.effective_count;
 const ageSafe=c.category!=="number"||c.id==="age4"?true:plan.result_request.requested_count===null;
 const passTarget=c.expectTarget===undefined||(idx>=0);
 const passRank1=!c.expectRank1||idx===0;
 const passCount=c.expectCount===undefined||actualCount===c.expectCount;
 const passMedia=!c.expectMedia||controlled.candidates.every((x:any)=>String(evidence.metadata[x.asset_id]?.mimeType??"").toUpperCase().startsWith(c.expectMedia!));
 // Clinical leakage is judged per newly indexed asset: none of them carries a supported clinical concept.
 const leaked=c.clinical?newMatches.map(r=>r.asset_id):[];
 const unsafeReasons=(response.results??[]).filter((x:any)=>newIds.has(x.asset_id)&&CLINICAL.test(String(x.match_reason??""))).map((x:any)=>({asset_id:x.asset_id,match_reason:x.match_reason}));
 const passUngrounded=c.category!=="batch-ungrounded"||newMatches.length===0;
 const passClinical=!c.clinical||leaked.length===0;
 const passUnsupported=!c.unsupported||newMatches.length===0;
 return{...c,pass:passTarget&&passRank1&&passCount&&passMedia&&ageSafe&&passClinical&&passUngrounded&&passUnsupported&&unsafeReasons.length===0,parsed_intent:plan.intent,requested_count:plan.result_request.requested_count,effective_count:actualCount,requirement_classes:[...new Set(["response_controls","hard_constraints","hard_exclusions","strong_requirements","preferences","negative_preferences","context","unresolved","conflicts"].flatMap(b=>((req as any)[b]??[]).map((r:any)=>r.classification)))],expanded_terms:(expanded.requirements??[]).flatMap((r:any)=>r.expansions??[]).length,candidate_count:retrieved.candidates.length,authorized_count:authorized.candidates.length,returned_count:controlled.candidates.length,target_returned:c.target?idx>=0:null,target_rank:idx>=0?idx+1:null,phase10_matches:newMatches,phase10_match_count:newMatches.length,clinical_leaked_assets:leaked,unsafe_match_reasons:unsafeReasons,ranking,latency_ms:{parser:parser_ms,retrieval:retrieval_ms,authorization:authorization_ms,ranking:ranking_ms,total:performance.now()-started}}}

const results:any[]=[];for(const c of cases){results.push(await run(c));const r=results.at(-1)!;console.log(`${c.id} ${r.pass?"PASS":"FAIL"} returned=${r.returned_count} rank=${r.target_rank??"-"}`)}
const repeatQueries=["give me 30 files with a visible person","surgery","IMG_2951.MP4"];const det:any[]=[];
for(const q of repeatQueries){const base=cases.find(x=>x.query===q)!;const rows:any[]=[];for(let i=0;i<3;i++)rows.push(await run({...base,id:`det-${i}`}));det.push({query:q,pass:rows.every((x,i)=>i===0||JSON.stringify(x.ranking.map((y:any)=>[y.asset_id,y.score]))===JSON.stringify(rows[0].ranking.map((y:any)=>[y.asset_id,y.score]))),orders:rows.map(x=>x.ranking.map((y:any)=>y.asset_id))})}
const report={generated_at:new Date().toISOString(),phase:10,status:results.every(x=>x.pass)&&det.every(x=>x.pass)?"PASS":"FAIL",cohort:ready.map(x=>({rollout_position:x.rollout_position,asset_id:x.asset_id,filename:x.filename})),cases:results,determinism:det,external_inference:0,semantic_media_analysis:0};
writeFileSync(path.join(out,"phase_10_raw_benchmark.json"),JSON.stringify(report,null,2)+"\n");
console.log(JSON.stringify({status:report.status,total:results.length,passed:results.filter(x=>x.pass).length,failed:results.filter(x=>!x.pass).map(x=>x.id),determinism:det.every(x=>x.pass)}));
if(report.status!=="PASS")process.exitCode=1;
