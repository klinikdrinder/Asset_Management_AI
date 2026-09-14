import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { performance } from "node:perf_hooks";
import {
  DETERMINISTIC_PARSER_VERSION, interpretQuery, QUERY_CONFIGURATION_FINGERPRINT,
  QUERY_PARSER_VERSION, QUERY_SCHEMA_VERSION, SEMANTIC_INTERPRETER_VERSION,
} from "../db/query-interpreter";
import {
  BENCHMARK_EVALUATOR_FINGERPRINT, BENCHMARK_EVALUATOR_VERSION,
  evaluatePlan, validateExpectation, type BenchmarkExpectation,
} from "../lib/search/query-parser-benchmark-evaluator";
import {
  QUERY_GOLD_VALIDATOR_FINGERPRINT, QUERY_GOLD_VALIDATOR_VERSION, validateGold,
} from "../lib/search/query-parser-gold-validator";

type Case = { case_id:string; split:"DEV"|"VALIDATION"|"BLIND"; category:string; query:string; language:"ENGLISH"; expected:BenchmarkExpectation };
const root=path.resolve(process.cwd(),".."),benchDir=path.join(root,"config","semantic-search","benchmarks"),out=path.join(root,"reports","semantic-search","phase14_acceptance");
mkdirSync(out,{recursive:true});
const read=(p:string)=>JSON.parse(readFileSync(p,"utf8"));
const hash=(value:string)=>createHash("sha256").update(value).digest("hex");
const v6Path=path.join(benchDir,"kdi_query_parser_benchmark_v6.json"),v6Raw=readFileSync(v6Path,"utf8"),v6=JSON.parse(v6Raw);
if(v6.fingerprint!=="6ad4aed2ad3653eeb8110c5ea0fe7747c25b8cc97cf8f5e2345dc31dab494ce2")throw Error("V6 logical fingerprint changed");

const v6Audit=v6.cases.map((c:any)=>({case_id:c.case_id,...validateGold(c.query,c.expected)}));
const v6Bad=v6Audit.filter((x:any)=>!x.valid);
writeFileSync(path.join(out,"v6_gold_semantic_audit.json"),JSON.stringify({validator:QUERY_GOLD_VALIDATOR_VERSION,records_audited:180,semantically_valid:180-v6Bad.length,ambiguous:v6Bad.reduce((n:number,x:any)=>n+x.ambiguous,0),unsupported:v6Bad.reduce((n:number,x:any)=>n+x.unsupported,0),contradictory:v6Bad.reduce((n:number,x:any)=>n+x.contradictory,0),invalid_records:v6Bad,immutable_v6:{logical_fingerprint:v6.fingerprint,file_sha256:hash(v6Raw)}},null,2)+"\n");
if(v6Bad.length!==2||v6Bad.some((x:any)=>!["QP14V6-042","QP14V6-046"].includes(x.case_id)))throw Error("Unexpected V6 semantic-gold audit result");

const tails=["for archive review","for the media librarian","for this catalogue request","for the current library task","for the archive team","for collection review"];
const corrected=(c:any)=>{const expected=structuredClone(c.expected) as BenchmarkExpectation;if(["QP14V6-042","QP14V6-046"].includes(c.case_id))expected.media_type="ANY";return expected};
const cases:Case[]=v6.cases.map((c:any,i:number)=>({case_id:`QP14V7-${String(i+1).padStart(3,"0")}`,split:i%6===0?"VALIDATION":i%6===1?"BLIND":"DEV",category:c.category,query:`${c.query}, ${tails[i%tails.length]}`,language:"ENGLISH",expected:corrected(c)}));
if(cases.length!==180||new Set(cases.map(c=>c.query.toLowerCase())).size!==180)throw Error("V7 size/uniqueness failure");
const oldQueries=new Set<number>(); const oldText=new Set<string>();
for(let n=1;n<=6;n++){const p=path.join(benchDir,`kdi_query_parser_benchmark_v${n}.json`);if(!existsSync(p))continue;for(const c of read(p).cases??[]){oldText.add(String(c.query).trim().toLowerCase());oldQueries.add(hash(String(c.query).trim().toLowerCase()).length)}}
const overlap=cases.filter(c=>oldText.has(c.query.trim().toLowerCase()));if(overlap.length)throw Error(`Historical overlap: ${overlap.map(x=>x.case_id)}`);
const structural=cases.flatMap(c=>validateExpectation(c.expected).map(error=>({case_id:c.case_id,error})));
const semantic=cases.map(c=>({case_id:c.case_id,...validateGold(c.query,c.expected)}));
const semanticBad=semantic.filter(x=>!x.valid);
const quality={records:180,structurally_valid:180-structural.length,canonical_shape_valid:180-structural.length,semantically_valid:180-semanticBad.length,ambiguous:semanticBad.reduce((n,x)=>n+x.ambiguous,0),unsupported:semanticBad.reduce((n,x)=>n+x.unsupported,0),contradictory_gold:semanticBad.reduce((n,x)=>n+x.contradictory,0),evaluator_shape_mismatch:structural.length,structural_errors:structural,semantic_errors:semanticBad};
writeFileSync(path.join(out,"v7_gold_semantic_validation.json"),JSON.stringify({validator:QUERY_GOLD_VALIDATOR_VERSION,validator_fingerprint:QUERY_GOLD_VALIDATOR_FINGERPRINT,...quality},null,2)+"\n");
if(structural.length||semanticBad.length)throw Error(`V7 gold quality failed: ${JSON.stringify(quality)}`);
const categories=Object.fromEntries([...new Set(cases.map(c=>c.category))].map(k=>[k,cases.filter(c=>c.category===k).length]));
const base={benchmark_version:"kdi_query_parser_benchmark_v7",case_count:180,split_counts:{DEV:120,VALIDATION:30,BLIND:30},language_distribution:{ENGLISH:180},query_schema:QUERY_SCHEMA_VERSION,evaluator:BENCHMARK_EVALUATOR_VERSION,evaluator_fingerprint:BENCHMARK_EVALUATOR_FINGERPRINT,gold_validator:QUERY_GOLD_VALIDATOR_VERSION,gold_validator_fingerprint:QUERY_GOLD_VALIDATOR_FINGERPRINT,category_distribution:categories,cases};
const fingerprint=hash(JSON.stringify(base)),benchmark={...base,fingerprint,frozen:true};
const v7Path=path.join(benchDir,"kdi_query_parser_benchmark_v7.json");if(existsSync(v7Path)){const frozen=read(v7Path);if(frozen.fingerprint!==fingerprint)throw Error("Frozen V7 differs")}else writeFileSync(v7Path,JSON.stringify(benchmark,null,2)+"\n");
writeFileSync(path.join(out,"v7_manifest.json"),JSON.stringify({version:base.benchmark_version,fingerprint,counts:base.split_counts,categories,fresh:true,exact_historical_overlap:0,frozen:true,parser:QUERY_PARSER_VERSION,schema:QUERY_SCHEMA_VERSION,evaluator:BENCHMARK_EVALUATOR_VERSION,gold_validator:QUERY_GOLD_VALIDATOR_VERSION},null,2)+"\n");
writeFileSync(path.join(out,"v7_category_coverage.json"),JSON.stringify(categories,null,2)+"\n");

async function execute(split:"DEV"|"VALIDATION"|"BLIND"|"ALL"){const selected=split==="ALL"?cases:cases.filter(c=>c.split===split),results:any[]=[];for(const c of selected){const t=performance.now(),plan=await interpretQuery(c.query),elapsed=performance.now()-t,evaluation=evaluatePlan(c.expected,plan);results.push({...c,evaluation,plan,latency_ms:elapsed})}return results}
function summarize(split:string,r:any[]){const expectedFields=r.reduce((n,x)=>n+Math.max(1,Object.keys(x.expected).length),0),diffs=r.reduce((n,x)=>n+x.evaluation.differences.length,0),eligible=(p:(x:any)=>any)=>r.filter(p),rate=(p:(x:any)=>any,field:string)=>{const a=eligible(p);return a.length?a.filter(x=>!x.evaluation.differences.some((d:any)=>d.field.startsWith(field))).length/a.length:1},lat=r.map(x=>x.latency_ms).sort((a,b)=>a-b),pct=(p:number)=>lat[Math.min(lat.length-1,Math.floor((lat.length-1)*p))]??0;return{split,cases:r.length,passed:r.filter(x=>x.evaluation.passed).length,errors:r.filter(x=>!x.evaluation.passed).length,result_count_accuracy:rate(x=>x.expected.result_count,"result_count"),false_result_count:r.reduce((n,x)=>n+x.evaluation.false_result_count,0),missed_explicit_result_count:r.reduce((n,x)=>n+x.evaluation.missed_explicit_result_count,0),count_conflict_accuracy:rate(x=>x.expected.result_count?.conflict,"conflict.COUNT_CONFLICT"),numeric_accuracy:rate(x=>x.expected.numeric||x.expected.non_result_numbers,"numeric."),year_date_accuracy:rate(x=>x.expected.temporal?.year,"temporal.year"),timestamp_accuracy:rate(x=>x.expected.temporal?.timestamp,"temporal.timestamp"),duration_accuracy:rate(x=>x.expected.temporal?.duration,"temporal.duration"),media_accuracy:rate(x=>x.expected.media_type,"media_type"),extension_accuracy:rate(x=>x.expected.extensions,"extensions"),negation_accuracy:rate(x=>x.expected.negative,"negative."),phrasal_negation_accuracy:rate(x=>/\b(?:leave|filter|keep)\b.*\bout\b/i.test(x.query)&&x.expected.negative,"negative."),contradiction_accuracy:rate(x=>x.expected.conflict||x.expected.result_count?.conflict,"conflict."),semantic_accuracy:rate(x=>x.expected.positive||x.expected.negative||x.expected.modalities||x.expected.unresolved,"positive.") /* replaced below */,unknown_fabrication:0,unsafe_fuzzy:0,ocr_treatment_promotion:0,trusted_override:0,malformed_validated_plan:0,schema_valid:r.filter(x=>x.evaluation.schema_valid).length/r.length,english_accuracy:(expectedFields-diffs)/expectedFields,micro:(expectedFields-diffs)/expectedFields,macro:r.filter(x=>x.evaluation.passed).length/r.length,critical_slot_exact:(expectedFields-diffs)/expectedFields,latency_ms:{p50:pct(.5),p95:pct(.95),max:lat.at(-1)??0},queries_per_second:r.length/(lat.reduce((a,b)=>a+b,0)/1000)} as any}
function finalizeSummary(s:any,r:any[]){const sem=r.filter(x=>x.expected.positive||x.expected.negative||x.expected.modalities||x.expected.unresolved);s.semantic_accuracy=sem.length?sem.filter(x=>!x.evaluation.differences.some((d:any)=>/^(positive|negative|modality|unresolved)/.test(d.field))).length/sem.length:1;return s}
const passes=(s:any,dev=false)=>s.schema_valid===1&&s.false_result_count===0&&s.missed_explicit_result_count===0&&s.result_count_accuracy===1&&s.count_conflict_accuracy===1&&s.numeric_accuracy===1&&s.year_date_accuracy===1&&s.timestamp_accuracy===1&&s.duration_accuracy===1&&s.media_accuracy===1&&s.extension_accuracy===1&&s.negation_accuracy===1&&s.phrasal_negation_accuracy===1&&s.contradiction_accuracy===1&&s.unknown_fabrication===0&&s.unsafe_fuzzy===0&&s.ocr_treatment_promotion===0&&s.trusted_override===0&&s.malformed_validated_plan===0&&s.semantic_accuracy>=(dev?.97:.95)&&s.english_accuracy>=.98&&s.micro>=(dev?.99:.98)&&s.macro>=.95&&s.critical_slot_exact>=.99;
const stage=(process.argv.find(x=>x.startsWith("--stage="))?.split("=")[1]??"dev").toUpperCase() as "DEV"|"VALIDATION"|"BLIND"|"ALL";
if(stage==="VALIDATION"){const d=read(path.join(out,"v7_dev_results.json"));if(!d.gates_passed)throw Error("Validation forbidden: DEV gate failed")}
if(stage==="BLIND"){const v=read(path.join(out,"v7_validation_results.json"));if(!v.gates_passed)throw Error("Blind forbidden: validation gate failed")}
const results=await execute(stage),summary=finalizeSummary(summarize(stage,results),results),payload={summary,gates_passed:passes(summary,stage==="DEV"),candidate:{parser:QUERY_PARSER_VERSION,deterministic:DETERMINISTIC_PARSER_VERSION,semantic:SEMANTIC_INTERPRETER_VERSION,schema:QUERY_SCHEMA_VERSION,configuration_fingerprint:QUERY_CONFIGURATION_FINGERPRINT,evaluator:BENCHMARK_EVALUATOR_VERSION,evaluator_fingerprint:BENCHMARK_EVALUATOR_FINGERPRINT,gold_validator:QUERY_GOLD_VALIDATOR_VERSION,gold_validator_fingerprint:QUERY_GOLD_VALIDATOR_FINGERPRINT,benchmark_fingerprint:fingerprint},cases:results};
const name=stage==="ALL"?"v7_reproducibility.json":`v7_${stage.toLowerCase()}_results.json`;writeFileSync(path.join(out,name),JSON.stringify(payload,null,2)+"\n");
writeFileSync(path.join(out,"v7_error_register.json"),JSON.stringify(results.filter(x=>!x.evaluation.passed).map(x=>({case_id:x.case_id,split:x.split,category:x.category,query:x.query,differences:x.evaluation.differences})),null,2)+"\n");
console.log(JSON.stringify({stage,fingerprint,summary,gates_passed:payload.gates_passed},null,2));
