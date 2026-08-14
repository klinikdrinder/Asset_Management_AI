import { readFileSync } from "node:fs";
import path from "node:path";
function load(file:string){try{return Object.fromEntries(readFileSync(file,"utf8").split(/\r?\n/).flatMap(line=>{const m=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return {}}}
const root=path.resolve(process.cwd(),"..");const rootEnv={...load(path.join(root,".env")),...load(path.join(root,".env.local"))};const dashboardEnv=load(path.join(process.cwd(),".env.local"));const env={...rootEnv,...dashboardEnv};
const url=env.NEXT_PUBLIC_SUPABASE_URL||env.SUPABASE_URL;const token=[process.env.SUPABASE_DASHBOARD_ACCESS_TOKEN,dashboardEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN,rootEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN].find(value=>value?.startsWith("sbp_"));
if(!url||!token)throw new Error("Supabase management configuration unavailable");const ref=new URL(url).hostname.split(".")[0];
const migration=process.argv[2]||"202608130002_add_full_library_visual_search.sql";
if(!/^2026\d{8}_[a-z0-9_]+\.sql$/.test(migration))throw new Error("Invalid migration filename");
const query=readFileSync(path.join(process.cwd(),"supabase","migrations",migration),"utf8");
const response=await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`,{method:"POST",headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},body:JSON.stringify({query})});
if(!response.ok)throw new Error(`Migration failed (${response.status}): ${(await response.text()).slice(0,1000)}`);
console.log("visual_search_migration=applied");
