import { NextRequest, NextResponse } from "next/server";
import { requireAdmin } from "../../../../../auth";
import { canManage } from "../../../../../lib/management-rbac";
import { classifyInvitationDeliveryFailure, invitationDeliveryMessage, managementAudit, publicOrigin, safeProviderDiagnostic, sameOrigin } from "../../../../../lib/user-management";
import { createServiceClient } from "../../../../../lib/supabase/service";

const headers={"Cache-Control":"private, no-store","Pragma":"no-cache"};
export async function POST(request:NextRequest,{params}:{params:Promise<{id:string}>}){
  let actor;
  try{actor=await requireAdmin()}catch{return NextResponse.json({error:"You do not have permission to resend invitations."},{status:403,headers})}
  if(!sameOrigin(request))return NextResponse.json({error:"Request could not be verified."},{status:403,headers});
  const{id}=await params,client=createServiceClient(),{data:invite}=await client.from("user_invitations").select("id,auth_user_id,email,assigned_role,status,last_sent_at,send_count").eq("id",id).maybeSingle();
  if(!invite||!canManage(actor.managementRole,invite.assigned_role))return NextResponse.json({error:"You do not have permission to resend this invitation."},{status:403,headers});
  if(invite.status!=="pending")return NextResponse.json({error:"Only pending invitations can be resent."},{status:409,headers});
  if(Date.now()-new Date(invite.last_sent_at).getTime()<60000)return NextResponse.json({error:"Please wait before resending this invitation."},{status:429,headers});
  const{error}=await client.auth.admin.inviteUserByEmail(invite.email,{redirectTo:`${publicOrigin(request)}/auth/setup-password`,data:{kdi_invitation_id:invite.id}});
  if(error){
    const diagnostic=safeProviderDiagnostic(error),reason=classifyInvitationDeliveryFailure(error);
    console.warn("KDI_USER_INVITATION",{stage:"email_resend",...diagnostic});
    await managementAudit(actor,"invitation_resent",{targetUserId:invite.auth_user_id,targetEmail:invite.email,roleAfter:invite.assigned_role,outcome:"failed",metadata:{reason:diagnostic.reason,provider_status:diagnostic.status,provider_code:diagnostic.code}});
    return NextResponse.json({error:invitationDeliveryMessage(reason),setupLinkAvailable:actor.managementRole==="super_admin"},{status:reason==="email_rate_limit"?429:502,headers});
  }
  await client.from("user_invitations").update({last_sent_at:new Date().toISOString(),send_count:invite.send_count+1,updated_at:new Date().toISOString()}).eq("id",id);
  await managementAudit(actor,"invitation_resent",{targetUserId:invite.auth_user_id,targetEmail:invite.email,roleAfter:invite.assigned_role});
  return NextResponse.json({message:"Invitation resent successfully."},{headers});
}
