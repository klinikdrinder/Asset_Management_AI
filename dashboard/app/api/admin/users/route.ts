import { NextRequest, NextResponse } from "next/server";
import { AuthenticationRequired, AuthorizationDenied, requireAdmin } from "../../../auth";
import { canInvite, canManage, allowedInvitationRoles } from "../../../lib/management-rbac";
import { classifyInvitationDeliveryFailure, invitationDeliveryMessage, managementAudit, normalizedEmail, publicOrigin, safeProviderDiagnostic, sameOrigin, validEmail } from "../../../lib/user-management";
import { createServiceClient } from "../../../lib/supabase/service";

const noStore={"Cache-Control":"private, no-store","Pragma":"no-cache"};

export async function GET(){
  try{
    const actor=await requireAdmin(),client=createServiceClient();
    const[{data:profiles,error:pError},{data:invites,error:iError},auth]=await Promise.all([
      client.from("app_users").select("user_id,email,management_role,is_active,created_at,invited_at,invited_by,disabled_at"),
      client.from("user_invitations").select("id,auth_user_id,email,assigned_role,status,invited_by,invited_at,last_sent_at,accepted_at,send_count"),
      client.auth.admin.listUsers({page:1,perPage:1000}),
    ]);
    if(pError||iError||auth.error)throw pError??iError??auth.error;
    const authById=new Map(auth.data.users.map(user=>[user.id,user])),profileById=new Map((profiles??[]).map(profile=>[profile.user_id,profile]));
    const users=(profiles??[]).map(profile=>{
      const identity=authById.get(profile.user_id),invitation=(invites??[]).find(item=>item.auth_user_id===profile.user_id);
      return{id:profile.user_id,email:profile.email,role:profile.management_role,status:!profile.is_active?(invitation?.status==="pending"?"Invitation Pending":"Disabled"):"Active",invitationStatus:invitation?.status??(identity?.email_confirmed_at?"accepted":null),createdAt:profile.created_at,invitedAt:profile.invited_at,lastSignInAt:identity?.last_sign_in_at??null,invitedBy:profile.invited_by?profileById.get(profile.invited_by)?.email??null:null,isActive:profile.is_active,invitationId:invitation?.id??null,lastSentAt:invitation?.last_sent_at??null,sendCount:invitation?.send_count??0,canManage:canManage(actor.managementRole,profile.management_role)};
    });
    return NextResponse.json({users,actorRole:actor.managementRole,allowedRoles:allowedInvitationRoles(actor.managementRole)},{headers:noStore});
  }catch(error){
    const status=error instanceof AuthenticationRequired?401:error instanceof AuthorizationDenied?403:500;
    return NextResponse.json({error:status===401?"Authentication required.":status===403?"You do not have permission to access user management.":"User management is temporarily unavailable."},{status,headers:noStore});
  }
}

export async function POST(request:NextRequest){
  let actor;
  try{actor=await requireAdmin()}catch(error){return NextResponse.json({error:"You do not have permission to invite users."},{status:error instanceof AuthenticationRequired?401:error instanceof AuthorizationDenied?403:403,headers:noStore})}
  if(!sameOrigin(request))return NextResponse.json({error:"Request could not be verified."},{status:403,headers:noStore});
  const body=await request.json().catch(()=>({}))as Record<string,unknown>,email=normalizedEmail(body.email),role=body.role;
  if(!validEmail(email))return NextResponse.json({error:"Enter a valid email address."},{status:400,headers:noStore});
  if(!canInvite(actor.managementRole,role)){
    await managementAudit(actor,"invitation_rejected",{targetEmail:email,roleAfter:String(role),outcome:"rejected",metadata:{reason:"role_not_allowed"}});
    return NextResponse.json({error:"You do not have permission to assign this role."},{status:403,headers:noStore});
  }
  const client=createServiceClient();
  const[{data:profile},{data:pending},authUsers]=await Promise.all([
    client.from("app_users").select("user_id,is_active").eq("email",email).maybeSingle(),
    client.from("user_invitations").select("id").eq("email",email).eq("status","pending").maybeSingle(),
    client.auth.admin.listUsers({page:1,perPage:1000}),
  ]);
  if(profile||authUsers.data.users.some(u=>u.email?.toLowerCase()===email))return NextResponse.json({error:profile&&!profile.is_active?"This account is disabled. Enable it instead of creating a duplicate.":"An account already exists for this email address."},{status:409,headers:noStore});
  if(pending)return NextResponse.json({error:"An invitation is already pending for this email address."},{status:409,headers:noStore});
  const{data:invitation,error:rowError}=await client.from("user_invitations").insert({email,assigned_role:role,invited_by:actor.userId}).select("id").single();
  if(rowError){
    console.error("KDI_USER_INVITATION",{stage:"invitation_record",code:rowError.code??null});
    await managementAudit(actor,"invitation_create_failed",{targetEmail:email,roleAfter:String(role),outcome:"failed",metadata:{reason:"invitation_record_rejected",database_code:rowError.code??null}});
    return NextResponse.json({error:"Invitation service is temporarily unavailable."},{status:500,headers:noStore});
  }
  const redirectTo=`${publicOrigin(request)}/auth/setup-password`,{data:sent,error:sendError}=await client.auth.admin.inviteUserByEmail(email,{redirectTo,data:{kdi_invitation_id:invitation.id}});
  if(sendError||!sent.user){
    const diagnostic=safeProviderDiagnostic(sendError);
    console.warn("KDI_USER_INVITATION",{stage:"email_delivery",...diagnostic});
    const orphaned=await client.auth.admin.listUsers({page:1,perPage:1000}),orphan=orphaned.data.users.find(user=>user.email?.toLowerCase()===email);
    if(orphan)await client.auth.admin.deleteUser(orphan.id);
    await client.from("user_invitations").update({status:"cancelled",cancelled_at:new Date().toISOString(),updated_at:new Date().toISOString()}).eq("id",invitation.id);
    await managementAudit(actor,"user_invited",{targetEmail:email,roleAfter:String(role),outcome:"failed",metadata:{reason:diagnostic.reason,provider_status:diagnostic.status,provider_code:diagnostic.code}});
    const reason=classifyInvitationDeliveryFailure(sendError);
    return NextResponse.json({error:invitationDeliveryMessage(reason),setupLinkAvailable:actor.managementRole==="super_admin"},{status:reason==="email_rate_limit"?429:502,headers:noStore});
  }
  const now=new Date().toISOString(),legacyRole=role==="admin"?"ADMIN":"STAFF";
  const{error:profileError}=await client.from("app_users").insert({user_id:sent.user.id,email,role:legacyRole,management_role:role,is_active:false,can_view_clinical:false,can_download:true,created_by:actor.userId,invited_by:actor.userId,invited_at:now});
  if(profileError){
    await client.auth.admin.deleteUser(sent.user.id);
    await client.from("user_invitations").update({status:"cancelled",cancelled_at:now,updated_at:now}).eq("id",invitation.id);
    console.error("KDI_USER_INVITATION",{stage:"profile_creation",code:profileError.code??null});
    await managementAudit(actor,"user_invited",{targetEmail:email,roleAfter:String(role),outcome:"failed",metadata:{reason:"profile_creation_failed",database_code:profileError.code??null}});
    return NextResponse.json({error:"The account profile could not be finalized. No account was retained."},{status:500,headers:noStore});
  }
  await client.from("user_invitations").update({auth_user_id:sent.user.id,updated_at:now}).eq("id",invitation.id);
  await managementAudit(actor,role==="admin"?"admin_invited":"user_invited",{targetUserId:sent.user.id,targetEmail:email,roleAfter:String(role)});
  return NextResponse.json({message:`${role==="admin"?"Admin":"User"} invitation sent successfully.`},{status:201,headers:noStore});
}
