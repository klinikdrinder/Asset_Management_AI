import type {SupabaseClient} from "@supabase/supabase-js";
import {interpretQuery} from "./query-interpreter";
import {classifyRequirements} from "./requirement-classifier";
import {expandQuery} from "./query-expander";
import {retrieveCandidates,CANDIDATE_RETRIEVER_VERSION} from "./candidate-retriever";
import {authorizeCandidates,CANDIDATE_AUTHORIZER_VERSION} from "./candidate-authorizer";
import {loadRerankingEvidence,rerankAuthorizedCandidates,DETERMINISTIC_RERANKER_VERSION} from "./deterministic-reranker";
import {encodePhase17Query} from "./phase17-query-encoder";
import {applyResultCount} from "./result-count-controller";
import {SEARCH_VOCABULARY_VERSION} from "./search-vocabulary-registry";

export const CANONICAL_SEARCH_VERSION="KDI_CANONICAL_SEMANTIC_SEARCH";
export const CANONICAL_SEARCH_SCHEMA_VERSION="kdi_canonical_search_result_v1";

export type CanonicalSearchInput={
  query:string;
  userId:string;
  requestedCount?:number|null;
  queryPlan?:any;
  mediaType?:"IMAGE"|"VIDEO"|"DOCUMENT"|null;
  extension?:string|null;
  restrictToAssetIds?:string[];
};

/** The sole production retrieval orchestration. It performs no semantic writes. */
export async function executeCanonicalSearch(db:SupabaseClient,input:CanonicalSearchInput){
  const query=input.query.trim().slice(0,300);
  if(!query)throw new Error("EMPTY_SEARCH_QUERY");
  const plan=input.queryPlan??await interpretQuery(query);
  if(input.mediaType)plan.media={...plan.media,media_type:input.mediaType};
  if(input.extension)plan.media={...plan.media,extension:input.extension};
  const requirementPlan=classifyRequirements(plan);
  const expandedPlan=expandQuery(plan,requirementPlan);
  const vectors=await encodePhase17Query(query);
  const effective=Math.max(1,Math.min(100,input.requestedCount??plan.result_request.effective_count??plan.result_request.system_default_count??5));
  const retrieved=await retrieveCandidates(db,{queryPlan:plan,requirementPlan,expandedQueryPlan:expandedPlan,queryVectors:vectors,requestedCount:effective});
  const authorized=await authorizeCandidates(db,retrieved,input.userId);
  const evidence=await loadRerankingEvidence(db,authorized);
  const ranked=rerankAuthorizedCandidates(authorized,requirementPlan,expandedPlan,evidence,effective);
  const scope=input.restrictToAssetIds?new Set(input.restrictToAssetIds):null;
  const eligible=scope?ranked.candidates.filter(x=>scope.has(x.asset_id)):ranked.candidates;
  const request={...plan.result_request,requested_count:input.requestedCount??plan.result_request.requested_count,effective_count:effective};
  const controlled=applyResultCount(eligible,request,{isAuthorized:x=>x.authorization?.discover===true,isEligible:x=>x.phase19.eligible===true});
  return {
    schema_version:CANONICAL_SEARCH_SCHEMA_VERSION,
    search_version:CANONICAL_SEARCH_VERSION,
    semantic_schema_version:"kdi_semantic_18_layer_v1",
    ontology_version:"kdi_semantic_ontology_v1",
    text_embedding:{provider:"sentence_transformers",model:"intfloat/multilingual-e5-small",model_version:"hf-main-pinned-runtime-v1",dimensions:384,query_format:"query: {normalized query}"},
    visual_embedding:{provider:"open_clip",model:"ViT-B-32",model_version:"laion2b_s34b_b79k",dimensions:512},
    fusion_version:DETERMINISTIC_RERANKER_VERSION,
    versions:{retriever:CANDIDATE_RETRIEVER_VERSION,authorizer:CANDIDATE_AUTHORIZER_VERSION,reranker:DETERMINISTIC_RERANKER_VERSION},
    query_plan:plan,
    requirement_plan:requirementPlan,
    expanded_query_plan:expandedPlan,
    encoder_provenance:vectors.provenance,
    retrieved,
    authorized,
    ranked,
    eligible_candidates:eligible,
    controlled,
    /** One explanation of the search, assembled from the run that just happened rather than from a
     * parallel debug engine. Callers decide whether to surface it; it carries no clinical text,
     * no credentials and no raw vectors. */
    diagnostics:{
      vocabulary_version:SEARCH_VOCABULARY_VERSION,
      parsed_intent:plan.intent,
      requested_count:request.requested_count,
      effective_count:effective,
      hard_constraints:(requirementPlan.hard_constraints??[]).map((r:any)=>r.canonical_code??r.field),
      exclusions:(requirementPlan.hard_exclusions??[]).map((r:any)=>r.canonical_code??r.field),
      strong_requirements:(requirementPlan.strong_requirements??[]).map((r:any)=>r.canonical_code??r.field),
      canonical_concepts:[...new Set((expandedPlan.requirements??[]).flatMap((r:any)=>r.canonical_code?[r.canonical_code]:[]))],
      candidates_per_channel:(retrieved.diagnostics as any)?.channels??{},
      candidates_retrieved:retrieved.candidates.length,
      authorization_removed:retrieved.candidates.length-authorized.candidates.length,
      scope_restricted_removed:ranked.candidates.length-eligible.length,
      returned:controlled.candidates.length,
      final_asset_ids:controlled.candidates.map((x:any)=>x.asset_id),
    },
  };
}
