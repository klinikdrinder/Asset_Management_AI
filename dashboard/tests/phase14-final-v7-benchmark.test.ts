import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { validateExpectation } from "../lib/search/query-parser-benchmark-evaluator";
import { validateGold } from "../lib/search/query-parser-gold-validator";

const file=path.resolve(process.cwd(),"..","config","semantic-search","benchmarks","kdi_query_parser_benchmark_v7.json");
test("V7 is a frozen 120/30/30 English benchmark with valid independent gold",()=>{const b=JSON.parse(readFileSync(file,"utf8"));assert.equal(b.benchmark_version,"kdi_query_parser_benchmark_v7");assert.equal(b.frozen,true);assert.equal(b.cases.length,180);assert.deepEqual(b.split_counts,{DEV:120,VALIDATION:30,BLIND:30});assert.equal(new Set(b.cases.map((x:any)=>x.query.toLowerCase())).size,180);for(const c of b.cases){assert.equal(c.language,"ENGLISH");assert.deepEqual(validateExpectation(c.expected),[]);assert.equal(validateGold(c.query,c.expected).valid,true,c.case_id)}});
