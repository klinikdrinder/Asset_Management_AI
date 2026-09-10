// FULL-INDEX-30 search acceptance. Exercises the certified production chain against the corrected
// cohort, including scene-level retrieval. Every expectation is derived from committed semantic
// truth; nothing is invented. Query vocabulary is NOT expanded here (that is the next phase).
import{readFileSync,writeFileSync,mkdirSync}from"node:fs";import path from"node:path";import{performance}from"node:perf_hooks";import{createClient}from"@supabase/supabase-js";
import{interpretQuery}from"../db/query-interpreter";import{classifyRequirements}from"../db/requirement-classifier";import{expandQuery}from"../db/query-expander";import{retrieveCandidates}from"../db/candidate-retriever";import{authorizeCandidates}from"../db/candidate-authorizer";import{loadRerankingEvidence,rerankAuthorizedCandidates}from"../db/deterministic-reranker";import{applyResultCount}from"../db/result-count-controller";import{encodePhase17Queries}from"../db/phase17-query-encoder";import{buildDatabaseGroundedResponse,SupabaseGroundedResponseRepository}from"../db/database-grounded-search-response";
const root=path.resolve(import.meta.dirname,"../.."),out=path.join(root,"reports/semantic-search/rollout/full-index-30");mkdirSync(out,{recursive:true});
function env(p:string){try{return Object.fromEntries(readFileSync(p,"utf8").replace(/^﻿/,"").split(/\r?\n/).flatMap(l=>{const m=l.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return{}}}
const e:any={...env(path.join(root,".env")),...env(path.join(root,".env.local")),...env(path.join(root,"dashboard/.env.local"))};
const db=createClient(e.SUPABASE_URL||e.NEXT_PUBLIC_SUPABASE_URL,e.SUPABASE_SERVICE_ROLE_KEY,{auth:{persistSession:false,autoRefreshToken:false}});

const layerRows=(await db.from("asset_semantic_layers").select("asset_id,processing_status").eq("active",true)).data??[];
const per=new Map<string,{n:number;c:number}>();
for(const r of layerRows){const v=per.get(r.asset_id)??{n:0,c:0};v.n++;if(r.processing_status==="COMPLETE")v.c++;per.set(r.asset_id,v)}
const cohortIds=[...per.entries()].filter(([,v])=>v.n===18&&v.c===18).map(([k])=>k);
const cohort=new Set(cohortIds);
const assetRows=(await db.from("assets").select("id,file_name,mime_type").in("id",cohortIds)).data??[];
const assetById=new Map(assetRows.map(a=>[a.id as string,a]));
const assertRows=(await db.from("semantic_assertions").select("asset_id,scene_id,canonical_concept_code,semantic_state").in("asset_id",cohortIds).eq("active",true)).data??[];
const observed=new Map<string,Set<string>>();const assetConcepts=new Map<string,string[]>();
const sceneConcepts=new Map<string,string[]>();
for(const r of assertRows){if(r.semantic_state!=="OBSERVED")continue;
 if(!observed.has(r.canonical_concept_code))observed.set(r.canonical_concept_code,new Set());
 observed.get(r.canonical_concept_code)!.add(r.asset_id);
 assetConcepts.set(r.asset_id,[...(assetConcepts.get(r.asset_id)??[]),r.canonical_concept_code]);
 if(r.scene_id)sceneConcepts.set(r.scene_id,[...(sceneConcepts.get(r.scene_id)??[]),r.canonical_concept_code])}
const scenes=((await db.from("asset_scenes").select("id,asset_id,scene_index,start_seconds,end_seconds,short_description").eq("canonical_active",true).in("asset_id",cohortIds)).data)??[];
const searchReady=new Set(((await db.from("asset_search_documents").select("asset_id,build_status").eq("build_status","READY")).data??[]).map(r=>r.asset_id as string));
const docText=new Map((((await db.from("asset_search_documents").select("asset_id,searchable_text").in("asset_id",cohortIds)).data)??[]).map(r=>[r.asset_id as string,String(r.searchable_text??"").toLowerCase()]));

const PHRASE:Record<string,string>={
 PERSON_OR_BODY_PART_VISIBLE:"a visible person",
 HANDHELD_INSTRUMENT_AND_PROTECTIVE_GLOVES_VISIBLE:"gloved hands holding an instrument",
 EXPOSED_BODY_REGION_VISIBLE:"an exposed body region",
 PHYSICAL_CONTACT_HOLDING_OR_MANIPULATION_VISIBLE:"physical contact",
 BROAD_ENVIRONMENT_VISIBLE:"a broad indoor or outdoor environment",
 CLINICIAN:"a clinician",PATIENT:"a patient",PATIENT_RECLINING:"a reclining patient",
 CLINICIAN_GLOVED:"a gloved clinician",TREATMENT_ROOM:"a treatment room",
 SCALP:"a scalp",FACE:"a face",FRONTAL_SCALP:"a frontal scalp",NECK:"a neck",
 INJECTING:"injecting",ADULT_PRESENTATION:"an adult",
 CLINICIAN_TREATS_PATIENT:"a clinician treating a patient"};
const CLINICAL_LICENSE:Record<string,string[]>={
 "hair transplant":["HAIR_TRANSPLANT","HAIR_TRANSPLANT_FUE","HAIR_TRANSPLANT_PROCEDURE_CONTENT","FUE_IMPLANTATION"],
 "fue":["HAIR_TRANSPLANT_FUE","FUE_IMPLANTATION"],"implantation":["FUE_IMPLANTATION","IMPLANTING_GRAFTS"],
 "graft":["FUE_IMPLANTATION","IMPLANTING_GRAFTS","RECIPIENT_REGION"],"extraction":[],"prp":[],"laser":[],"surgery":[],
 "injection":["INJECTABLES","INJECTING","HOLDING_SYRINGE","VISIBLE_INJECTION_AT_LOWER_FACE","VISIBLE_INJECTION_AT_NECK"],
 "procedure":["PROCEDURE_CONTENT","PROCEDURE_PREPARATION_CONTENT","VISIBLE_RECIPIENT_AREA_PROCEDURE","HAIR_TRANSPLANT_PROCEDURE_CONTENT","OPERATING_ROOM"],
 "treatment":["TREATMENT_ROOM","PATIENT_POSITIONED_IN_TREATMENT_CHAIR","CLINICIAN_TREATS_PATIENT","SCALP_UNDER_ACTIVE_CLINICAL_ATTENTION","FACE_UNDER_ACTIVE_CLINICAL_ATTENTION","NECK_TREATMENT_AREA_DOMINANT","TREATMENT_AREA_PARTIALLY_VISIBLE","TOOL_VISIBLE_NEAR_TREATMENT_AREA"]};
const CLINICAL_RE=/surgery|procedure|treatment|hair transplant|fue|implantation|extraction|graft|prp|laser|injection/i;
function licensed(a:string,t:string){return (CLINICAL_LICENSE[t]??[]).some(c=>(assetConcepts.get(a)??[]).includes(c))}
function queryTerm(q:string){const m=q.toLowerCase().match(/hair transplant|implantation|extraction|procedure|treatment|surgery|injection|graft|fue|prp|laser/);return m?m[0]:null}
function affirmative(r:string){return String(r??"").split(/(?:^|\.\s*)(?:the specific|no )/i)[0]}

type Case={id:string;category:string;query:string;target?:string;expectTarget?:boolean;expectRank1?:boolean;
 expectCount?:number;expectMedia?:string;expectZero?:boolean;relevant?:string[];clinical?:boolean;informational?:boolean;note?:string};
const cases:Case[]=[];
const ordered=[...cohortIds].sort((a,b)=>String(assetById.get(a)?.file_name).localeCompare(String(assetById.get(b)?.file_name)));

// filename identity across the whole cohort
for(const id of ordered){const f=String(assetById.get(id)!.file_name);const stem=f.replace(/\.[^.]+$/,"");
 cases.push({id:`fn:${f}`,category:"filename",query:f,target:id,expectTarget:true,expectRank1:true});
 if(stem!==f)cases.push({id:`stem:${f}`,category:"filename-stem",query:stem,target:id,expectTarget:true})}
// asset-level grounded retrieval
for(const id of ordered){const cs=(assetConcepts.get(id)??[]).filter(x=>PHRASE[x]);
 if(!cs.length)continue;
 const pick=cs.sort((a,b)=>observed.get(a)!.size-observed.get(b)!.size)[0];
 cases.push({id:`grounded:${assetById.get(id)!.file_name}`,category:"grounded",
  query:`give me 30 files with ${PHRASE[pick]}`,target:id,expectTarget:true,relevant:[...observed.get(pick)!]})}
// SCENE-SPECIFIC retrieval: a query built from one scene's own observations must reach its asset
for(const s of scenes){const cs=(sceneConcepts.get(s.id)??[]).filter(x=>PHRASE[x]);
 if(!cs.length)continue;
 const pick=cs.sort((a,b)=>observed.get(a)!.size-observed.get(b)!.size)[0];
 cases.push({id:`scene:${assetById.get(s.asset_id)?.file_name}#${s.scene_index}`,category:"scene-specific",
  query:`give me 30 files with ${PHRASE[pick]}`,target:s.asset_id,expectTarget:true,
  relevant:[...observed.get(pick)!],note:`scene ${s.scene_index} ${s.start_seconds}-${s.end_seconds}s`})}
// paraphrase (measured, informational — query vocabulary is deliberately not expanded in this phase)
for(const[id,q,c]of [["para-person","give me 30 files showing somebody","PERSON_OR_BODY_PART_VISIBLE"],
 ["para-gloves","give me 30 files with hands in surgical gloves","HANDHELD_INSTRUMENT_AND_PROTECTIVE_GLOVES_VISIBLE"],
 ["para-skin","give me 30 files where skin is uncovered","EXPOSED_BODY_REGION_VISIBLE"]] as Array<[string,string,string]>)
 cases.push({id,category:"paraphrase",query:q,relevant:[...(observed.get(c)??[])],informational:true});
// multi-concept + filters + exclusions
cases.push({id:"multi-1",category:"multi-concept",query:"give me 30 files with a visible person and physical contact"});
cases.push({id:"multi-2",category:"multi-concept",query:"give me 30 files with an exposed body region and gloved hands holding an instrument"});
cases.push({id:"media-video",category:"media-filter",query:"show me 30 videos with a visible person",expectMedia:"VIDEO"});
cases.push({id:"media-image",category:"media-filter",query:"show me 30 images with a visible person",expectMedia:"IMAGE"});
cases.push({id:"excl-1",category:"exclusion",query:"give me 30 files with a visible person but without gloved hands"});
cases.push({id:"excl-2",category:"exclusion",query:"give me 30 files with an exposed body region but not physical contact"});
// exact-N and count parsing
for(const n of[1,3,5,7,10])cases.push({id:`count-${n}`,category:"exact-n",query:`give me ${n} files with a visible person`,expectCount:n});
for(const[id,q,n]of[["num-1","man around 30",5],["num-2","person in his 30s",5],["num-3","30-year-old",5],["num-4","give me 30 results",30]] as Array<[string,string,number]>)
 cases.push({id,category:"count-parsing",query:q,expectCount:n});
// clinical specificity
for(const q of["surgery","procedure","treatment","hair transplant","FUE","implantation","extraction"])
 cases.push({id:`clin-${q.replace(/\s+/g,"-")}`,category:"clinical",query:q,clinical:true});
for(const q of["food","car","animal","airplane"])cases.push({id:`zero-${q}`,category:"zero-result",query:q,expectZero:true});

const users=(await db.from("app_users").select("user_id").eq("is_active",true).limit(1)).data??[];
const userId=String(users[0]!.user_id);
const uniq=[...new Set(cases.map(c=>c.query))];const vecs=await encodePhase17Queries(uniq);
const vecBy=new Map(uniq.map((q,i)=>[q,vecs[i]]));
function dcg(r:number[]){return r.reduce((s,v,i)=>s+v/Math.log2(i+2),0)}

async function run(c:Case){const t0=performance.now();
 const plan=await interpretQuery(c.query),req=classifyRequirements(plan),exp=expandQuery(plan,req),rv=vecBy.get(c.query)!;
 const retrieved=await retrieveCandidates(db,{queryPlan:plan,requirementPlan:req,expandedQueryPlan:exp,queryVectors:rv,requestedCount:plan.result_request.effective_count});
 const authorized=await authorizeCandidates(db,retrieved,userId);
 const evidence=await loadRerankingEvidence(db,authorized as any);
 const ranked=rerankAuthorizedCandidates(authorized as any,req,exp,evidence,plan.result_request.effective_count);
 const controlled=applyResultCount(ranked.candidates,plan.result_request,{isAuthorized:(x:any)=>x.authorization?.discover===true,isEligible:(x:any)=>x.phase19.eligible===true});
 const response=await buildDatabaseGroundedResponse({query:c.query,userId,count:controlled.count,candidates:controlled.candidates.map((x:any)=>({asset_id:x.asset_id,score:x.phase19.normalizedScore}))},new SupabaseGroundedResponseRepository(db));
 const ids=controlled.candidates.map((x:any)=>x.asset_id);const idx=c.target?ids.indexOf(c.target):-1;
 const ranking=controlled.candidates.map((x:any,i:number)=>({rank:i+1,asset_id:x.asset_id,filename:x.filename,score:x.phase19.normalizedScore,channels:(x.channels??[]).map((h:any)=>h.channel)}));
 const sceneChannels=[...new Set(ranking.flatMap(r=>r.channels).filter((ch:string)=>/SCENE|KEYFRAME/.test(ch)))];
 let metrics:any=null;
 if(c.relevant?.length){const rel=new Set(c.relevant);const flags=ids.map(id=>rel.has(id)?1:0);
  const first=flags.indexOf(1);const ideal=[...flags].sort((a,b)=>b-a);
  metrics={relevant_total:rel.size,hits:flags.reduce<number>((a,b)=>a+b,0),
   recall_at_k:rel.size?flags.reduce<number>((a,b)=>a+b,0)/rel.size:null,
   mrr:first>=0?1/(first+1):0,
   ndcg_at_10:dcg(ideal.slice(0,10))?dcg(flags.slice(0,10))/dcg(ideal.slice(0,10)):null}}
 const qt=c.clinical?queryTerm(c.query):null;
 const trace=c.clinical?ranking.map(r=>{const reason=(response.results??[]).find((x:any)=>x.asset_id===r.asset_id)?.match_reason??"";
  const claimed=[...new Set((affirmative(reason).toLowerCase().match(/hair transplant|implantation|extraction|procedure|treatment|surgery|injection|graft|fue|prp|laser/g)??[]))];
  const unlicensed=claimed.filter(t=>!licensed(r.asset_id,t));
  return{asset_id:r.asset_id,filename:r.filename,rank:r.rank,query_term:qt,
   supported:qt?licensed(r.asset_id,qt):false,
   negated_in_document:qt?new RegExp(`no [a-z ]{0,24}${qt}`).test(docText.get(r.asset_id)??""):false,
   claimed_terms:claimed,unlicensed_claim_terms:unlicensed,match_reason:reason}}):[];
 const unsupportedClinical=trace.filter(x=>x.unlicensed_claim_terms.length>0);
 const notReady=ranking.filter(r=>!searchReady.has(r.asset_id));
 const unauthorized=(authorized.candidates as any[]).filter(x=>x.authorization?.discover!==true);
 const count=controlled.count.effective_count;
 const ageSafe=c.category!=="count-parsing"||c.id==="num-4"?true:plan.result_request.requested_count===null;
 const pass=(c.expectTarget===undefined||idx>=0)&&(!c.expectRank1||idx===0)
  &&(c.expectCount===undefined||count===c.expectCount)
  &&(!c.expectMedia||controlled.candidates.every((x:any)=>String(evidence.metadata[x.asset_id]?.mimeType??"").toUpperCase().startsWith(c.expectMedia!)))
  &&(!c.expectZero||ids.length===0)&&(!c.clinical||unsupportedClinical.length===0)
  &&notReady.length===0&&unauthorized.length===0&&ageSafe
  &&(c.informational||!c.relevant?.length||(metrics.hits>0&&metrics.recall_at_k>=0.5));
 return{...c,pass,parsed_intent:plan.intent,requested_count:plan.result_request.requested_count,
  effective_count:count,candidate_count:retrieved.candidates.length,authorized_count:authorized.candidates.length,
  returned_count:ids.length,target_returned:c.target?idx>=0:null,target_rank:idx>=0?idx+1:null,
  metrics,clinical_trace:trace,unsupported_clinical_returned:unsupportedClinical,
  not_search_ready_returned:notReady,unauthorized_in_authorized_set:unauthorized.length,
  scene_channels_contributing:sceneChannels,
  channel_diagnostics:Object.fromEntries(Object.entries((retrieved.diagnostics as any).channels??{}).map(([k,v]:any)=>[k,v.hits??0])),
  ranking,latency_ms:performance.now()-t0}}

// Every acceptance call is bounded. Without this a hung RPC, embedding call or authorization
// request stalls the whole suite silently instead of failing the one case that is stuck.
const CASE_TIMEOUT_MS=Number(process.env.KDI_ACCEPTANCE_TIMEOUT_MS??120000);
async function runBounded(c:Case){
 let timer:NodeJS.Timeout|undefined;
 const guard=new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(Object.assign(new Error(`CASE_TIMEOUT:${c.id}:${CASE_TIMEOUT_MS}ms`),{timeout:true})),CASE_TIMEOUT_MS)});
 try{return await Promise.race([run(c),guard])}
 finally{if(timer)clearTimeout(timer)}}

const results:any[]=[];
for(const c of cases){results.push(await runBounded(c));const r=results.at(-1)!;
 console.log(`${c.id} ${r.pass?"PASS":"FAIL"} ret=${r.returned_count} rank=${r.target_rank??"-"}${r.metrics?` recall=${(r.metrics.recall_at_k??0).toFixed(2)}`:""}`)}
const detQ=["IMG_2951.MP4","give me 30 files with a visible person","give me 3 files with a visible person","surgery"];
const det:any[]=[];
for(const q of detQ){const base=cases.find(x=>x.query===q)??{id:"det",category:"determinism",query:q};
 const rows:any[]=[];for(let i=0;i<3;i++)rows.push(await runBounded({...base,id:`det-${i}`} as Case));
 const sig=(x:any)=>JSON.stringify(x.ranking.map((y:any)=>[y.asset_id,y.score]));
 det.push({query:q,repetitions:3,stable:rows.every((x,i)=>i===0||sig(x)===sig(rows[0]))})}

const blocking=results.filter(x=>!x.pass&&!x.informational);
const sceneCases=results.filter(x=>x.category==="scene-specific");
const clin=results.filter(x=>x.category==="clinical");
const report={generated_at:new Date().toISOString(),phase:"FULL_INDEX_30",
 status:blocking.length===0&&det.every(d=>d.stable)?"PASS":"FAIL",
 cohort:cohortIds.length,canonical_scenes:scenes.length,
 totals:{cases:results.length,passed:results.filter(x=>x.pass).length,
  blocking_failures:blocking.map(x=>x.id),informational_failures:results.filter(x=>!x.pass&&x.informational).map(x=>x.id)},
 scene_specific:{cases:sceneCases.length,passed:sceneCases.filter(x=>x.pass).length,
  scene_channels_observed:[...new Set(sceneCases.flatMap(x=>x.scene_channels_contributing))]},
 authorization_leakage:results.reduce((s,x)=>s+x.not_search_ready_returned.length+x.unauthorized_in_authorized_set,0),
 clinical_false_positives:clin.reduce((s,x)=>s+x.unsupported_clinical_returned.length,0),
 determinism:det,cases:results,external_inference:0};
writeFileSync(path.join(out,"full_index_30_raw_acceptance.json"),JSON.stringify(report,null,2)+"\n");
console.log(JSON.stringify({status:report.status,total:results.length,passed:report.totals.passed,
 blocking:report.totals.blocking_failures,informational:report.totals.informational_failures,
 scene_specific:report.scene_specific,auth_leak:report.authorization_leakage,
 clinical_fp:report.clinical_false_positives,determinism:det.every(d=>d.stable)}));
if(report.status!=="PASS")process.exitCode=1;
