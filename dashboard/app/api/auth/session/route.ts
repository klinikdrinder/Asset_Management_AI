import { timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { profileForFirebaseUid } from "../../../lib/auth-profile";
import { getFirebaseAdminAuth } from "../../../lib/firebase/admin";
import { FIREBASE_CSRF_COOKIE, FIREBASE_SESSION_COOKIE, SESSION_MAX_AGE_MS } from "../../../lib/firebase/session";
import { FirebaseIdentityError, verifyFirebaseIdToken } from "../../../lib/firebase/verified-token";
import { FIREBASE_SUPABASE_TOKEN_COOKIE } from "../../../lib/library/authenticated-token";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function failure(status: number, code: string, message: string) {
  return NextResponse.json({ stage: "session", code, message }, { status });
}

function csrfValid(request: NextRequest) {
  const cookie = request.cookies.get(FIREBASE_CSRF_COOKIE)?.value ?? "";
  const header = request.headers.get("x-csrf-token") ?? "";
  const origin = request.headers.get("origin");
  if (!cookie || !header || origin !== request.nextUrl.origin) return false;
  const a = Buffer.from(cookie); const b = Buffer.from(header);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function POST(request: NextRequest) {
  if (!csrfValid(request)) return failure(403, "csrf_rejected", "The secure sign-in request was rejected. Please try again.");
  try {
    const body = await request.json() as { idToken?: unknown };
    const token = typeof body.idToken === "string" ? body.idToken : "";
    const decoded = await verifyFirebaseIdToken(token, true);
    if (decoded.role !== "authenticated") return failure(409, "claim_refresh_required", "Your access update has not completed. Please try again.");
    const profile = await profileForFirebaseUid(decoded.uid);
    if (!profile?.is_active || !["STAFF", "ADMIN"].includes(profile.role)) {
      return failure(403, profile && !profile.is_active ? "account_inactive" : "account_not_approved", "Your Google account was authenticated, but it is not approved to access this application.");
    }
    const session = await getFirebaseAdminAuth().createSessionCookie(token, { expiresIn: SESSION_MAX_AGE_MS });
    const response = NextResponse.json({ stage: "session", code: "session_succeeded", landing: profile.role === "ADMIN" ? "/admin" : "/library" });
    response.cookies.set(FIREBASE_SESSION_COOKIE, session, {
      httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge: SESSION_MAX_AGE_MS / 1000,
    });
    response.cookies.set(FIREBASE_SUPABASE_TOKEN_COOKIE, token, {
      httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge: 55 * 60,
    });
    response.cookies.delete(FIREBASE_CSRF_COOKIE);
    response.headers.set("Cache-Control", "private, no-store");
    return response;
  } catch (error) {
    return error instanceof FirebaseIdentityError
      ? failure(401, "invalid_firebase_identity", "Google identity verification failed. Please try again.")
      : failure(503, "session_creation_failed", "A secure session could not be created. Please try again.");
  }
}
