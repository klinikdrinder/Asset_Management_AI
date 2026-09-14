import {createHash} from "node:crypto";
import ontology from "../../config/semantic-search/kdi_people_appearance_ontology_v1.json";

export const PEOPLE_APPEARANCE_CONTRACT_VERSION=ontology.version;
export type Assertion={id:string;asset_id:string;scene_id:string|null;keyframe_id?:string|null;value_text?:string|null;canonical_concept_code?:string|null;confidence?:number|null;human_review_status?:string|null;analysis_run_id?:string|null};
export type Context={personId:string;assetId:string;sceneId:string;existingAuthorityRank?:number};
export type Materialization={person:{id:string;asset_id:string;scene_id:string;canonical_person_role?:string;gender_presentation?:string};appearance:{scene_person_id:string;asset_id:string;scene_id:string;canonical_hair_color?:string;canonical_hair_length?:string;hair_density?:string;hairline_pattern?:string;clothing_type?:string;clothing_color?:string;posture?:string;authority_rank:number;source_type:"HUMAN_REVIEW"|"DERIVED_ASSERTION";appearance_confidence:number;materialization_key:string};evidence:Array<{assertion_id:string;attribute_name:string;attribute_value:unknown;confidence:number;authority_rank:number;materialization_key:string}>};
const norm=(x:string)=>x.trim().toLowerCase().replace(/\s+/g," ");
const synonym=(category:keyof typeof ontology.synonyms,text:string)=>Object.entries(ontology.synonyms[category] as Record<string,string>).sort((a,b)=>b[0].length-a[0].length).find(([surface])=>new RegExp(`\\b${surface.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")}\\b`,`i`).test(text))?.[1];
export function materializePersonAppearance(assertions:Assertion[],context:Context):Materialization|null{
  const scoped=assertions.filter(x=>x.asset_id===context.assetId&&x.scene_id===context.sceneId&&Boolean(x.value_text||x.canonical_concept_code));if(!scoped.length)return null;
  const text=norm(scoped.map(x=>`${x.canonical_concept_code??""} ${x.value_text??""}`).join(" "));
  const role=synonym("person_role",text),gender=synonym("gender_presentation",text),hairline=synonym("hairline_pattern",text),color=synonym("clothing_color",text),clothing=synonym("clothing_type",text),posture=synonym("posture",text);
  if(![role,gender,hairline,color,clothing,posture].some(Boolean))return null;
  const reviewed=scoped.some(x=>x.human_review_status==="HUMAN_APPROVED"),rank=reviewed?100:40;if(rank<(context.existingAuthorityRank??0))return null;
  const confidence=Math.min(...scoped.map(x=>Number(x.confidence??0)));
  const core={contract:PEOPLE_APPEARANCE_CONTRACT_VERSION,person:context.personId,scene:context.sceneId,assertions:scoped.map(x=>x.id).sort()};const key=createHash("sha256").update(JSON.stringify(core)).digest("hex");
  const attrs:Record<string,string|undefined>={canonical_person_role:role,gender_presentation:gender,hairline_pattern:hairline,clothing_color:color,clothing_type:clothing,posture};
  return {person:{id:context.personId,asset_id:context.assetId,scene_id:context.sceneId,...(role?{canonical_person_role:role}:{}),...(gender?{gender_presentation:gender}:{})},appearance:{scene_person_id:context.personId,asset_id:context.assetId,scene_id:context.sceneId,...(hairline?{hairline_pattern:hairline}:{}),...(color?{clothing_color:color}:{}),...(clothing?{clothing_type:clothing}:{}),...(posture?{posture}:{}),authority_rank:rank,source_type:reviewed?"HUMAN_REVIEW":"DERIVED_ASSERTION",appearance_confidence:confidence,materialization_key:key},evidence:Object.entries(attrs).filter((x):x is [string,string]=>Boolean(x[1])).map(([attribute_name,attribute_value])=>({assertion_id:scoped[0].id,attribute_name,attribute_value,confidence,authority_rank:rank,materialization_key:createHash("sha256").update(`${key}:${attribute_name}`).digest("hex")}))};
}
