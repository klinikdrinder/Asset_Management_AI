import type { EmailOtpType } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";
import { applicationOrigin, safeReturnPath } from "../../lib/supabase/config";
import { copyResponseCookies, createRouteClient } from "../../lib/supabase/route-client";
import { createServiceClient } from "../../lib/supabase/service";

const allowedTypes=new Set<EmailOtpType>(["invite","recovery","magiclink","email"]);
export const dynamic="force-dynamic";

export async function GET(request:NextRequest){
  const origin=applicationOrigin(request.url),tokenHash=request.nextUrl.searchParams.get("token_hash")??"",rawType=request.nextUrl.searchParams.get("type")??"",next=safeReturnPath(request.nextUrl.searchParams.get("next"),rawType==="recovery"?"/auth/reset-password":"/auth/setup-password");
  if(!tokenHash||!allowedTypes.has(rawType as EmailOtpType))return NextResponse.redirect(new URL("/login?error=invalid_email_link",origin));
  const cookieResponse=NextResponse.next(),supabase=createRouteClient(request,cookieResponse),{data,error}=await supabase.auth.verifyOtp({token_hash:tokenHash,type:rawType as EmailOtpType});
  if(error||!data.user){
    console.warn("KDI_AUTH_EMAIL_LINK",{reason:"verification_failed",type:rawType});
    return NextResponse.redirect(new URL(`/login?error=${rawType==="recovery"?"invalid_reset_link":"invalid_invitation_link"}`,origin));
  }
  if(next==="/auth/setup-password"){
    const{data:invitation}=await createServiceClient().from("user_invitations").select("id").eq("auth_user_id",data.user.id).eq("status","pending").maybeSingle();
    if(!invitation){await supabase.auth.signOut({scope:"local"});return NextResponse.redirect(new URL("/login?error=invalid_invitation_link",origin))}
  }
  return copyResponseCookies(cookieResponse,NextResponse.redirect(new URL(next,origin)));
}
