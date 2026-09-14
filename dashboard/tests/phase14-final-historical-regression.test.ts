import assert from"node:assert/strict";import test from"node:test";import{interpretQuery}from"../db/query-interpreter";
const cases:[string,string[],string[]][]=[
 ["Patient with implantation of grafts",["PATIENT","IMPLANTING_GRAFTS"],[]],
 ["grafts being implanted",["IMPLANTING_GRAFTS"],[]],
 ["drawing of frontal hairline",["DRAWING_HAIRLINE","FRONTAL_HAIRLINE"],[]],
 ["scalp being cleansed",["CLEANSING","SCALP"],[]],
 ["patient receiving injection",["PATIENT","INJECTING"],[]],
 ["No graft implantation but graft implantation must be visible",["IMPLANTING_GRAFTS"],["IMPLANTING_GRAFTS"]],
 ["Leave any syringe scenes out",[],["INJECTING"]],
 ["Material taken in 2017",[],[]],
 ["A consultation taking place within a clinic",["CONSULTATION","CLINIC"],[]],
];
for(const[q,pos,neg]of cases)test(`historical ${q}`,async()=>{const p=await interpretQuery(q),pc=p.semantic.positive_concepts.map(x=>x.canonical_code),nc=p.semantic.negative_concepts.map(x=>x.canonical_code);for(const c of pos)assert.ok(pc.includes(c),`${q}: +${c}`);for(const c of neg)assert.ok(nc.includes(c),`${q}: -${c}`);if(q.startsWith("Material"))assert.equal(p.media.media_type,"ANY")});
