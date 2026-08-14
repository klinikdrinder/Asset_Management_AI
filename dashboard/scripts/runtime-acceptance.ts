import { readFileSync } from "node:fs";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";
import { getDriveAccessToken, resolveKdiMasterDriveId } from "../app/lib/google/service-account";

function load(file:string){try{return Object.fromEntries(readFileSync(file,"utf8").replace(/^\uFEFF/,"").split(/\r?\n/).flatMap(line=>{const m=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return {}}}
const fileEnv=load(path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/,"$1")),"..",".env.local"));const env={...process.env,...fileEnv};
const baseUrl=(process.env.KDI_BASE_URL||"http://127.0.0.1:3000").replace(/\/$/,"");
const url=env.NEXT_PUBLIC_SUPABASE_URL||"",key=env.NEXT_PUBLIC_SUPABASE_ANON_KEY||"",service=env.SUPABASE_SERVICE_ROLE_KEY||"";
const ref=(()=>{try{return new URL(url).hostname.split(".")[0]}catch{return "invalid"}})();
const result:Record<string,string|number>={SUPABASE_URL:"FAIL",SUPABASE_PROJECT_REF:ref,SUPABASE_BROWSER_ACCESS:"FAIL",SUPABASE_SERVER_ACCESS:"FAIL",ASSET_QUERY:"FAIL",VISUAL_RPC:"FAIL",GOOGLE_DRIVE_AUTH:"FAIL"};
if(url&&key&&service&&ref!=="invalid")result.SUPABASE_URL="PASS";
const anon=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}});
try{const {error}=await anon.auth.getSession();if(!error)result.SUPABASE_BROWSER_ACCESS="PASS"}catch{}
const admin=createClient(url,service,{auth:{persistSession:false,autoRefreshToken:false}});
let session:any=null;
try{const link=await admin.auth.admin.generateLink({type:"magiclink",email:"kdimediaautomation@gmail.com"});const hash=link.data.properties?.hashed_token;if(!hash)throw new Error("reader link unavailable");const verified=await anon.auth.verifyOtp({token_hash:hash,type:"email"});session=verified.data.session;if(session)result.SUPABASE_SERVER_ACCESS="PASS"}catch{}
let assetId="",assetName="";
if(session){
  const reader=createClient(url,key,{global:{headers:{Authorization:`Bearer ${session.access_token}`}},auth:{persistSession:false,autoRefreshToken:false}});
  const count=await reader.from("assets").select("id",{count:"exact",head:true});if(!count.error&&count.count===881)result.ASSET_QUERY=`PASS (${count.count})`;
  const destinations=await admin.from("asset_destinations").select("asset_id").eq("upload_status","VERIFIED").not("destination_google_file_id","is",null).limit(1);assetId=String(destinations.data?.[0]?.asset_id||"");
  if(assetId){const first=await reader.from("assets").select("file_name").eq("id",assetId).single();assetName=String(first.data?.file_name||"")}
  const vector=[1,...Array(511).fill(0)];const rpc=await reader.rpc("hybrid_search_assets_v2",{search_query:"clinic",visual_query_embedding:vector,visual_provider:"open_clip",visual_model:"ViT-B-32",visual_version:"laion2b_s34b_b79k",qwen_query_embedding:null,qwen_provider:null,qwen_model:null,qwen_version:null,filter_category:null,filter_extension:null,result_limit:5,result_offset:0});if(!rpc.error&&Array.isArray(rpc.data))result.VISUAL_RPC="PASS";
}
try{const token=await getDriveAccessToken(env);const folderId=resolveKdiMasterDriveId(env);const response=await fetch(`https://www.googleapis.com/drive/v3/files/${encodeURIComponent(folderId)}?fields=id&supportsAllDrives=true`,{headers:{Authorization:`Bearer ${token}`}});if(response.ok)result.GOOGLE_DRIVE_AUTH="PASS"}catch{}
function cookiesFor(sessionValue:any){const raw=`base64-${Buffer.from(JSON.stringify(sessionValue)).toString("base64url")}`;const name=`sb-${ref}-auth-token`;const values=[];for(let i=0;i<raw.length;i+=3180)values.push(`${name}.${values.length}=${raw.slice(i,i+3180)}`);return values.join("; ")}
const runtime:Record<string,string|number>={};
if(session){const headers={Cookie:cookiesFor(session)};for(const route of ["/library","/library?query=IMG","/library?category=image","/library?refine=clinic%20room"]){const response=await fetch(`${baseUrl}${route}`,{headers,redirect:"manual"});runtime[route]=response.status;const body=await response.text();if(route==="/library")runtime.asset_cards=body.includes(assetName)||/fileCard|fileGrid|Open preview|Download/.test(body)?"PASS":"FAIL"}
  if(assetId)for(const operation of ["thumbnail","preview","download"]){const response=await fetch(`${baseUrl}/api/media/${assetId}/${operation}`,{headers,redirect:"manual"});runtime[operation]=response.status;}
}
console.log(JSON.stringify({diagnostics:result,runtime},null,2));
