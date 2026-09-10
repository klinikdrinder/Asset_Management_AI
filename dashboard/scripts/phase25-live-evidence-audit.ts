import { createClient } from "@supabase/supabase-js";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const PILOT = ["DSC03753.JPG","DSC08097.JPG","IMG_0493.MP4","IMG_0531.MP4","IMG_1148.MP4","IMG_1160.MP4","IMG_1238.MP4","IMG_2963.MP4","IMG_3429.MP4","IMG_9871.MOV"];
function env(file:string){try{return Object.fromEntries(readFileSync(file,"utf8").replace(/^\uFEFF/,"").split(/\r?\n/).flatMap(line=>{const m=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return{}}}
const root=path.resolve(import.meta.dirname,"../.."), local={...env(path.join(root,".env.local")),...env(path.join(root,"dashboard",".env.local"))} as Record<string,string>;
const url=local.NEXT_PUBLIC_SUPABASE_URL,key=local.SUPABASE_SERVICE_ROLE_KEY;if(!url||!key)throw Error("DATABASE_CONFIGURATION_UNAVAILABLE");
const db=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}});
async function rows(table:string,select:string,assetIds:string[]){const q=await db.from(table).select(select).in("asset_id",assetIds);if(q.error)throw Error(`${table}:${q.error.message}`);return q.data??[]}
const assetsQ=await db.from("assets").select("id,file_name,mime_type").in("file_name",PILOT);if(assetsQ.error)throw assetsQ.error;
const assets=assetsQ.data??[];if(assets.length!==10||JSON.stringify(assets.map(x=>x.file_name).sort())!==JSON.stringify([...PILOT].sort()))throw Error("PILOT_MANIFEST_MISMATCH");
const ids=assets.map(x=>x.id);
const [layers,assertions,evidence,scenes,events,narratives,transcripts,ocr,profiles]=await Promise.all([
  rows("asset_semantic_layers","id,asset_id,layer_id,applicability,semantic_state,processing_status,completeness_status,semantic_spec_version,active",ids),
  rows("semantic_assertions","id,asset_id,scene_id,event_id,layer_id,predicate,semantic_state,canonical_concept_code,value_json,confidence,human_review_status,active,source_fingerprint",ids),
  rows("semantic_assertion_evidence","id,assertion_id,asset_id,scene_id,event_id,evidence_type,polarity,completeness,keyframe_id,transcript_chunk_id,ocr_observation_id,start_time,end_time,evidence_score,source_fingerprint",ids),
  rows("asset_scenes","id,asset_id,scene_index,start_seconds,end_seconds,literal_description,short_description,semantic_label,semantic_state,semantic_version,canonical_active,review_status",ids),
  rows("asset_events","id,asset_id,scene_id,event_type,canonical_action,semantic_state,start_time,end_time,technical_only,semantic_version,review_status",ids),
  rows("semantic_narratives","id,asset_id,scene_id,event_id,narrative_type,text,search_status,human_review_status,active,semantic_spec_fingerprint",ids),
  rows("asset_transcript_chunks","id,asset_id,start_seconds,end_seconds,transcript_text,summary,topics,transcription_status",ids),
  rows("ocr_observations","id,asset_id,scene_id,keyframe_id,timestamp_seconds,raw_text,normalized_text,text_type,confidence",ids),
  rows("asset_ai_profiles","asset_id,short_description,detailed_description",ids),
]);
const claimQ=await db.from("narrative_claims").select("id,narrative_id,claim_text,modality_source,confidence,search_critical,review_status").in("narrative_id",narratives.map((x:any)=>x.id));if(claimQ.error)throw claimQ.error;const claims=claimQ.data??[];const byId=new Map(assets.map(a=>[a.id,a.file_name]));
const output={generated_at:new Date().toISOString(),source:"LIVE_SUPABASE_STORED_EVIDENCE_ONLY",project_ref:"wcqqjpndlwsvatjuqnol",pilot_manifest:PILOT,assets:assets.map(a=>({ ...a,
  layers:layers.filter((x:any)=>x.asset_id===a.id),assertions:assertions.filter((x:any)=>x.asset_id===a.id),evidence:evidence.filter((x:any)=>x.asset_id===a.id),scenes:scenes.filter((x:any)=>x.asset_id===a.id),events:events.filter((x:any)=>x.asset_id===a.id),narratives:narratives.filter((x:any)=>x.asset_id===a.id),claims:claims.filter((x:any)=>narratives.some((n:any)=>n.asset_id===a.id&&n.id===x.narrative_id)),transcripts:transcripts.filter((x:any)=>x.asset_id===a.id),ocr:ocr.filter((x:any)=>x.asset_id===a.id),profiles:profiles.filter((x:any)=>x.asset_id===a.id)})),counts:{assets:assets.length,layers:layers.length,assertions:assertions.length,evidence:evidence.length,scenes:scenes.length,events:events.length,narratives:narratives.length,claims:claims.length,transcripts:transcripts.length,ocr:ocr.length,profiles:profiles.length},asset_id_filename:Object.fromEntries([...byId])};
const dir=path.join(root,"reports","semantic-search","phase25");mkdirSync(dir,{recursive:true});writeFileSync(path.join(dir,"live_evidence_audit.json"),JSON.stringify(output,null,2)+"\n");console.log(JSON.stringify(output.counts));
