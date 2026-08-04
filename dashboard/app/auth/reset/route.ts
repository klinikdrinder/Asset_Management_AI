import { NextRequest, NextResponse } from "next/server";
import { applicationOrigin } from "../../lib/supabase/config";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const requested = request.nextUrl.searchParams.get("next");
  const destination = requested?.startsWith("/auth/google?") && !requested.includes("\\") ? requested : "/login";
  const response = NextResponse.redirect(new URL(destination, applicationOrigin(request.url)));
  for (const { name } of request.cookies.getAll()) {
    if (/^sb-wcqqjpndlwsvatjuqnol-auth-token(?:-code-verifier|\.\d+)?$/.test(name)) response.cookies.set(name, "", { httpOnly: true, sameSite: "lax", secure: false, path: "/", maxAge: 0 });
  }
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}
