import {createClient} from "@supabase/supabase-js";import {mkdir,writeFile} from "node:fs/promises";import {resolve} from "node:path";
import {encodePhase17Query} from "../db/phase17-query-encoder";
import {interpretQuery} from "../db/query-interpreter";
import {classifyRequirements} from "../db/requirement-classifier";
import {expandQuery} from "../db/query-expander";
import {retrieveCandidates} from "../db/candidate-retriever";

const url=process.env.NEXT_PUBLIC_SUPABASE_URL,key=process.env.SUPABASE_SERVICE_ROLE_KEY;
if(!url||!key)throw new Error("credentials unavailable");
const db=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}});
const query="neck injection",vectors=await encodePhase17Query(query),p=await interpretQuery(query),r=classifyRequirements(p),e=expandQuery(p,r);
const started=performance.now(),set=await retrieveCandidates(db,{queryPlan:p,requirementPlan:r,expandedQueryPlan:e,queryVectors:vectors,requestedCount:10}),retrieval_ms=performance.now()-started,report={query,encoder:vectors.provenance,retrieval_ms,candidates:set.candidates.map((x:any)=>({filename:x.filename,asset_id:x.asset_id,channels:x.channels.map((h:any)=>({channel:h.channel,rank:h.channel_rank,similarity:h.raw_similarity,scene_id:h.scene_id,event_id:h.event_id,keyframe_id:h.keyframe_id,time_start:h.time_start,time_end:h.time_end,dimension:h.embedding_dimension,family:h.embedding_family}))})),diagnostics:set.diagnostics};const dir=resolve(import.meta.dirname,"../../reports/semantic-search/phase17");await mkdir(dir,{recursive:true});await writeFile(resolve(dir,"live_neck_injection_smoke.json"),JSON.stringify(report,null,2)+"\n");await writeFile(resolve(dir,"latency.json"),JSON.stringify({query,encoder_ms:vectors.provenance.elapsed_ms,retrieval_ms,channels:Object.fromEntries(Object.entries(set.diagnostics.channels).map(([k,v]:any)=>[k,v.elapsed_ms]))},null,2)+"\n");console.log(JSON.stringify({query,retrieval_ms,candidates:report.candidates.map((x:any)=>x.filename),channels:set.diagnostics.channels},null,2));
