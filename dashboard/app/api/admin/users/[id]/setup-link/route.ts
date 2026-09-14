import { NextRequest, NextResponse } from "next/server";
import { requireSuperAdmin } from "../../../../../auth";
import { managementAudit, publicOrigin, safeProviderDiagnostic, sameOrigin } from "../../../../../lib/user-management";
import { createServiceClient } from "../../../../../lib/supabase/service";

const headers={"Cache-Control":"private, no-store","Pragma":"no-cache"};

export async function POST(request:NextRequest,{params}:{params:Promise<{id:string}>}){
  let actor;
  try{actor=await requireSuperAdmin()}catch{return NextResponse.json({error:"Only the Super Admin can generate setup links."},{status:403,headers})}
  if(!sameOrigin(request))return NextResponse.json({error:"Request could not be verified."},{status:403,headers});
  const{id}=await params,client=createServiceClient(),{data:invite}=await client.from("user_invitations").select("id,auth_user_id,email,assigned_role,status,last_sent_at,send_count").eq("id",id).maybeSingle();
  if(!invite||invite.status!=="pending"||!invite.auth_user_id)return NextResponse.json({error:"A pending invitation was not found."},{status:404,headers});
  if(Date.now()-new Date(invite.last_sent_at).getTime()<60000)return NextResponse.json({error:"Please wait before generating another setup link."},{status:429,headers});
  const generated=await client.auth.admin.generateLink({type:"magiclink",email:invite.email,options:{redirectTo:`${publicOrigin(request)}/auth/setup-password`}}),tokenHash=generated.data.properties?.hashed_token;
  if(generated.error||!tokenHash){
    const diagnostic=safeProviderDiagnostic(generated.error);
    console.warn("KDI_SETUP_LINK",{stage:"replacement_generation",...diagnostic});
    await managementAudit(actor,"setup_link_regenerated",{targetUserId:invite.auth_user_id,targetEmail:invite.email,roleAfter:invite.assigned_role,outcome:"failed",metadata:{reason:diagnostic.reason}});
    return NextResponse.json({error:"A replacement setup link could not be generated."},{status:502,headers});
  }
  await client.from("user_invitations").update({last_sent_at:new Date().toISOString(),send_count:invite.send_count+1,updated_at:new Date().toISOString()}).eq("id",id);
  await managementAudit(actor,"setup_link_regenerated",{targetUserId:invite.auth_user_id,targetEmail:invite.email,roleAfter:invite.assigned_role,metadata:{delivery:"super_admin_secure_handoff"}});
  const setupUrl=`${publicOrigin(request)}/auth/confirm?token_hash=${encodeURIComponent(tokenHash)}&type=magiclink&next=${encodeURIComponent("/auth/setup-password")}`;
  return NextResponse.json({message:"Replacement secure setup link generated.",setupUrl},{headers});
}
