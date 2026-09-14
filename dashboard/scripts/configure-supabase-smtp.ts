import { readFileSync } from "node:fs";

function envFile(path:string){try{return Object.fromEntries(readFileSync(path,"utf8").replace(/^\uFEFF/,"").split(/\r?\n/).flatMap(line=>{const match=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return match?[[match[1],match[2].trim().replace(/^(['"])(.*)\1$/, "$2")]]:[]}))}catch{return{}}}
const config={...envFile("../.env.local"),...envFile(".env.local"),...process.env} as Record<string,string|undefined>;
const required=["KDI_SMTP_HOST","KDI_SMTP_PORT","KDI_SMTP_USERNAME","KDI_SMTP_PASSWORD","KDI_SMTP_SENDER_EMAIL","KDI_SMTP_SENDER_NAME"] as const;
const missing=required.filter(name=>!config[name]);
if(missing.length)throw new Error(`Missing server-only SMTP configuration: ${missing.join(", ")}`);
const url=config.NEXT_PUBLIC_SUPABASE_URL,accessToken=config.SUPABASE_DASHBOARD_ACCESS_TOKEN;
if(!url||!accessToken)throw new Error("Supabase project URL or dashboard access token is unavailable.");
if(!process.argv.includes("--apply")){console.log("SMTP_CONFIG_VALID=PASS");console.log("No changes made. Re-run with --apply after reviewing the server-only values.");process.exit(0)}
const projectRef=new URL(url).hostname.split(".")[0];
const response=await fetch(`https://api.supabase.com/v1/projects/${projectRef}/config/auth`,{method:"PATCH",headers:{Authorization:`Bearer ${accessToken}`,"Content-Type":"application/json"},body:JSON.stringify({smtp_host:config.KDI_SMTP_HOST,smtp_port:Number(config.KDI_SMTP_PORT),smtp_user:config.KDI_SMTP_USERNAME,smtp_pass:config.KDI_SMTP_PASSWORD,smtp_admin_email:config.KDI_SMTP_SENDER_EMAIL,smtp_sender_name:config.KDI_SMTP_SENDER_NAME})});
if(!response.ok)throw new Error(`Supabase SMTP update failed (${response.status}).`);
console.log("SMTP_CONFIGURATION_APPLIED=PASS");
