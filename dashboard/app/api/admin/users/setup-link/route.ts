import { NextRequest, NextResponse } from "next/server";
import { requireSuperAdmin } from "../../../../auth";
import { canInvite } from "../../../../lib/management-rbac";
import { managementAudit, normalizedEmail, publicOrigin, safeProviderDiagnostic, sameOrigin, validEmail } from "../../../../lib/user-management";
import { createServiceClient } from "../../../../lib/supabase/service";

const headers={"Cache-Control":"private, no-store","Pragma":"no-cache"};

export async function POST(request:NextRequest){
  let actor;
  try{actor=await requireSuperAdmin()}catch{return NextResponse.json({error:"Only the Super Admin can generate setup links."},{status:403,headers})}
  if(!sameOrigin(request))return NextResponse.json({error:"Request could not be verified."},{status:403,headers});
  const body=await request.json().catch(()=>({}))as Record<string,unknown>,email=normalizedEmail(body.email),role=body.role;
  if(!validEmail(email))return NextResponse.json({error:"Enter a valid email address."},{status:400,headers});
  if(!canInvite(actor.managementRole,role))return NextResponse.json({error:"You do not have permission to assign this role."},{status:403,headers});
  const client=createServiceClient();
  const[{data:profile},{data:pending},authUsers]=await Promise.all([
    client.from("app_users").select("user_id,is_active").eq("email",email).maybeSingle(),
    client.from("user_invitations").select("id").eq("email",email).eq("status","pending").maybeSingle(),
    client.auth.admin.listUsers({page:1,perPage:1000}),
  ]);
  if(profile||authUsers.data.users.some(u=>u.email?.toLowerCase()===email))return NextResponse.json({error:profile&&!profile.is_active?"This account is disabled. Enable it instead of creating a duplicate.":"An account already exists for this email address."},{status:409,headers});
  if(pending)return NextResponse.json({error:"An invitation is already pending for this email address."},{status:409,headers});
  const{data:invitation,error:rowError}=await client.from("user_invitations").insert({email,assigned_role:role,invited_by:actor.userId}).select("id").single();
  if(rowError){
    console.error("KDI_SETUP_LINK",{stage:"invitation_record",code:rowError.code??null});
    return NextResponse.json({error:"Secure setup link could not be created."},{status:500,headers});
  }
  const generated=await client.auth.admin.generateLink({type:"invite",email,options:{redirectTo:`${publicOrigin(request)}/auth/setup-password`,data:{kdi_invitation_id:invitation.id}}});
  const authUser=generated.data.user,tokenHash=generated.data.properties?.hashed_token;
  if(generated.error||!authUser||!tokenHash){
    const diagnostic=safeProviderDiagnostic(generated.error);
    console.warn("KDI_SETUP_LINK",{stage:"provider_generation",...diagnostic});
    const users=await client.auth.admin.listUsers({page:1,perPage:1000}),orphan=users.data.users.find(user=>user.email?.toLowerCase()===email);
    if(orphan)await client.auth.admin.deleteUser(orphan.id);
    await client.from("user_invitations").update({status:"cancelled",cancelled_at:new Date().toISOString(),updated_at:new Date().toISOString()}).eq("id",invitation.id);
    await managementAudit(actor,"setup_link_generated",{targetEmail:email,roleAfter:String(role),outcome:"failed",metadata:{reason:diagnostic.reason}});
    return NextResponse.json({error:"Secure setup link could not be generated."},{status:502,headers});
  }
  const now=new Date().toISOString(),legacyRole=role==="admin"?"ADMIN":"STAFF";
  const{error:profileError}=await client.from("app_users").insert({user_id:authUser.id,email,role:legacyRole,management_role:role,is_active:false,can_view_clinical:false,can_download:true,created_by:actor.userId,invited_by:actor.userId,invited_at:now});
  if(profileError){
    await client.auth.admin.deleteUser(authUser.id);
    await client.from("user_invitations").update({status:"cancelled",cancelled_at:now,updated_at:now}).eq("id",invitation.id);
    console.error("KDI_SETUP_LINK",{stage:"profile_creation",code:profileError.code??null});
    return NextResponse.json({error:"The account profile could not be finalized. No account was retained."},{status:500,headers});
  }
  await client.from("user_invitations").update({auth_user_id:authUser.id,updated_at:now}).eq("id",invitation.id);
  await managementAudit(actor,"setup_link_generated",{targetUserId:authUser.id,targetEmail:email,roleAfter:String(role),metadata:{delivery:"super_admin_secure_handoff"}});
  const setupUrl=`${publicOrigin(request)}/auth/confirm?token_hash=${encodeURIComponent(tokenHash)}&type=invite&next=${encodeURIComponent("/auth/setup-password")}`;
  return NextResponse.json({message:`Secure ${role==="admin"?"Admin":"User"} setup link generated.`,setupUrl},{status:201,headers});
}
