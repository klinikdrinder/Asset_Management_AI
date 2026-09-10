export const CONVERSATIONAL_SEARCH_MEMORY_VERSION="kdi_conversational_search_memory_v1";
export const SEARCH_CONTEXT_TTL_MS=30*60*1000;

export type ContextMode="NEW_QUERY"|"CONTINUE"|"NARROW"|"MODIFY"|"RESULT_SET_REFERENCE"|"ASSET_REFERENCE"|"UNRESOLVED";
export type PriorSearchContext={sessionId:string;userId:string;queryId:string;resolvedQuery:string;filters:Record<string,string>;requestedCount:number;resultAssetIds:string[];lastActivityAt:string};
export type ContextResolution={context_mode:ContextMode;status:"RESOLVED"|"CONTEXT_NOT_AVAILABLE"|"CONTEXT_EXPIRED"|"ORDINAL_OUT_OF_RANGE";prior_query_id:string|null;resolved_query:string;filters:Record<string,string>;requested_count:number|null;prior_result_scope:string[];referenced_asset_id:string|null;reference_kind:"NONE"|"SHORT_DESCRIPTION"|"DETAILED_DESCRIPTION"|"ANATOMY"|"ACTION"|"TREATMENT"};

const ordinal=(q:string,count:number)=>{const m=q.match(/\b(?:the\s+)?(first|second|third|fourth|fifth|last|\d+(?:st|nd|rd|th))\s+(?:one|result|file|asset)?\b/i);if(!m)return null;if(m[1].toLowerCase()==="last")return count;const words:Record<string,number>={first:1,second:2,third:3,fourth:4,fifth:5};return words[m[1].toLowerCase()]??Number.parseInt(m[1],10)};
const countOf=(q:string)=>{const words:Record<string,number>={one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10};const m=q.match(/\b(?:give me|show me|top|best|return|need)\s+(?:(?:only|the|top|best)\s+)*(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b/i);return m?(words[m[1].toLowerCase()]??Number(m[1])):null};
const referenceKind=(q:string):ContextResolution["reference_kind"]=>/detailed|master/i.test(q)?"DETAILED_DESCRIPTION":/short description/i.test(q)?"SHORT_DESCRIPTION":/treatment/i.test(q)?"TREATMENT":/anatomy|body area/i.test(q)?"ANATOMY":/action|happening/i.test(q)?"ACTION":"NONE";
const clean=(q:string)=>q.trim().replace(/\s+/g," ").slice(0,300);
const unique=(ids:string[])=>[...new Set(ids)];

export function resolveConversationalSearch(input:{query:string;sessionId:string;userId:string;prior?:PriorSearchContext;now?:Date}):ContextResolution{
  const q=clean(input.query), prior=input.prior, base={prior_query_id:prior?.queryId??null,prior_result_scope:unique(prior?.resultAssetIds??[]),referenced_asset_id:null,reference_kind:referenceKind(q)};
  const reference=/\b(?:the\s+)?(first|second|third|fourth|fifth|last|\d+(?:st|nd|rd|th))\s+(?:one|result|file|asset)?\b/i.test(q);
  const follow=/^(?:only|actually|exclude|without|from those|same search|what about|give me|top|best|return)\b/i.test(q)||reference||/\bones?\s*\??$/i.test(q);
  if(!prior){return{...base,context_mode:follow?"UNRESOLVED":"NEW_QUERY",status:follow?"CONTEXT_NOT_AVAILABLE":"RESOLVED",resolved_query:q,filters:{},requested_count:countOf(q)}};
  if(prior.sessionId!==input.sessionId||prior.userId!==input.userId)return{...base,context_mode:"UNRESOLVED",status:"CONTEXT_NOT_AVAILABLE",resolved_query:q,filters:{},requested_count:null,prior_result_scope:[]};
  if((input.now??new Date()).getTime()-new Date(prior.lastActivityAt).getTime()>SEARCH_CONTEXT_TTL_MS)return{...base,context_mode:"UNRESOLVED",status:"CONTEXT_EXPIRED",resolved_query:q,filters:{},requested_count:null,prior_result_scope:[]};
  if(reference){const n=ordinal(q,base.prior_result_scope.length);if(!n||n>base.prior_result_scope.length)return{...base,context_mode:"UNRESOLVED",status:"ORDINAL_OUT_OF_RANGE",resolved_query:q,filters:{...prior.filters},requested_count:null};return{...base,context_mode:"ASSET_REFERENCE",status:"RESOLVED",resolved_query:prior.resolvedQuery,filters:{...prior.filters},requested_count:1,referenced_asset_id:base.prior_result_scope[n-1]};}
  const resultSet=/\bfrom those\b/i.test(q), same=/\bsame search\b/i.test(q), count=countOf(q);
  const media=/\bvideos?\b/i.test(q)?"video":/\b(images?|photos?)\b/i.test(q)?"image":null;
  const neck=/\bneck\b/i.test(q), lower=/\blower[- ]?face\b/i.test(q);
  const excludeNeck=/\b(?:exclude|without)\s+(?:the\s+)?neck\b/i.test(q);
  if(follow||same||resultSet){const filters={...prior.filters};if(media)filters.media_type=media;if(lower)filters.anatomy="LOWER_FACE";else if(neck&&!excludeNeck)filters.anatomy="NECK";if(excludeNeck){delete filters.anatomy;filters.excluded_anatomy="NECK"}const mode:ContextMode=resultSet?"RESULT_SET_REFERENCE":lower||/\bactually\b/i.test(q)?"MODIFY":media||neck||excludeNeck?"NARROW":"CONTINUE";return{...base,context_mode:mode,status:"RESOLVED",resolved_query:prior.resolvedQuery,filters,requested_count:count??prior.requestedCount};}
  return{...base,context_mode:"NEW_QUERY",status:"RESOLVED",resolved_query:q,filters:{},requested_count:count};
}

export function memoryRecord(resolution:ContextResolution){return{implementation_version:CONVERSATIONAL_SEARCH_MEMORY_VERSION,context_mode:resolution.context_mode,context_status:resolution.status,prior_query_id:resolution.prior_query_id,prior_result_scope:resolution.prior_result_scope,referenced_asset_id:resolution.referenced_asset_id,reference_kind:resolution.reference_kind};}
