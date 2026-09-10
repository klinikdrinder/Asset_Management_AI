import type{SupabaseClient}from"@supabase/supabase-js";
import type{ResultCountMetadata}from"./result-count-controller";

export const SEARCH_RESPONSE_IMPLEMENTATION_VERSION="kdi_database_grounded_response_v1";
export const SEARCH_RESPONSE_SCHEMA_VERSION="kdi_search_response_v1";
export const GROUNDING_MODE="DATABASE_REQUIRED" as const;
type State="OBSERVED"|"FALSE"|"UNKNOWN"|"NOT_APPLICABLE";
type Row=Record<string,any>;
export type GroundedCandidate={asset_id:string;score?:number|null;matched_scene_id?:string|null;matched_start_seconds?:number|null;matched_end_seconds?:number|null};
export interface GroundedResponseRepository{
  authorize(userId:string,assetIds:string[]):Promise<Set<string>>;assets(ids:string[]):Promise<Row[]>;profiles(ids:string[]):Promise<Row[]>;
  assertions(ids:string[]):Promise<Row[]>;evidence(assertionIds:string[]):Promise<Row[]>;documents(ids:string[]):Promise<Row[]>;
  transcripts(ids:string[]):Promise<Row[]>;ocr(ids:string[]):Promise<Row[]>;
}
const many=async(q:any)=>{const{data,error}=await q;if(error)throw error;return data??[]};
export class SupabaseGroundedResponseRepository implements GroundedResponseRepository{
  constructor(private db:SupabaseClient){}
  async authorize(userId:string,assetIds:string[]):Promise<Set<string>>{const{data,error}=await this.db.rpc("phase18_authorize_candidates_for",{p_user_id:userId,p_asset_ids:assetIds});if(error)throw error;return new Set<string>((data??[]).filter((x:any)=>x.discover&&x.view_metadata&&x.preview).map((x:any)=>String(x.asset_id)))}
  assets(ids:string[]){return many(this.db.from("assets").select("id,file_name,mime_type").in("id",ids))}
  profiles(ids:string[]){return many(this.db.from("asset_ai_profiles").select("asset_id,short_description,detailed_description,specific_treatment").in("asset_id",ids))}
  assertions(ids:string[]){return many(this.db.from("semantic_assertions").select("id,asset_id,scene_id,event_id,layer_id,predicate,canonical_concept_code,semantic_state,search_critical").in("asset_id",ids).eq("active",true).is("superseded_by",null))}
  evidence(ids:string[]){return ids.length?many(this.db.from("semantic_assertion_evidence").select("id,assertion_id,scene_id,event_id,start_time,end_time").in("assertion_id",ids)):Promise.resolve([])}
  documents(ids:string[]){return many(this.db.from("search_document_builds").select("id,asset_id,document_fingerprint").in("asset_id",ids).eq("document_type","ASSET").eq("active",true).eq("stale",false))}
  transcripts(ids:string[]){return many(this.db.from("asset_transcript_chunks").select("id,asset_id,scene_id,start_seconds,end_seconds,normalized_text,raw_text").in("asset_id",ids).eq("search_status","ACCEPTED_FOR_SEARCH"))}
  ocr(ids:string[]){return many(this.db.from("ocr_observations").select("id,asset_id,scene_id,timestamp_seconds,end_time,normalized_text,raw_text").in("asset_id",ids).eq("search_status","ACCEPTED_FOR_SEARCH"))}
}
const media=(mime:unknown)=>String(mime??"").startsWith("video/")?"VIDEO":String(mime??"").startsWith("image/")?"IMAGE":String(mime??"").startsWith("audio/")?"AUDIO":"DOCUMENT";
const stored=(value:unknown)=>typeof value==="string"&&value.trim()?{status:"STORED" as const,value}:{status:"NOT_STORED" as const,value:null};
const stem=(x:string)=>x.toLowerCase().replace(/_/g," ").replace(/(ing|ion|ed|s)$/," ").trim();
export async function buildDatabaseGroundedResponse(input:{query:string;userId:string;candidates:GroundedCandidate[];count:ResultCountMetadata},repo:GroundedResponseRepository){
  const base={response_version:SEARCH_RESPONSE_SCHEMA_VERSION,implementation_version:SEARCH_RESPONSE_IMPLEMENTATION_VERSION,grounding_mode:GROUNDING_MODE,query:input.query,...input.count};
  if(!input.candidates.length)return{...base,returned_count:0,results:[],zero_result_reason:"NO_RELEVANT_AUTHORIZED_RESULTS",grounding_status:"GROUNDED"};
  try{
    const ordered=[...new Set(input.candidates.map(x=>x.asset_id))],authorized=await repo.authorize(input.userId,ordered),ids=ordered.filter(x=>authorized.has(x));
    if(!ids.length)return{...base,returned_count:0,available_valid_count:0,results:[],zero_result_reason:"NO_RELEVANT_AUTHORIZED_RESULTS",grounding_status:"GROUNDED"};
    const[assets,profiles,assertions,documents,transcripts,ocr]=await Promise.all([repo.assets(ids),repo.profiles(ids),repo.assertions(ids),repo.documents(ids),repo.transcripts(ids),repo.ocr(ids)]);
    const evidence=await repo.evidence(assertions.map(x=>String(x.id))),by=(rows:Row[],key:string)=>{const m=new Map<string,Row[]>();for(const x of rows){const a=m.get(String(x[key]))??[];a.push(x);m.set(String(x[key]),a)}return m};
    const am=new Map(assets.map(x=>[String(x.id),x])),pm=new Map(profiles.map(x=>[String(x.asset_id),x])),asm=by(assertions,"asset_id"),em=by(evidence,"assertion_id"),dm=by(documents,"asset_id"),tm=by(transcripts,"asset_id"),om=by(ocr,"asset_id"),q=input.query.toLowerCase();
    const results=[];for(const candidate of input.candidates){if(!authorized.has(candidate.asset_id))continue;const a=am.get(candidate.asset_id);if(!a)throw Error("AUTHORIZED_ASSET_HYDRATION_MISSING");const facts=(asm.get(candidate.asset_id)??[]).filter(x=>["OBSERVED","FALSE","UNKNOWN","NOT_APPLICABLE"].includes(x.semantic_state));const observed=facts.filter(x=>x.semantic_state==="OBSERVED"&&x.canonical_concept_code);const matched=[...observed].sort((x,y)=>Number(q.includes(stem(String(y.canonical_concept_code))))-Number(q.includes(stem(String(x.canonical_concept_code)))||0)||Number(y.search_critical)-Number(x.search_critical)).slice(0,4);const unknownTreatment=facts.some(x=>x.layer_id==="TREATMENT_PROCEDURE"&&x.semantic_state==="UNKNOWN");
      const p=pm.get(candidate.asset_id),docs=dm.get(candidate.asset_id)??[],labels=matched.map(x=>String(x.canonical_concept_code).toLowerCase().replace(/_/g," "));let reason=labels.length?`Stored semantic evidence identifies ${labels.join(", ")}.`:"Stored database evidence supports this ranked match.";if(unknownTreatment||(/\b(exact|specific)\s+treatment\b/i.test(input.query)&&!p?.specific_treatment))reason+=" The specific treatment could not be reliably determined from stored evidence.";
      const wantTranscript=/\b(transcript|speech|spoken|audio)\b/i.test(input.query),wantOcr=/\b(ocr|text|words|written|visible text)\b/i.test(input.query);
      results.push({rank:results.length+1,asset_id:candidate.asset_id,filename:a.file_name,media_type:media(a.mime_type),short_description:stored(p?.short_description),detailed_description:stored(p?.detailed_description),specific_treatment:stored(p?.specific_treatment),match_reason:reason,matched_concepts:matched.map(x=>({code:x.canonical_concept_code,state:x.semantic_state as State})),semantic_facts:facts.map(x=>({layer:x.layer_id,predicate:x.predicate,code:x.canonical_concept_code,state:x.semantic_state as State})),relevant_segment:candidate.matched_scene_id?{scene_id:candidate.matched_scene_id,start_time:candidate.matched_start_seconds??null,end_time:candidate.matched_end_seconds??null}:null,transcript:wantTranscript?(tm.get(candidate.asset_id)??[]).map(x=>({status:"STORED",text:x.normalized_text||x.raw_text,start_time:x.start_seconds,end_time:x.end_seconds})):[],ocr:wantOcr?(om.get(candidate.asset_id)??[]).map(x=>({status:"STORED",text:x.normalized_text||x.raw_text,start_time:x.timestamp_seconds,end_time:x.end_time})):[],score:candidate.score??null,grounding:{asset_id:candidate.asset_id,semantic_assertion_ids:facts.map(x=>x.id),evidence_ids:facts.flatMap(x=>(em.get(String(x.id))??[]).map(e=>e.id)),scene_ids:[...new Set(facts.map(x=>x.scene_id).filter(Boolean))],event_ids:[...new Set(facts.map(x=>x.event_id).filter(Boolean))],search_document_ids:docs.map(x=>x.id)}})}
    return{...base,returned_count:results.length,available_valid_count:Math.max(0,input.count.available_valid_count-(ordered.length-ids.length)),results,zero_result_reason:results.length?null:"NO_RELEVANT_AUTHORIZED_RESULTS",grounding_status:"GROUNDED"};
  }catch{return{...base,returned_count:0,results:[],zero_result_reason:null,grounding_status:"DATABASE_UNAVAILABLE",error:"Stored KDI asset intelligence could not be retrieved."}}
}
