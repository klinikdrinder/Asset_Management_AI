/**
 * The one canonical production search entry point.
 *
 * Every production search request terminates here. There is no version branching, no silent
 * fallback to an earlier engine, and no second parser: interpretation comes from the canonical
 * query interpreter and retrieval from executeCanonicalSearch. The developer library preview lives
 * behind its own explicitly non-production route and can never serve this endpoint.
 */
import { NextRequest,NextResponse } from "next/server";
import { requireStaffOrAdmin } from "../../auth";
import { ASSET_SELECT,mapAsset } from "../../lib/media/repository";
import { createServiceClient } from "../../lib/supabase/service";
import { sameOrigin } from "../../lib/user-management";
import { interpretQuery } from "../../../db/query-interpreter";
import { executeCanonicalSearch,CANONICAL_SEARCH_VERSION } from "../../../db/canonical-production-retriever";
import { buildDatabaseGroundedResponse,SupabaseGroundedResponseRepository } from "../../../db/database-grounded-search-response";
import { memoryRecord,resolveConversationalSearch,type PriorSearchContext } from "../../../db/conversational-search-memory";

const headers={"Cache-Control":"private, no-store"};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function POST(request:NextRequest){
  if(!sameOrigin(request))return NextResponse.json({error:"Request could not be verified."},{status:403,headers});
  const user=await requireStaffOrAdmin().catch(()=>null); if(!user)return NextResponse.json({error:"Authentication required."},{status:401,headers});
  const body=await request.json().catch(()=>({})) as Record<string,unknown>;
  const raw=typeof body.query==="string"?body.query.trim().slice(0,300):"";
  if(!raw)return NextResponse.json({error:"A search query is required."},{status:400,headers});
  const client=createServiceClient(); let sessionId=typeof body.sessionId==="string"&&uuid.test(body.sessionId)?body.sessionId:null;
  let context:{resolvedQuery:string;filters:Record<string,unknown>;requestedCount:number|null;returnedAssetIds:string[]}|undefined; let priorContext:PriorSearchContext|undefined; let parentQueryId:string|null=null; let sequence=0;
  if(sessionId){
    const {data:session}=await client.from("search_sessions").select("id,user_id,last_activity_at").eq("id",sessionId).eq("user_id",user.userId).eq("status","ACTIVE").maybeSingle();
    if(!session)return NextResponse.json({error:"Search session is unavailable."},{status:404,headers});
    const {data:prior}=await client.from("search_queries").select("id,sequence_number,resolved_query,structured_filters,requested_count").eq("session_id",sessionId).order("sequence_number",{ascending:false}).limit(1).maybeSingle();
    if(prior){ const {data:results}=await client.from("search_results").select("asset_id,rank").eq("search_query_id",prior.id).order("rank",{ascending:true}); parentQueryId=prior.id; sequence=prior.sequence_number+1; const ids=(results||[]).map(r=>r.asset_id); context={resolvedQuery:prior.resolved_query||raw,filters:prior.structured_filters||{},requestedCount:prior.requested_count,returnedAssetIds:ids}; priorContext={sessionId,userId:user.userId,queryId:prior.id,resolvedQuery:prior.resolved_query||raw,filters:prior.structured_filters||{},requestedCount:prior.requested_count,resultAssetIds:ids,lastActivityAt:session.last_activity_at}; }
  }else{
    const {data,error}=await client.from("search_sessions").insert({user_id:user.userId,metadata:{search_authority:CANONICAL_SEARCH_VERSION}}).select("id").single(); if(error||!data)return NextResponse.json({error:"Search session could not be created."},{status:500,headers}); sessionId=data.id;
  }
  const canonicalPlan=await interpretQuery(raw);
  const resolution=resolveConversationalSearch({query:raw,sessionId:sessionId!,userId:user.userId,prior:priorContext});
  if(resolution.status!=="RESOLVED")return NextResponse.json({sessionId,grounding_mode:"DATABASE_REQUIRED",context_status:resolution.status,context_mode:resolution.context_mode,results:[]},{status:409,headers});
  // Retained for conversational scope only; the canonical parser owns interpretation.
  const resolvedContext=resolution.context_mode==="NEW_QUERY"?undefined:{resolvedQuery:resolution.resolved_query,filters:resolution.filters,requestedCount:resolution.requested_count??context?.requestedCount??5,returnedAssetIds:resolution.prior_result_scope};
  const effective=resolution.requested_count??(typeof canonicalPlan.result_request.effective_count==="number"?canonicalPlan.result_request.effective_count:canonicalPlan.result_request.system_default_count);
  const resultRequest={...canonicalPlan.result_request,requested_count:resolution.requested_count,effective_count:effective};
  const contextual=resolution.context_mode!=="NEW_QUERY";
  const {data:q,error:qError}=await client.from("search_queries").insert({session_id:sessionId,parent_query_id:contextual?parentQueryId:null,sequence_number:sequence,raw_query:raw,resolved_query:resolution.resolved_query,query_type:resolution.context_mode==="NEW_QUERY"?"NEW_SEARCH":resolution.context_mode==="CONTINUE"?"COUNT_CHANGE":"REFINEMENT",requested_count:effective,count_explicit:resolution.requested_count!==null,result_offset:0,media_type:resolution.filters.media_type??(canonicalPlan.media.media_type==="ANY"?null:canonicalPlan.media.media_type.toLowerCase()),parsed_intent:canonicalPlan,structured_filters:resolution.filters,semantic_intent:{query:resolution.resolved_query,canonical_query_fingerprint:canonicalPlan.parser_metadata.query_fingerprint,...memoryRecord(resolution)},sort_mode:"RELEVANCE",minimum_relevance:0.08,status:"SEARCHING",resolved_at:new Date().toISOString()}).select("id").single();
  if(qError||!q)return NextResponse.json({error:"Search query could not be recorded."},{status:500,headers});
  try{
    if(resolution.context_mode==="ASSET_REFERENCE"){
      const count={requested_count:1,effective_count:1,returned_count:1,available_valid_count:1,count_source:"EXPLICIT" as const,count_clamped:false};
      const response=await buildDatabaseGroundedResponse({query:raw,userId:user.userId,count,candidates:[{asset_id:resolution.referenced_asset_id!}]},new SupabaseGroundedResponseRepository(client));
      if(response.grounding_status==="DATABASE_UNAVAILABLE"){await client.from("search_queries").update({status:"FAILED"}).eq("id",q.id);return NextResponse.json(response,{status:503,headers})}
      if(response.results.length){await client.from("search_results").insert(response.results.map((item,index)=>({search_query_id:q.id,asset_id:item.asset_id,rank:index+1,overall_score:1,match_reason:"Phase 23 authorized ordinal reference",matched_features:{memory_version:"kdi_conversational_search_memory_v1"},result_group_key:item.asset_id})));}
      await Promise.all([client.from("search_queries").update({status:"COMPLETED"}).eq("id",q.id),client.from("search_sessions").update({last_activity_at:new Date().toISOString()}).eq("id",sessionId).eq("user_id",user.userId)]);
      return NextResponse.json({sessionId,queryId:q.id,context:memoryRecord(resolution),count:{...count,returned_count:response.results.length,available_valid_count:response.results.length},response},{headers});
    }
    const canonical=await executeCanonicalSearch(client,{query:resolution.resolved_query,userId:user.userId,requestedCount:resultRequest.effective_count,queryPlan:canonicalPlan,restrictToAssetIds:resolution.context_mode==="RESULT_SET_REFERENCE"?resolution.prior_result_scope:undefined});
    const controlled=canonical.controlled,rankedCandidates=canonical.eligible_candidates;
    const ids=controlled.candidates.map(item=>item.asset_id),{data:assetRows,error:assetError}=ids.length?await client.from("assets").select(ASSET_SELECT).in("id",ids):{data:[],error:null};if(assetError)throw assetError;
    const rows=new Map((assetRows??[]).map(row=>[String(row.id),row])),items=controlled.candidates.flatMap(item=>{const row=rows.get(item.asset_id);return row?[mapAsset(row,item.authorization.download===true,item.phase19.normalizedScore)]:[]});
    const page={items,total:rankedCandidates.filter(item=>item.phase19.eligible).length,page:1,pageSize:controlled.count.effective_count,totalPages:1};
    const count={...controlled.count,returned_count:items.length,available_valid_count:page.total};
    const response=await buildDatabaseGroundedResponse({query:raw,userId:user.userId,count,candidates:page.items.map(item=>({asset_id:item.id,score:item.matchPercent??null}))},new SupabaseGroundedResponseRepository(client));
    if(response.grounding_status==="DATABASE_UNAVAILABLE"){await client.from("search_queries").update({status:"FAILED"}).eq("id",q.id);return NextResponse.json(response,{status:503,headers})}
    if(page.items.length){const {error}=await client.from("search_results").insert(page.items.map((item,index)=>({search_query_id:q.id,asset_id:item.id,rank:index+1,overall_score:Math.max(0,Math.min(1,(item.matchPercent||0)/100)),match_reason:"KDI grounded deterministic hybrid match",matched_features:{search_version:CANONICAL_SEARCH_VERSION,ranking_version:canonical.fusion_version,channels:controlled.candidates[index]?.channels?.map((hit:any)=>hit.channel)??[],provenance:controlled.candidates[index]?.channels??[]},result_group_key:item.id})));if(error)throw error;}
    await Promise.all([client.from("search_queries").update({status:"COMPLETED"}).eq("id",q.id),client.from("search_sessions").update({last_activity_at:new Date().toISOString()}).eq("id",sessionId).eq("user_id",user.userId)]);
    return NextResponse.json({sessionId,queryId:q.id,searchVersion:CANONICAL_SEARCH_VERSION,queryType:resolution.context_mode,resolvedQuery:resolution.resolved_query,filters:resolution.filters,context:memoryRecord(resolution),...page,count,response},{headers});
  }catch{
    await client.from("search_queries").update({status:"FAILED"}).eq("id",q.id);
    return NextResponse.json({error:"Search is temporarily unavailable."},{status:503,headers});
  }
}
