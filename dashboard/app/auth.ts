import "server-only";
import { redirect } from "next/navigation";
import { profileForFirebaseUid } from "./lib/auth-profile";
import { verifyFirebaseSession } from "./lib/firebase/session";
import { createClient } from "./lib/supabase/server";
import { getPreviewRole } from "./lib/dev-preview";
import { isLocalAuthBypassActive } from "./lib/local-auth-bypass";
import { currentAdmin } from "./lib/admin-auth/session";
import type { ManagementRole } from "./lib/management-rbac";
export type AppRole="STAFF"|"ADMIN";
export type AppUser={userId:string;firebaseUid:string|null;email:string;displayName:string;role:AppRole;managementRole:ManagementRole;isActive:boolean;canViewClinical:boolean;canDownload:boolean};
export class AuthenticationRequired extends Error{} export class AuthorizationDenied extends Error{}
export async function getCurrentAppUser():Promise<AppUser|null>{
  if(await isLocalAuthBypassActive())return{userId:"local-auth-bypass",firebaseUid:null,email:"local@localhost.invalid",displayName:"Local KDI User",role:"ADMIN",managementRole:"super_admin",isActive:true,canViewClinical:true,canDownload:true};
  const admin=await currentAdmin();if(admin)return{userId:admin.id,firebaseUid:null,email:admin.email,displayName:admin.fullName,role:"ADMIN",managementRole:"super_admin",isActive:admin.isActive,canViewClinical:true,canDownload:true};
  const preview=await getPreviewRole();if(preview)return{userId:"preview-only",firebaseUid:null,email:"preview@preview.invalid",displayName:"Frontend Preview User",role:preview,managementRole:preview==="ADMIN"?"admin":"user",isActive:true,canViewClinical:preview==="ADMIN",canDownload:preview==="ADMIN"};
  const identity=await verifyFirebaseSession();
  if(identity?.uid&&identity.email){const p=await profileForFirebaseUid(identity.uid);if(!p||p.email!==identity.email.trim().toLowerCase())return null;return{userId:p.user_id,firebaseUid:p.firebase_uid,email:p.email,displayName:p.email.split("@")[0].slice(0,40),role:p.role,managementRole:p.management_role,isActive:p.is_active,canViewClinical:p.can_view_clinical,canDownload:p.can_download}}
  // Temporary rollback path: retain the deployed Supabase website OAuth until
  // Firebase live acceptance succeeds.
  const supabase=await createClient(),{data:{user}}=await supabase.auth.getUser();
  if(!user?.id||!user.email)return null;
  const{data:p}=await supabase.from("app_users").select("user_id,email,role,management_role,is_active,can_view_clinical,can_download,firebase_uid").eq("user_id",user.id).maybeSingle();
  if(!p)return null;const fullName=typeof user.user_metadata?.full_name==="string"?user.user_metadata.full_name.trim():"";return{userId:p.user_id,firebaseUid:p.firebase_uid??null,email:p.email,displayName:(fullName||p.email.split("@")[0]).slice(0,40),role:p.role as AppRole,managementRole:p.management_role as ManagementRole,isActive:p.is_active===true,canViewClinical:p.can_view_clinical===true,canDownload:p.can_download===true};
}
export async function requireActiveAppUser(){const u=await getCurrentAppUser();if(!u)throw new AuthenticationRequired("Authentication required");if(!u.isActive)throw new AuthorizationDenied("Access denied");return u}
export async function requireStaffOrAdmin(){const u=await requireActiveAppUser();if(u.role!=="STAFF"&&u.role!=="ADMIN")throw new AuthorizationDenied("Access denied");return u}
export async function requireAdmin(){const u=await requireActiveAppUser();if(u.managementRole!=="super_admin"&&u.managementRole!=="admin")throw new AuthorizationDenied("Access denied");return u}
export async function requireSuperAdmin(){const u=await requireActiveAppUser();if(u.managementRole!=="super_admin")throw new AuthorizationDenied("Access denied");return u}
export async function requireClinicalPermission(){const u=await requireStaffOrAdmin();if(!u.canViewClinical)throw new AuthorizationDenied("Access denied");return u}
export async function requireDownloadPermission(){const u=await requireStaffOrAdmin();if(!u.canDownload)throw new AuthorizationDenied("Access denied");return u}
export async function requireProtectedPage(role:"STAFF_OR_ADMIN"|"ADMIN"="STAFF_OR_ADMIN"){try{return role==="ADMIN"?await requireAdmin():await requireStaffOrAdmin()}catch(e){if(e instanceof AuthorizationDenied)redirect("/access-denied");redirect("/login")}}
export function maskEmail(email:string){const[name,domain]=email.split("@");return`${name.slice(0,2)}***@${domain??"account"}`}
