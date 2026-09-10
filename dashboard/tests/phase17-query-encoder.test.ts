import assert from "node:assert/strict";
import test from "node:test";
import {encodePhase17Query} from "../db/phase17-query-encoder";

test("locked Phase 17 encoders produce normalized compatible dimensions",{timeout:240_000},async()=>{
  const value=await encodePhase17Query("neck injection");
  assert.equal(value.text.length,384);
  assert.equal(value.visual.length,512);
  const norm=(v:number[])=>Math.sqrt(v.reduce((n,x)=>n+x*x,0));
  assert.ok(Math.abs(norm(value.text)-1)<1e-4);
  assert.ok(Math.abs(norm(value.visual)-1)<1e-4);
  assert.equal(value.provenance.e5.model,"intfloat/multilingual-e5-small");
  assert.equal(value.provenance.openclip.checkpoint,"laion2b_s34b_b79k");
});

test("mixed dimensions fail safely before RPC",async()=>{
  const calls:string[]=[];const db:any={from(){const q:any={select(){return q},eq(){return q},ilike(){return q},in(){return q},limit(){return q},then(resolve:any){resolve({data:[],error:null})}};return q},rpc(name:string){calls.push(name);return Promise.resolve({data:[],error:null})}};
  const p={original_query:"neck injection",parser_metadata:{query_fingerprint:"q"},result_request:{effective_count:5}};
  const {retrieveCandidates}=await import("../db/candidate-retriever");
  const out=await retrieveCandidates(db,{queryPlan:p,requirementPlan:{classifier_fingerprint:"r"},expandedQueryPlan:{expansion_fingerprint:"e",requirements:[]},queryVectors:{text:Array(512).fill(0)}});
  assert.equal(calls.length,0);
  assert.ok(out.diagnostics.unavailable_channels.includes("TEXT_ASSET"));
});
