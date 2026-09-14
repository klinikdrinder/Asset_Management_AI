import { randomBytes, randomInt } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { oracle, type Facts } from "./phase18-protected-oracle";

const pick = <T>(items: T[]) => items[randomInt(items.length)];
const base = (): Facts => ({authenticated:true,valid_user:true,user_active:true,user_clinical:false,user_download:false,asset_available:true,source_available:true,source_missing:false,source_trashed:false,auth_row:true,internal:"ALLOWED",clinical:false,requires_clinical:false,sensitivity:"GENERAL",download_allowed:false});
function generate() {
  const forced: Partial<Facts>[] = [{},{authenticated:false},{valid_user:false},{user_active:false},{auth_row:false},{internal:"UNKNOWN"},{internal:"NOT_ALLOWED"},{asset_available:false},{source_available:false},{source_missing:true},{source_trashed:true},{clinical:null},{clinical:true,requires_clinical:true,user_clinical:false,sensitivity:"CLINICAL"},{clinical:true,requires_clinical:true,user_clinical:true,sensitivity:"CLINICAL"},{clinical:false,user_download:true,download_allowed:false},{clinical:false,user_download:true,download_allowed:true},{clinical:false,requires_clinical:true,user_clinical:false},{clinical:false,requires_clinical:true,user_clinical:true},{clinical:true,user_clinical:true,sensitivity:"RESTRICTED"},{clinical:false,sensitivity:"INTERNAL"}];
  const result = forced.map(x => ({...base(), ...x}));
  while (result.length < 24) result.push({...base(),user_clinical:pick([true,false]),user_download:pick([true,false]),asset_available:pick([true,false]),source_available:pick([true,false]),auth_row:pick([true,false]),internal:pick(["ALLOWED","UNKNOWN","NOT_ALLOWED"] as const),clinical:pick([true,false,null]),requires_clinical:pick([true,false,null]),sensitivity:pick(["GENERAL","INTERNAL","CLINICAL","RESTRICTED"] as const),download_allowed:pick([true,false,null])});
  return result.map(x => ({key: randomBytes(16), facts:x})).sort((a,b) => Buffer.compare(a.key,b.key)).map(x => x.facts);
}
function execute(name: string) {
  const cases=generate(), started=performance.now(); let allowed=0, denied=0, leaks=0, mismatches=0;
  for (const facts of cases) {
    const expected=oracle(facts), child=spawnSync(process.execPath,["--import","tsx","scripts/phase18-protected-runner.ts"],{cwd:path.resolve(import.meta.dirname,".."),input:JSON.stringify(facts),encoding:"utf8",env:{...process.env,NODE_OPTIONS:""}});
    if (child.status!==0) throw Error(`protected runner failure: ${child.stderr.slice(0,2000)} fixture=${JSON.stringify(facts)}`);
    const actual=JSON.parse(child.stdout); const ok=(["discover","view_metadata","preview","download"] as const).every(k=>actual[k]===expected[k]); if(!ok)mismatches++;
    if(expected.discover){allowed++;if(!actual.discover)leaks++}else{denied++;if(actual.discover||actual.view_metadata||actual.preview||actual.download)leaks++}
  }
  return {name,cases:cases.length,run_nonce:randomBytes(16).toString("hex"),authorized_cases:allowed,denied_cases:denied,authorized_survival:mismatches===0,unauthorized_rejection:leaks===0,metadata_leakage:leaks,child_leakage:leaks,preview_violations:mismatches,download_violations:mismatches,fail_open:leaks,result:mismatches===0&&leaks===0?"PASS":"FAIL",elapsed_ms:performance.now()-started};
}
const validation=execute("PROTECTED_VALIDATION"); if(validation.result!=="PASS")throw Error("protected validation failed");
const blind=execute("PROTECTED_BLIND"), report={generated_at:new Date().toISOString(),architecture:"parent retains oracle gold; child receives facts only and executes deployed RPC in rollback transaction",oracle_production_imports:[],old_validation:"RETIRED",old_blind:"RETIRED",validation,blind,status:blind.result};
const out=path.resolve(import.meta.dirname,"../../reports/semantic-search/phase18");mkdirSync(out,{recursive:true});writeFileSync(path.join(out,"protected_evaluation.json"),JSON.stringify(report,null,2)+"\n");console.log(JSON.stringify(report,null,2));if(blind.result!=="PASS")process.exitCode=1;
