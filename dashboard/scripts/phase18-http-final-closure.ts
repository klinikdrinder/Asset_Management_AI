import { createHash, randomBytes } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";

type AssetId = string & { readonly __assetId: unique symbol };
type SourceFileId = string & { readonly __sourceFileId: unique symbol };
type SafeResponse = { status:number; cache:string|null; type:string|null; fingerprint:string; leakage:number; containsAsset:boolean };
const root=path.resolve(import.meta.dirname,"../..");
function env(file:string){try{return Object.fromEntries(readFileSync(file,"utf8").replace(/^\uFEFF/,"").split(/\r?\n/).flatMap(line=>{const m=line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);return m?[[m[1],m[2].trim().replace(/^(['"])(.*)\1$/,"$2")]]:[]}))}catch{return{}}}
const a:any=env(path.join(root,".env.local")),b:any=env(path.join(root,"dashboard",".env.local"));
const url=b.NEXT_PUBLIC_SUPABASE_URL||a.NEXT_PUBLIC_SUPABASE_URL,key=b.SUPABASE_SERVICE_ROLE_KEY||a.SUPABASE_SERVICE_ROLE_KEY,base=process.env.PHASE18_HTTP_BASE||"http://127.0.0.1:3108";
if(!url||!key)throw Error("configuration unavailable");
const db=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}}),nonce=randomBytes(12).toString("hex"),password=`T!${randomBytes(24).toString("base64url")}8a`;
const emails=[`phase18-final-a-${nonce}@example.invalid`,`phase18-final-b-${nonce}@example.invalid`],created:string[]=[];
const retry=async<T>(fn:()=>Promise<T>,label:string):Promise<T>=>{let last:unknown;for(let i=0;i<3;i++){try{return await fn()}catch(e){last=e;if(i<2)await new Promise(r=>setTimeout(r,500*(i+1)))}}throw new Error(`${label} failed after retries`,{cause:last})};
const call=async(pathname:string,cookie?:string,method="GET",body?:unknown)=>{const r=await fetch(`${base}${pathname}`,{method,redirect:"manual",headers:{origin:base,...(cookie?{cookie}:{}),...(body?{"content-type":"application/json"}:{}),...(pathname.includes("/api/media/")?{range:"bytes=0-0"}:{})},body:body?JSON.stringify(body):undefined});const bytes=new Uint8Array(await r.arrayBuffer()),text=new TextDecoder().decode(bytes.slice(0,30000));return{r,bytes,text}};
const hash=(bytes:Uint8Array)=>createHash("sha256").update(bytes).digest("hex");
async function login(email:string){const {r}=await call("/api/auth/password-login",undefined,"POST",{email,password});if(!r.ok)throw Error(`login failed ${r.status}`);return((r.headers as any).getSetCookie?.()??[r.headers.get("set-cookie")??""]).map((x:string)=>x.split(";",1)[0]).join("; ")}
let asset:any=null,original:any=null,report:any=null;
try{
  const selected=await retry(async()=>await db.from("assets").select("id,file_name,asset_sources(source_file_id),asset_destinations!inner(upload_status,destination_google_file_id)").eq("file_name","IMG_3429.MP4").eq("asset_destinations.upload_status","VERIFIED").limit(1).single(),"controlled asset lookup");
  if(selected.error||!selected.data)throw selected.error||Error("controlled asset unavailable");asset=selected.data;
  const assetId=asset.id as AssetId,sourceFileId=(asset.asset_sources as any[])[0]?.source_file_id as SourceFileId;
  if(!assetId||!sourceFileId||assetId===String(sourceFileId))throw Error("asset/source identifier contract invalid");
  const assetProof=await db.from("assets").select("id").eq("id",assetId).single(),sourceProof=await db.from("source_files").select("id").eq("id",sourceFileId).single();
  if(assetProof.error||sourceProof.error||assetProof.data.id!==assetId||sourceProof.data.id!==sourceFileId)throw Error("identifier semantic assertion failed");
  const snap=await db.from("asset_access_control").select("*").eq("asset_id",assetId).single();if(snap.error)throw snap.error;original=snap.data;
  for(let i=0;i<2;i++){const made=await retry(()=>db.auth.admin.createUser({email:emails[i],password,email_confirm:true}),`create identity ${i}`);if(made.error||!made.data.user)throw made.error||Error("identity unavailable");created.push(made.data.user.id);const p=await db.from("app_users").insert({user_id:made.data.user.id,email:emails[i],role:"STAFF",management_role:"user",is_active:true,can_view_clinical:i===0,can_download:i===0});if(p.error)throw p.error}
  const changed=await db.from("asset_access_control").update({internal_usage_status:"ALLOWED",is_clinical:true,requires_clinical_permission:true,sensitivity_level:"CLINICAL",download_allowed:true}).eq("asset_id",assetId);if(changed.error)throw changed.error;
  const [A,B]=await Promise.all(emails.map(login)),meta=`/library/files/${assetId}`,preview=`/api/media/${assetId}/preview`,download=`/api/media/${assetId}/download`,search="/api/search/v3",markers=[asset.file_name,"destination_google_file_id","google drive","transcript","ocr","clinical"];
  const safe=(x:Awaited<ReturnType<typeof call>>,authorized:boolean):SafeResponse=>{let resultAsset=false,scanText=x.text;try{const json=JSON.parse(x.text);resultAsset=Array.isArray(json.items)&&json.items.some((item:any)=>item?.id===assetId);delete json.resolvedQuery;scanText=JSON.stringify(json)}catch{}return{status:x.r.status,cache:x.r.headers.get("cache-control"),type:x.r.headers.get("content-type"),fingerprint:hash(x.bytes),leakage:authorized?0:markers.filter(v=>scanText.toLowerCase().includes(String(v).toLowerCase())).length,containsAsset:resultAsset}};
  const specs=[{name:"metadata",path:meta,method:"GET"},{name:"preview",path:preview,method:"GET"},{name:"download",path:download,method:"GET"},{name:"search",path:search,method:"POST",body:{query:asset.file_name}}];
  const directions:any={forward:{},reverse:{},concurrent:{}};
  for(const s of specs){const a1=await call(s.path,A,s.method,s.body),b2=await call(s.path,B,s.method,s.body),b1=await call(s.path,B,s.method,s.body),a2=await call(s.path,A,s.method,s.body);directions.forward[s.name]={authorized:safe(a1,true),unauthorized:safe(b2,false)};directions.reverse[s.name]={unauthorized:safe(b1,false),authorized:safe(a2,true)};const [ac,bc]=await Promise.all([call(s.path,A,s.method,s.body),call(s.path,B,s.method,s.body)]);directions.concurrent[s.name]={authorized:safe(ac,true),unauthorized:safe(bc,false)}}
  const anonymous={metadata:safe(await call(meta),false),preview:safe(await call(preview),false),download:safe(await call(download),false),search:safe(await call(search,undefined,"POST",{query:asset.file_name}),false)};
  await db.from("asset_access_control").update({download_allowed:false}).eq("asset_id",assetId);const viewWithoutDownload=safe(await call(download,A),false);
  const mediaOk=(x:any)=>[200,206].includes(x.authorized.status)&&x.unauthorized.status===403&&x.unauthorized.leakage===0,metadataOk=(x:any)=>x.authorized.status===200&&x.unauthorized.leakage===0&&x.authorized.fingerprint!==x.unauthorized.fingerprint,searchOk=(x:any)=>x.authorized.status===200&&x.authorized.containsAsset&&x.unauthorized.status===200&&x.unauthorized.leakage===0&&!x.unauthorized.containsAsset;
  const all=[directions.forward,directions.reverse,directions.concurrent],pass=all.every((d:any)=>metadataOk(d.metadata)&&mediaOk(d.preview)&&mediaOk(d.download)&&searchOk(d.search))&&viewWithoutDownload.status===403&&viewWithoutDownload.leakage===0&&anonymous.metadata.leakage===0&&anonymous.preview.leakage===0&&anonymous.download.leakage===0&&anonymous.search.leakage===0;
  report={generated_at:new Date().toISOString(),run_nonce:nonce,status:pass?"PASS":"FAIL",server:{base,port:3108},identifier_contract:{metadata:"assets.id",preview:"assets.id",download:"assets.id",asset_source_ids_distinct:true},same_controlled_asset:true,directions,anonymous,view_without_download:viewWithoutDownload,cross_user_leakage:all.reduce((n,d:any)=>n+Object.values(d).reduce((m:number,x:any)=>m+x.unauthorized.leakage,0),0)};
}finally{
  if(original&&asset){const{asset_id,created_at,updated_at,...restore}=original;await retry(async()=>{const r=await db.from("asset_access_control").update(restore).eq("asset_id",asset.id);if(r.error)throw r.error;return r},"ACL restore")}
  if(created.length)await db.from("search_sessions").delete().in("user_id",created);
  for(const id of [...created].reverse())await retry(async()=>{const r=await db.auth.admin.deleteUser(id);if(r.error)throw r.error;return r},"temporary user cleanup");
  if(report){const acl=await db.from("asset_access_control").select("*").eq("asset_id",asset.id).single(),users=await db.from("app_users").select("user_id",{count:"exact",head:true}).in("user_id",created);const fields=["internal_usage_status","is_clinical","requires_clinical_permission","sensitivity_level","download_allowed"];report.cleanup={temporary_users:Number(users.count||0),acl_restored:!acl.error&&fields.every(k=>acl.data?.[k]===original[k])};report.status=report.status==="PASS"&&report.cleanup.temporary_users===0&&report.cleanup.acl_restored?"PASS":"FAIL";const out=path.join(root,"reports","semantic-search","phase18");mkdirSync(out,{recursive:true});writeFileSync(path.join(out,"http_final_closure.json"),JSON.stringify(report,null,2)+"\n");console.log(JSON.stringify(report,null,2));if(report.status!=="PASS")process.exitCode=1}
}
