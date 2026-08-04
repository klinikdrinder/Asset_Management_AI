import { NextRequest, NextResponse } from "next/server";
import { applicationOrigin } from "../../lib/supabase/config";
import { copyResponseCookies, createRouteClient } from "../../lib/supabase/route-client";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const origin = applicationOrigin(request.url);
  const cookieResponse = NextResponse.next();
  const supabase = createRouteClient(request, cookieResponse);
  await supabase.auth.signOut({ scope: "local" });
  return copyResponseCookies(cookieResponse, NextResponse.redirect(new URL("/login", origin)));
}
