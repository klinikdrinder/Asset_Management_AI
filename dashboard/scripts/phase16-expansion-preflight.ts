import {createHash} from "node:crypto"; import {readFile} from "node:fs/promises";
const sha=async(p:string)=>createHash("sha256").update(await readFile(p)).digest("hex");
console.log(JSON.stringify({parser:await sha("dashboard/db/query-interpreter.ts"),classifier:await sha("dashboard/db/requirement-classifier.ts"),benchmark:await sha("config/semantic-search/benchmarks/kdi_query_expansion_benchmark_v1.json")},null,2));
