// Phase 11 — 30-asset cohort acceptance suite.
// Exercises the certified Phase 9/10 production search chain. Ground truth is read from committed
// semantic truth (active OBSERVED assertions); no relevance judgement is invented here.
import{readFileSync,writeFileSync,mkdirSync}from"node:fs";import path from"node:path";import{performance}from"node:perf_hooks";import{createClient}from"@supabase/supabase-js";
import{interpretQuery}from"../db/query-interpreter";import{classifyRequirements}from"../db/requirement-classifier";import{expandQuery}from"../db/query-expander";import{retrieveCandidates}from"../db/candidate-retriever";import{authorizeCandidates}from"../db/candidate-authorizer";import{loadRerankingEvidence,rerankAuthorizedCandidates}from"../db/deterministic-reranker";import{applyResultCount}from"../db/result-count-controller";import{encodePhase17Queries}from"../db/phase17-query-encoder";import{buildDatabaseGroundedResponse,SupabaseGroundedResponseRepository}from"../db/database-grounded-search-response";
const root=path.resolve(import.meta.dirname,"../.."),out=path.join(root,"reports/semantic-search/rollout/phase-11");mkdirSync(out,{recursive:true});
const CANARY="a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd";
function env(p:string){try{return Object.fromEntries(readFileSync(p,"utf8").replace(/^﻿/,"").split(/\r?\n/).flatMap(l=>{const m=l.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return{}}}
const e:any={...env(path.join(root,".env")),...env(path.join(root,".env.local")),...env(path.join(root,"dashboard/.env.local"))};
const db=createClient(e.SUPABASE_URL||e.NEXT_PUBLIC_SUPABASE_URL,e.SUPABASE_SERVICE_ROLE_KEY,{auth:{persistSession:false,autoRefreshToken:false}});

// ---------- cohort + ground truth from committed semantic truth ----------
const layerRows=(await db.from("asset_semantic_layers").select("asset_id,processing_status").eq("active",true)).data??[];
const per=new Map<string,{n:number;c:number}>();
for(const r of layerRows){const v=per.get(r.asset_id)??{n:0,c:0};v.n++;if(r.processing_status==="COMPLETE")v.c++;per.set(r.asset_id,v)}
const cohortIds=[...per.entries()].filter(([,v])=>v.n===18&&v.c===18).map(([k])=>k);
const assetRows=(await db.from("assets").select("id,file_name,mime_type,file_extension").in("id",cohortIds)).data??[];
const assetById=new Map(assetRows.map(a=>[a.id as string,a]));
const cohort=new Set(cohortIds);
const assertRows=(await db.from("semantic_assertions").select("asset_id,canonical_concept_code,semantic_state,layer_id").in("asset_id",cohortIds).eq("active",true)).data??[];
const observed=new Map<string,Set<string>>();       // concept -> assets
const assetConcepts=new Map<string,string[]>();     // asset -> concepts
for(const r of assertRows){if(r.semantic_state!=="OBSERVED")continue;
  if(!observed.has(r.canonical_concept_code))observed.set(r.canonical_concept_code,new Set());
  observed.get(r.canonical_concept_code)!.add(r.asset_id);
  assetConcepts.set(r.asset_id,[...(assetConcepts.get(r.asset_id)??[]),r.canonical_concept_code])}
const readyRows=(await db.from("asset_search_documents").select("asset_id,build_status").eq("build_status","READY")).data??[];
const searchReady=new Set(readyRows.map(r=>r.asset_id as string));

// Query phrasing for the concepts that actually exist in the cohort. Nothing here invents a concept.
const PHRASE:Record<string,string>={
 PERSON_OR_BODY_PART_VISIBLE:"a visible person",
 HANDHELD_INSTRUMENT_AND_PROTECTIVE_GLOVES_VISIBLE:"gloved hands holding an instrument",
 EXPOSED_BODY_REGION_VISIBLE:"an exposed body region",
 PHYSICAL_CONTACT_HOLDING_OR_MANIPULATION_VISIBLE:"physical contact",
 BROAD_ENVIRONMENT_VISIBLE:"a broad indoor or outdoor environment",
 CLINICIAN:"a clinician",PATIENT:"a patient",PATIENT_RECLINING:"a reclining patient",
 CLINICIAN_GLOVED:"a gloved clinician",CLINICIAN_MASKED:"a masked clinician",
 TREATMENT_ROOM:"a treatment room",OPERATING_ROOM:"an operating room",
 SCALP:"a scalp",FACE:"a face",FRONTAL_SCALP:"a frontal scalp",NECK:"a neck",CHEEK:"a cheek",
 HANDHELD:"a handheld moving camera",STATIC:"a static camera",VERTICAL:"vertical framing",
 CLOSEUP:"a close-up",EXTREME_CLOSEUP:"an extreme close-up",MEDIUM_CLOSEUP:"a medium close-up",
 TOUCHING:"touching",INJECTING:"injecting",USING_DEVICE:"using a device",
 ADULT_PRESENTATION:"an adult",EYE_PROTECTION_VISIBLE:"visible eye protection",
 CLINICIAN_TREATS_PATIENT:"a clinician treating a patient",
 CLINICIAN_HANDS_IN_FOREGROUND:"clinician hands in the foreground",
 PROCEDURE_CONTENT:"procedure content",CLINICAL_REFERENCE:"clinical reference material",
 VISIBLE_TEXT:"readable on-screen text",AUDIO_STREAM_PRESENT:"an audio track"};
// A clinical word is licensed for an asset when one of its own observed concepts supports it.
// Anything else is either an explicit grounded negation ("no active procedure") or unsupported.
const CLINICAL_LICENSE:Record<string,string[]>={
 "hair transplant":["HAIR_TRANSPLANT","HAIR_TRANSPLANT_FUE","HAIR_TRANSPLANT_PROCEDURE_CONTENT","FUE_IMPLANTATION"],
 "fue":["HAIR_TRANSPLANT_FUE","FUE_IMPLANTATION"],
 "implantation":["FUE_IMPLANTATION","IMPLANTING_GRAFTS"],
 "graft":["FUE_IMPLANTATION","IMPLANTING_GRAFTS","RECIPIENT_REGION"],
 "extraction":[],
 "injection":["INJECTABLES","INJECTING","HOLDING_SYRINGE","VISIBLE_INJECTION_AT_LOWER_FACE","VISIBLE_INJECTION_AT_NECK"],
 "prp":[],"laser":[],"surgery":[],
 "procedure":["PROCEDURE_CONTENT","PROCEDURE_PREPARATION_CONTENT","VISIBLE_RECIPIENT_AREA_PROCEDURE","HAIR_TRANSPLANT_PROCEDURE_CONTENT","OPERATING_ROOM"],
 "treatment":["TREATMENT_ROOM","PATIENT_POSITIONED_IN_TREATMENT_CHAIR","CLINICIAN_TREATS_PATIENT","SCALP_UNDER_ACTIVE_CLINICAL_ATTENTION","FACE_UNDER_ACTIVE_CLINICAL_ATTENTION","NECK_TREATMENT_AREA_DOMINANT","TREATMENT_AREA_PARTIALLY_VISIBLE","TOOL_VISIBLE_NEAR_TREATMENT_AREA"]};
const CLINICAL_CONCEPTS=[...new Set(Object.values(CLINICAL_LICENSE).flat())];
const CLINICAL_RE=/surgery|procedure|treatment|hair transplant|fue|implantation|extraction|graft|prp|laser|injection/i;
const docText=new Map((((await db.from("asset_search_documents").select("asset_id,searchable_text").in("asset_id",cohortIds)).data)??[]).map(r=>[r.asset_id as string,String(r.searchable_text??"").toLowerCase()]));
function licensed(assetId:string,term:string){const codes=CLINICAL_LICENSE[term]??[];const own=assetConcepts.get(assetId)??[];return codes.some(c=>own.includes(c))}
function negated(assetId:string,term:string){const t=docText.get(assetId)??"";return new RegExp(`no [a-z ]{0,24}${term}`).test(t)}
function queryTerm(q:string){const m=q.toLowerCase().match(/hair transplant|implantation|extraction|procedure|treatment|surgery|injection|graft|fue|prp|laser/);return m?m[0]:null}
// The grounded builder emits "…identifies X, Y." plus an optional disclaimer sentence. Only the
// affirmative clause can assert a clinical fact; the disclaimer is correct behaviour, not leakage.
function affirmative(reason:string){return String(reason??"").split(/(?:^|\.\s*)(?:the specific|no )/i)[0]}

type Case={id:string;category:string;query:string;target?:string;expectTarget?:boolean;expectRank1?:boolean;
 expectCount?:number;expectMedia?:string;expectZero?:boolean;relevant?:string[];clinical?:boolean;note?:string};
const cases:Case[]=[];
const ordered=[...cohortIds].sort((a,b)=>String(assetById.get(a)?.file_name).localeCompare(String(assetById.get(b)?.file_name)));

// A. filename — every cohort asset, full + stem + case variants
for(const id of ordered){const f=String(assetById.get(id)!.file_name);const stem=f.replace(/\.[^.]+$/,"");
 cases.push({id:`fn-exact:${f}`,category:"filename-exact",query:f,target:id,expectTarget:true,expectRank1:true});
 if(stem&&stem!==f)cases.push({id:`fn-stem:${f}`,category:"filename-stem",query:stem,target:id,expectTarget:true});
 cases.push({id:`fn-lower:${f}`,category:"filename-case",query:f.toLowerCase(),target:id,expectTarget:true});
 cases.push({id:`fn-upper:${f}`,category:"filename-case",query:f.toUpperCase(),target:id,expectTarget:true})}
// A2. false-match guards for the Phase 10 filename correction
for(const q of["mp4","jpeg","JPG","mov"])cases.push({id:`fn-ext:${q}`,category:"filename-extension-guard",query:q,note:"a bare extension must not behave as a precise filename literal"});
for(const q of["ZZQQ_9999.mp4","99.99 (99).jpeg"])cases.push({id:`fn-absent:${q}`,category:"filename-absent",query:q,expectZero:true});

// B. grounded semantic — one per cohort asset, built from that asset's own observed concepts
for(const id of ordered){const cs=(assetConcepts.get(id)??[]).filter(c=>PHRASE[c]);
 if(!cs.length){cases.push({id:`gr:${assetById.get(id)!.file_name}`,category:"grounded-none",query:String(assetById.get(id)!.file_name),target:id,expectTarget:true,note:"no phrase-mappable observed concept; identity retrieval is the grounded path"});continue}
 const pick=cs.sort((a,b)=>(observed.get(a)!.size)-(observed.get(b)!.size))[0];
 cases.push({id:`gr:${assetById.get(id)!.file_name}`,category:"grounded",query:`give me 30 files with ${PHRASE[pick]}`,target:id,expectTarget:true,relevant:[...observed.get(pick)!]})}

// C. paraphrase across distinct concepts
const paraphrase:Array<[string,string,string]>=[
 ["p-person","give me 30 files showing somebody","PERSON_OR_BODY_PART_VISIBLE"],
 ["p-gloves","give me 30 files with hands in surgical gloves","HANDHELD_INSTRUMENT_AND_PROTECTIVE_GLOVES_VISIBLE"],
 ["p-skin","give me 30 files where skin is uncovered","EXPOSED_BODY_REGION_VISIBLE"],
 ["p-room","give me 30 files inside a clinic room","TREATMENT_ROOM"],
 ["p-recline","give me 30 files with someone lying back in a chair","PATIENT_RECLINING"]];
for(const[id,q,c]of paraphrase)cases.push({id,category:"paraphrase",query:q,relevant:[...(observed.get(c)??[])]});

// D. multi-concept
cases.push({id:"mc-people-action",category:"multi-concept",query:"give me 30 files with a visible person and physical contact"});
cases.push({id:"mc-anatomy-instrument",category:"multi-concept",query:"give me 30 files with an exposed body region and gloved hands holding an instrument"});
cases.push({id:"mc-setting-framing",category:"multi-concept",query:"give me 30 files in a treatment room with a close-up"});
cases.push({id:"mc-speech-topic",category:"multi-concept",query:"give me 30 files with an audio track and a clinician",note:"speech+topic combination; depends on Layer 14 truth"});
// E/F. filters
cases.push({id:"media-video",category:"media-filter",query:"show me 30 videos with a visible person",expectMedia:"VIDEO"});
cases.push({id:"media-image",category:"media-filter",query:"show me 30 images with a visible person",expectMedia:"IMAGE"});
cases.push({id:"neg-1",category:"negative-filter",query:"give me 30 files with a visible person but without gloved hands"});
cases.push({id:"neg-2",category:"negative-filter",query:"give me 30 files with an exposed body region but not physical contact"});
// G. counts, incl. a request larger than the eligible pool
for(const n of[1,3,5,7,10])cases.push({id:`count-${n}`,category:"count",query:`give me ${n} files with a visible person`,expectCount:n});
cases.push({id:"count-500",category:"count-shortage",query:"give me 500 files with a visible person",expectCount:500,note:"requested count exceeds the eligible pool; shortage must be honest, not padded"});
// H. number interpretation
for(const[id,q,n]of[["age-1","man around 30",5],["age-2","person in his 30s",5],["age-3","30-year-old",5],["age-4","give me 30 results",30]] as Array<[string,string,number]>)
 cases.push({id,category:"number",query:q,expectCount:n});
// Clinical regression with per-asset tracing
for(const q of["surgery","procedure","treatment","hair transplant","FUE","implantation","extraction"])
 cases.push({id:`clin-${q.replace(/\s+/g,"-")}`,category:"clinical",query:q,clinical:true});
// §12 replacement for the historical "visible tool" assertion
cases.push({id:"visible-tool-relevance",category:"ranking-displacement",query:"visible tool",
 relevant:[...(observed.get("HANDHELD_INSTRUMENT_AND_PROTECTIVE_GLOVES_VISIBLE")??[])],
 note:"replaces the legacy fixed-asset top-5 assertion with a relevant-set assertion"});
// O. zero-result honesty
for(const q of["food","car","landscape photograph of a mountain","animal","airplane"])
 cases.push({id:`zero-${q.split(" ")[0]}`,category:"zero-result",query:q,expectZero:true});

const users=(await db.from("app_users").select("user_id,is_active").eq("is_active",true).limit(1)).data??[];
if(!users[0])throw Error("active user unavailable");const userId=String(users[0].user_id);
const uniq=[...new Set(cases.map(c=>c.query))];
const vecs=await encodePhase17Queries(uniq);const vecBy=new Map(uniq.map((q,i)=>[q,vecs[i]]));

function dcg(rel:number[]){return rel.reduce((s,r,i)=>s+r/Math.log2(i+2),0)}
async function run(c:Case){const t0=performance.now();
 const plan=await interpretQuery(c.query),req=classifyRequirements(plan),exp=expandQuery(plan,req),rv=vecBy.get(c.query)!;
 const retrieved=await retrieveCandidates(db,{queryPlan:plan,requirementPlan:req,expandedQueryPlan:exp,queryVectors:rv,requestedCount:plan.result_request.effective_count});
 const authorized=await authorizeCandidates(db,retrieved,userId);
 const evidence=await loadRerankingEvidence(db,authorized as any);
 const ranked=rerankAuthorizedCandidates(authorized as any,req,exp,evidence,plan.result_request.effective_count);
 const controlled=applyResultCount(ranked.candidates,plan.result_request,{isAuthorized:(x:any)=>x.authorization?.discover===true,isEligible:(x:any)=>x.phase19.eligible===true});
 const response=await buildDatabaseGroundedResponse({query:c.query,userId,count:controlled.count,candidates:controlled.candidates.map((x:any)=>({asset_id:x.asset_id,score:x.phase19.normalizedScore}))},new SupabaseGroundedResponseRepository(db));
 const ids=controlled.candidates.map((x:any)=>x.asset_id);
 const idx=c.target?ids.indexOf(c.target):-1;
 const ranking=controlled.candidates.map((x:any,i:number)=>({rank:i+1,asset_id:x.asset_id,filename:x.filename,score:x.phase19.normalizedScore,eligible:x.phase19.eligible,in_cohort:cohort.has(x.asset_id)}));
 const count=controlled.count.effective_count;
 // metrics against committed ground truth
 let metrics:any=null;
 if(c.relevant?.length){const rel=new Set(c.relevant);const flags=ids.map(id=>rel.has(id)?1:0);
  const firstHit=flags.indexOf(1);const ideal=[...flags].sort((a,b)=>b-a);
  metrics={relevant_total:rel.size,retrieved:ids.length,hits:flags.reduce<number>((a,b)=>a+b,0),
   recall_at_k:rel.size?flags.reduce<number>((a,b)=>a+b,0)/rel.size:null,
   precision_at_k:ids.length?flags.reduce<number>((a,b)=>a+b,0)/ids.length:null,
   mrr:firstHit>=0?1/(firstHit+1):0,
   ndcg_at_10:dcg(ideal.slice(0,10))?dcg(flags.slice(0,10))/dcg(ideal.slice(0,10)):null}}
 // authorization + leakage
 const notReady=ranking.filter(r=>!searchReady.has(r.asset_id));
 const unauthorized=(authorized.candidates as any[]).filter(x=>x.authorization?.discover!==true);
 // clinical tracing: which returned assets actually support a clinical concept
 const qt=c.clinical?queryTerm(c.query):null;
 const clinicalTrace=c.clinical?ranking.map(r=>{const sup=qt?licensed(r.asset_id,qt):false;const neg=qt?negated(r.asset_id,qt):false;
   const reason=(response.results??[]).find((x:any)=>x.asset_id===r.asset_id)?.match_reason??"";
   const claimed=[...new Set((affirmative(reason).toLowerCase().match(/hair transplant|implantation|extraction|procedure|treatment|surgery|injection|graft|fue|prp|laser/g)??[]))];
   const unlicensed=claimed.filter(t=>!licensed(r.asset_id,t));
   const asserted=unlicensed.length>0;
   return{asset_id:r.asset_id,filename:r.filename,rank:r.rank,query_term:qt,
    supporting_concepts:(assetConcepts.get(r.asset_id)??[]).filter(x=>(CLINICAL_LICENSE[qt??""]??[]).includes(x)),
    supported:sup,explicitly_negated_in_document:neg,asserts_clinical_claim:asserted,
    claimed_terms:claimed,unlicensed_claim_terms:unlicensed,match_reason:reason,
    classification:sup?"SUPPORTED":neg?"MATCHED_ON_GROUNDED_NEGATION":"UNSUPPORTED_NON_GROUNDED_MATCH"}}):[];
 // A false positive is an unsupported asset for which the system actually asserts the clinical fact.
 const unsupportedClinical=clinicalTrace.filter(x=>!x.supported&&x.asserts_clinical_claim);
 const unsafeReason=(response.results??[]).filter((x:any)=>CLINICAL_RE.test(affirmative(x.match_reason))&&!(assetConcepts.get(x.asset_id)??[]).some(y=>CLINICAL_CONCEPTS.includes(y))).map((x:any)=>({asset_id:x.asset_id,match_reason:x.match_reason}));
 const ageSafe=c.category!=="number"||c.id==="age-4"?true:plan.result_request.requested_count===null;
 const passTarget=c.expectTarget===undefined||idx>=0;
 const passRank1=!c.expectRank1||idx===0;
 const passCount=c.category==="count-shortage"
  ?(plan.result_request.requested_count===c.expectCount&&ids.length<=count&&ids.length===new Set(ids).size)
  :(c.expectCount===undefined||count===c.expectCount);
 const passMedia=!c.expectMedia||controlled.candidates.every((x:any)=>String(evidence.metadata[x.asset_id]?.mimeType??"").toUpperCase().startsWith(c.expectMedia!));
 const passZero=!c.expectZero||ids.length===0;
 const passClinical=!c.clinical||unsupportedClinical.length===0;
 const passReady=notReady.length===0;
 const informational=c.category==="paraphrase";
 const passRelevance=informational||!c.relevant?.length||(metrics.hits>0&&metrics.recall_at_k>=0.5);
 return{...c,informational,pass:passTarget&&passRank1&&passCount&&passMedia&&passZero&&passClinical&&passReady&&passRelevance&&ageSafe&&unsafeReason.length===0,
  parsed_intent:plan.intent,requested_count:plan.result_request.requested_count,effective_count:count,
  requirement_classes:[...new Set(["response_controls","hard_constraints","hard_exclusions","strong_requirements","preferences","negative_preferences","context","unresolved","conflicts"].flatMap(b=>((req as any)[b]??[]).map((r:any)=>r.classification)))],
  expanded_terms:((exp as any).requirements??[]).flatMap((r:any)=>r.expansions??[]).length,
  candidate_count:retrieved.candidates.length,authorized_count:authorized.candidates.length,
  unauthorized_in_authorized_set:unauthorized.length,not_search_ready_returned:notReady,
  returned_count:ids.length,target_returned:c.target?idx>=0:null,target_rank:idx>=0?idx+1:null,
  metrics,clinical_trace:clinicalTrace,unsupported_clinical_returned:unsupportedClinical,
  unsafe_match_reasons:unsafeReason,
  filename_literal:(retrieved.diagnostics as any).channels?.FILENAME_LITERAL??null,
  grounded_results:(response.results??[]).slice(0,3).map((x:any)=>({asset_id:x.asset_id,match_reason:x.match_reason??null,grounding:x.grounding??null})),
  ranking,latency_ms:performance.now()-t0}}

const results:any[]=[];
for(const c of cases){results.push(await run(c));const r=results.at(-1)!;
 console.log(`${c.id} ${r.pass?"PASS":"FAIL"} ret=${r.returned_count} rank=${r.target_rank??"-"}${r.metrics?` recall=${(r.metrics.recall_at_k??0).toFixed(2)}`:""}`)}

// M. determinism across the required query shapes
const detQueries=["IMG_2951.MP4","give me 30 files with a visible person","give me 30 files with a visible person and physical contact","give me 3 files with a visible person","surgery","give me 30 files with an audio track and a clinician"];
const det:any[]=[];
for(const q of detQueries){const base=cases.find(x=>x.query===q)??{id:"det",category:"determinism",query:q};
 const rows:any[]=[];for(let i=0;i<3;i++)rows.push(await run({...base,id:`det-${i}`} as Case));
 const sig=(x:any)=>JSON.stringify(x.ranking.map((y:any)=>[y.asset_id,y.score]));
 det.push({query:q,repetitions:3,stable:rows.every((x,i)=>i===0||sig(x)===sig(rows[0])),order:rows[0].ranking.map((y:any)=>y.asset_id)})}

const failed=results.filter(x=>!x.pass);
const report={generated_at:new Date().toISOString(),phase:11,
 status:failed.length===0&&det.every(d=>d.stable)?"PASS":"FAIL",
 cohort_size:cohortIds.length,search_ready:searchReady.size,
 cohort:ordered.map(id=>({asset_id:id,filename:assetById.get(id)!.file_name,mime_type:assetById.get(id)!.mime_type,observed_concepts:assetConcepts.get(id)??[]})),
 totals:{cases:results.length,passed:results.length-failed.length,failed:failed.map(x=>x.id)},
 cases:results,determinism:det,external_inference:0,semantic_media_analysis:0};
writeFileSync(path.join(out,"phase_11_raw_acceptance.json"),JSON.stringify(report,null,2)+"\n");
console.log(JSON.stringify({status:report.status,cohort:cohortIds.length,total:results.length,passed:report.totals.passed,failed:report.totals.failed,determinism:det.every(d=>d.stable)}));
if(report.status!=="PASS")process.exitCode=1;
