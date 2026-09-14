import {readFile} from "node:fs/promises";
import {resolve} from "node:path";

const url=process.env.NEXT_PUBLIC_SUPABASE_URL,token=process.env.SUPABASE_DASHBOARD_ACCESS_TOKEN;
if(!url||!token)throw new Error("Supabase management configuration unavailable");
const ref=new URL(url).hostname.split(".")[0];
const sql=await readFile(resolve(import.meta.dirname,"../../supabase/migrations/20260826034218_phase17_hybrid_embedding_retrieval.sql"),"utf8");
const response=await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`,{method:"POST",headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},body:JSON.stringify({query:sql})});
if(!response.ok)throw new Error(`PHASE17_MIGRATION_FAILED:${response.status}:${await response.text()}`);
console.log(JSON.stringify({status:"APPLIED",migration:"20260826034218_phase17_hybrid_embedding_retrieval.sql",secrets_printed:false}));
