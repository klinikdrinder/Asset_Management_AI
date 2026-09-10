import {readFileSync} from "node:fs";
import path from "node:path";

function loadEnv(file:string){
  try{return Object.fromEntries(readFileSync(file,"utf8").replace(/^\uFEFF/,"").split(/\r?\n/).flatMap(line=>{
    const match=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    return match?[[match[1],match[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[];
  }))}catch{return{}}
}

const root=path.resolve(process.cwd(),"..");
const rootEnv=loadEnv(path.join(root,".env.local"));
const dashboardEnv=loadEnv(path.join(process.cwd(),".env.local"));
const url=dashboardEnv.NEXT_PUBLIC_SUPABASE_URL||rootEnv.NEXT_PUBLIC_SUPABASE_URL;
const token=[rootEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN,dashboardEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN]
  .find(value=>value?.startsWith("sbp_"));
if(!url||!token)throw new Error("Supabase management configuration unavailable");

const ref=new URL(url).hostname.split(".")[0];
const migrations=[
  "20260903053907_kdi_search_v4_canonical_authority.sql",
  "20260903054706_kdi_search_v4_readiness_compatibility_fix.sql",
  "20260904090000_unify_kdi_canonical_search_authority.sql",
];

for(const migration of migrations){
  const sql=readFileSync(path.join(root,"supabase","migrations",migration),"utf8");
  const response=await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`,{
    method:"POST",
    headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},
    body:JSON.stringify({query:sql}),
  });
  if(!response.ok)throw new Error(`CANONICAL_SEARCH_MIGRATION_FAILED:${migration}:${response.status}:${await response.text()}`);
  console.log(JSON.stringify({status:"APPLIED",migration,secrets_printed:false}));
}
