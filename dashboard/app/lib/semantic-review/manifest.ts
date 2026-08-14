import "server-only";
import { randomUUID } from "node:crypto";
import { readFile, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { EVIDENCE_REVIEWER, REVIEWER, REVIEW_FIELDS, validateReviewFields, type ReviewAsset } from "./contract";
export { CONTENT_TYPES, EVIDENCE_REVIEWER, REVIEWER, REVIEW_FIELDS, validatePending } from "./contract";
export type { ReviewAsset, ReviewValidation } from "./contract";

export function resolveReviewManifestPath(dashboardRoot=process.cwd()){
  if(path.basename(path.resolve(dashboardRoot)).toLowerCase()!=="dashboard")throw new Error("Semantic review must run from the dashboard project root");
  return path.resolve(dashboardRoot,"..","data","semantic_manual_benchmark_20.json");
}
export const MANIFEST_PATH=resolveReviewManifestPath();
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type Manifest = { manifest_version:string; assets:ReviewAsset[] };

function assertShape(value:unknown): asserts value is Manifest {
  if (!value || typeof value!=="object" || !Array.isArray((value as Manifest).assets) || (value as Manifest).assets.length!==20) throw new Error("Benchmark manifest has an unexpected structure");
  const ids=new Set<string>();
  for(const row of (value as Manifest).assets){
    if(!row || typeof row!=="object" || !UUID.test(row.asset_id) || ids.has(row.asset_id) || !["image","video"].includes(row.media_type)) throw new Error("Benchmark manifest contains an invalid asset entry");
    ids.add(row.asset_id);
    for(const key of [...REVIEW_FIELDS,"filename","reviewed_by","reviewed_at"] as const) if(typeof row[key]!=="string") throw new Error("Benchmark manifest contains an invalid field");
  }
}
export async function loadReviewManifest(manifestPath=MANIFEST_PATH){const value:unknown=JSON.parse(await readFile(manifestPath,"utf8"));assertShape(value);return value;}
function singaporeTimestamp(){const now=new Date(Date.now()+8*60*60*1000);return now.toISOString().replace("Z","+08:00");}
export async function writeManifestSafely(manifestPath:string,manifest:Manifest){
  assertShape(manifest);const temporary=`${manifestPath}.${process.pid}.${randomUUID()}.tmp`;
  try{await writeFile(temporary,`${JSON.stringify(manifest,null,2)}\n`,{encoding:"utf8",flag:"wx"});const written:unknown=JSON.parse(await readFile(temporary,"utf8"));assertShape(written);await rename(temporary,manifestPath);}catch(error){await rm(temporary,{force:true}).catch(()=>undefined);throw error;}
}
type ReviewProvenance={reviewer:string;description_provider?:string;description_model?:string;description_version?:string};
export async function saveReview(assetId:string,input:unknown,manifestPath=MANIFEST_PATH,provenance:ReviewProvenance={reviewer:REVIEWER,description_provider:"manual",description_model:"human-reviewed",description_version:"manual-v1"}){
  if(!UUID.test(assetId)||!input||typeof input!=="object"||Array.isArray(input))throw new Error("Invalid review request");
  const keys=Object.keys(input);if(keys.some(k=>!(REVIEW_FIELDS as readonly string[]).includes(k))||keys.length!==REVIEW_FIELDS.length)throw new Error("Unsupported review fields");
  const values=input as Record<string,unknown>;for(const key of REVIEW_FIELDS)if(typeof values[key]!=="string")throw new Error(`Invalid ${key}`);
  const requiredError=validateReviewFields({content_type:String(values.content_type),ai_description:String(values.ai_description),short_caption:String(values.short_caption)});if(requiredError)throw new Error(requiredError);
  const manifest=await loadReviewManifest(manifestPath),index=manifest.assets.findIndex(x=>x.asset_id===assetId);if(index>=0&&index<5)throw new Error("Existing benchmark seeds are read-only");if(index<0)throw new Error("Unknown benchmark asset");
  if(!([REVIEWER,EVIDENCE_REVIEWER] as readonly string[]).includes(provenance.reviewer))throw new Error("Unsupported review provenance");
  const original=manifest.assets[index];manifest.assets[index]={...original,...Object.fromEntries(REVIEW_FIELDS.map(k=>[k,String(values[k]).trim()])),reviewed_by:provenance.reviewer,reviewed_at:singaporeTimestamp(),...(provenance.description_provider?{description_provider:provenance.description_provider}:{}),...(provenance.description_model?{description_model:provenance.description_model}:{}),...(provenance.description_version?{description_version:provenance.description_version}:{})};assertShape(manifest);
  await writeManifestSafely(manifestPath,manifest);return manifest.assets[index];
}
export async function saveEvidenceReview(assetId:string,input:unknown,manifestPath=MANIFEST_PATH){return saveReview(assetId,input,manifestPath,{reviewer:EVIDENCE_REVIEWER,description_provider:"codex-assisted",description_model:"evidence-reviewed",description_version:"codex-review-v1"})}
export async function correctReviewedAssetEvidence(assetId:string,input:unknown,manifestPath=MANIFEST_PATH){
  if(!UUID.test(assetId)||!input||typeof input!=="object"||Array.isArray(input))throw new Error("Invalid review request");
  const values=input as Record<string,unknown>;if(Object.keys(values).some(k=>!(REVIEW_FIELDS as readonly string[]).includes(k))||Object.keys(values).length!==REVIEW_FIELDS.length)throw new Error("Unsupported review fields");
  for(const key of REVIEW_FIELDS)if(typeof values[key]!=="string")throw new Error(`Invalid ${key}`);
  const requiredError=validateReviewFields({content_type:String(values.content_type),ai_description:String(values.ai_description),short_caption:String(values.short_caption)});if(requiredError)throw new Error(requiredError);
  const manifest=await loadReviewManifest(manifestPath),index=manifest.assets.findIndex(x=>x.asset_id===assetId);if(index<5)throw new Error("Existing benchmark seeds are read-only");if(index<0)throw new Error("Unknown benchmark asset");
  const original=manifest.assets[index];if(original.reviewed_by!==REVIEWER||!original.reviewed_at)throw new Error("Only an existing Nusaiba review can use evidence correction");
  manifest.assets[index]={...original,...Object.fromEntries(REVIEW_FIELDS.map(k=>[k,String(values[k]).trim()])),description_provider:"codex-assisted",description_model:"evidence-reviewed",description_version:"codex-review-v1",evidence_reviewed_by:EVIDENCE_REVIEWER,evidence_reviewed_at:singaporeTimestamp()};
  await writeManifestSafely(manifestPath,manifest);return manifest.assets[index];
}
export async function recordBenchmarkOwnerApproval(manifestPath=MANIFEST_PATH){
  const manifest=await loadReviewManifest(manifestPath),approvedAt=singaporeTimestamp();
  for(let index=5;index<manifest.assets.length;index++){
    if(!manifest.assets[index].reviewed_by||!manifest.assets[index].reviewed_at)throw new Error("Owner approval requires every benchmark review to be complete");
    manifest.assets[index]={...manifest.assets[index],owner_approved_by:"Project owner",owner_approved_at:approvedAt};
  }
  await writeManifestSafely(manifestPath,manifest);return{approved:15,owner_approved_at:approvedAt};
}
