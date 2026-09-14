import "server-only";
import { createServiceClient } from "./supabase/service";
import type { AppUser } from "../auth";

export const normalizedEmail=(value:unknown)=>typeof value==="string"?value.trim().toLowerCase():"";
export const validEmail=(value:string)=>value.length<=254&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
export async function managementAudit(actor:AppUser|null,action:string,fields:{targetUserId?:string|null;targetEmail?:string|null;roleBefore?:string|null;roleAfter?:string|null;outcome?:"allowed"|"rejected"|"failed";metadata?:Record<string,unknown>}={}){
  await createServiceClient().from("user_management_audit").insert({actor_user_id:actor?.userId??null,action,target_user_id:fields.targetUserId??null,target_email:fields.targetEmail??null,role_before:fields.roleBefore??null,role_after:fields.roleAfter??null,outcome:fields.outcome??"allowed",metadata:fields.metadata??{}});
}
export function sameOrigin(request:Request){const origin=request.headers.get("origin"),host=request.headers.get("host");if(!origin||!host)return false;try{return new URL(origin).host===host}catch{return false}}
export function publicOrigin(request:Request){
  const origin=request.headers.get("origin"),host=request.headers.get("host");
  if(origin&&host){try{const candidate=new URL(origin);if(candidate.host===host)return candidate.origin}catch{}}
  const url=new URL(request.url);return `${url.protocol}//${url.host}`;
}

export type InvitationDeliveryFailure="email_rate_limit"|"smtp_unavailable"|"redirect_not_allowed"|"identity_conflict"|"email_provider_rejected";
export function classifyInvitationDeliveryFailure(error:unknown):InvitationDeliveryFailure{
  const candidate=error as{message?:unknown;code?:unknown;status?:unknown}|null;
  const text=`${String(candidate?.code??"")} ${String(candidate?.message??"")}`.toLowerCase();
  if(candidate?.status===429||text.includes("rate limit"))return"email_rate_limit";
  if(text.includes("smtp")||text.includes("mailer")||text.includes("email provider"))return"smtp_unavailable";
  if(text.includes("redirect")||text.includes("url is not allowed"))return"redirect_not_allowed";
  if(text.includes("already")&&(text.includes("registered")||text.includes("exists")))return"identity_conflict";
  return"email_provider_rejected";
}
export function invitationDeliveryMessage(reason:InvitationDeliveryFailure){
  if(reason==="email_rate_limit")return"Email service limit reached. Please try again later or use the secure setup-link option.";
  if(reason==="smtp_unavailable")return"Invitation email service is not configured.";
  if(reason==="redirect_not_allowed")return"The account setup address is not authorized. Contact support.";
  if(reason==="identity_conflict")return"An account already exists for this email address.";
  return"Invitation email could not be accepted for delivery. Please try again later or use the secure setup-link option.";
}
export function safeProviderDiagnostic(error:unknown){
  const candidate=error as{code?:unknown;status?:unknown}|null;
  return{reason:classifyInvitationDeliveryFailure(error),status:typeof candidate?.status==="number"?candidate.status:null,code:typeof candidate?.code==="string"?candidate.code.slice(0,80):null};
}
