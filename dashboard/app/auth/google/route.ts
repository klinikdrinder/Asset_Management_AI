import { NextRequest, NextResponse } from "next/server";
import { applicationOrigin } from "../../lib/supabase/config";
import { recordAuthDiagnostic } from "../callback/diagnostics";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const origin = applicationOrigin(request.url);
  await recordAuthDiagnostic({ stage: "oauth_start", reason: "server_oauth_route_retired", status: 307, redirectPath: "/login" });
  return NextResponse.redirect(new URL("/login?error=server_oauth_route_retired", origin));
}
