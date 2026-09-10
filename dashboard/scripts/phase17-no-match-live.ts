import {createClient} from "@supabase/supabase-js";
import {encodePhase17Queries} from "../db/phase17-query-encoder";
const queries=["airplane cockpit","wedding ceremony","football stadium","underwater coral reef"];
const url=process.env.NEXT_PUBLIC_SUPABASE_URL,key=process.env.SUPABASE_SERVICE_ROLE_KEY;if(!url||!key)throw Error("credentials unavailable");
const db=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}}),vectors=await encodePhase17Queries(queries),rows=[];
for(let i=0;i<queries.length;i++){const channels:any={};for(const [representation,vector,dimension]of [["TEXT_ASSET",vectors[i].text,384],["VISUAL_ASSET",vectors[i].visual,512]]as const){const q=await db.rpc("match_phase17_semantic_embeddings",{query_embedding:vector,requested_representation:representation,requested_provider:dimension===384?"sentence_transformers":"open_clip",requested_model:dimension===384?"intfloat/multilingual-e5-small":"ViT-B-32",requested_model_version:dimension===384?"hf-main-pinned-runtime-v1":"laion2b_s34b_b79k",requested_dimension:dimension,result_limit:3,minimum_similarity:-1});if(q.error)throw q.error;channels[representation]=(q.data??[]).map((x:any)=>({filename:x.filename,similarity:x.raw_similarity}))}rows.push({query:queries[i],channels})}
console.log(JSON.stringify(rows,null,2));
