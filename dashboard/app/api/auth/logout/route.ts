import { NextRequest, NextResponse } from "next/server";
import { FIREBASE_CSRF_COOKIE, FIREBASE_SESSION_COOKIE } from "../../../lib/firebase/session";
import { FIREBASE_SUPABASE_TOKEN_COOKIE } from "../../../lib/library/authenticated-token";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  if (request.headers.get("origin") !== request.nextUrl.origin) {
    return NextResponse.json({ status: "denied" }, { status: 403 });
  }
  const response = NextResponse.json({ status: "signed_out" });
  response.cookies.delete(FIREBASE_SESSION_COOKIE);
  response.cookies.delete(FIREBASE_CSRF_COOKIE);
  response.cookies.delete(FIREBASE_SUPABASE_TOKEN_COOKIE);
  for (const cookie of request.cookies.getAll()) {
    if (cookie.name.startsWith("sb-") || cookie.name.includes("supabase")) response.cookies.delete(cookie.name);
  }
  response.headers.set("Clear-Site-Data", '"cache", "storage"');
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}
