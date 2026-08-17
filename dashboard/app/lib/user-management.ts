import "server-only";
import { createServiceClient } from "./supabase/service";
import type { AppUser } from "../auth";

export const normalizedEmail=(value:unknown)=>typeof value==="string"?value.trim().toLowerCase():"";
export const validEmail=(value:string)=>value.length<=254&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
export async function managementAudit(actor:AppUser|null,action:string,fields:{targetUserId?:string|null;targetEmail?:string|null;roleBefore?:string|null;roleAfter?:string|null;outcome?:"allowed"|"rejected"|"failed";metadata?:Record<string,unknown>}={}){
  await createServiceClient().from("user_management_audit").insert({actor_user_id:actor?.userId??null,action,target_user_id:fields.targetUserId??null,target_email:fields.targetEmail??null,role_before:fields.roleBefore??null,role_after:fields.roleAfter??null,outcome:fields.outcome??"allowed",metadata:fields.metadata??{}});
}
export function sameOrigin(request:Request){const origin=request.headers.get("origin"),host=request.headers.get("host");if(!origin||!host)return false;try{return new URL(origin).host===host}catch{return false}}
export function publicOrigin(request:Request){const url=new URL(request.url);return `${url.protocol}//${url.host}`}
