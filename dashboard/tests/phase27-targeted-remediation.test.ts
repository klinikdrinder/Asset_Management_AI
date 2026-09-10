import assert from "node:assert/strict";
import test from "node:test";
import {interpretQuery} from "../db/query-interpreter";
import {classifyRequirements} from "../db/requirement-classifier";
import {retrieveCandidates} from "../db/candidate-retriever";
import {resolveConversationalSearch} from "../db/conversational-search-memory";

test("lower-face variants generalize to canonical anatomy",async()=>{
  for(const query of ["injection in lower facial area","procedure around the lower facial region"]){
    const plan=await interpretQuery(query);
    assert.ok(plan.semantic.positive_concepts.some((x:any)=>x.canonical_code==="LOWER_FACE"));
  }
});

test("numeric semantics remain independent from result count",async()=>{
  const age=await interpretQuery("return 4 videos featuring a 30 year old patient");
  assert.equal(age.result_request.requested_count,4);assert.equal(age.numeric.age_exact,30);
  const graft=await interpretQuery("return 2 clips involving 3000 grafts");
  assert.equal(graft.result_request.requested_count,2);assert.equal(graft.numeric.graft_count_exact,3000);
});

test("conversation exclusion remains an exclusion",()=>{
  const prior={sessionId:"s",userId:"u",queryId:"q",resolvedQuery:"injection video",filters:{media_type:"video"},requestedCount:5,resultAssetIds:["a"],lastActivityAt:new Date().toISOString()};
  const resolution=resolveConversationalSearch({query:"without the neck",sessionId:"s",userId:"u",prior});
  assert.equal(resolution.filters.excluded_anatomy,"NECK");assert.equal(resolution.filters.anatomy,undefined);
});

test("explicit false observation does not become ordinary negative retrieval",async()=>{
  const db:any={from(table:string){let falseState=false;const q:any={select(){return q},eq(column:string,value:any){if(column==="semantic_state"&&value==="FALSE")falseState=true;return q},is(){return q},limit(){return q},ilike(){return q},in(){return q},then(resolve:any){const data=table==="semantic_assertions"&&falseState?[]:table==="asset_search_concepts_v2"?[{asset_id:"injection",canonical_code:"INJECTING"}]:[];return Promise.resolve(resolve({data,error:null}))}};return q}};
  const plan=await interpretQuery("files explicitly not depicting injection"),requirements=classifyRequirements(plan);
  const out=await retrieveCandidates(db,{queryPlan:plan,requirementPlan:requirements,expandedQueryPlan:{requirements:Object.values(requirements).flat(),expansion_fingerprint:"x"}});
  assert.equal(out.candidates.length,0);assert.equal(out.diagnostics.channels.STRUCTURED_CANONICAL.hits>0,true);
});
