import { randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { getFirebaseAdminAuth } from "../../../lib/firebase/admin";
import { FIREBASE_CSRF_COOKIE } from "../../../lib/firebase/session";
import { FirebaseIdentityError, verifyFirebaseIdToken } from "../../../lib/firebase/verified-token";
import { createServiceClient } from "../../../lib/supabase/service";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type BootstrapStage = "request_validation" | "csrf_validation" | "firebase_token_verification" | "firebase_project_validation" | "verified_email_validation" | "approved_profile_lookup" | "firebase_identity_link" | "firebase_claim_assignment" | "bootstrap_complete";

function diagnostic(stage: BootstrapStage, code: string, status: number, verificationSucceeded: boolean, profileLookupSucceeded: boolean) {
  console.info("firebase_bootstrap", { stage, code, status, verificationSucceeded, profileLookupSucceeded });
}

function failure(status: number, stage: BootstrapStage, code: string, message: string, verificationSucceeded = false, profileLookupSucceeded = false) {
  diagnostic(stage, code, status, verificationSucceeded, profileLookupSucceeded);
  return NextResponse.json({ stage, code, message }, { status });
}

function sameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  return !!origin && origin === request.nextUrl.origin;
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return failure(403, "csrf_validation", "csrf_rejected", "The secure sign-in request was rejected. Please try again.");
  let decoded;
  try {
    const body = await request.json() as { idToken?: unknown };
    if (typeof body.idToken !== "string" || !body.idToken) return failure(400, "request_validation", "missing_token", "The sign-in response was incomplete. Please try again.");
    decoded = await verifyFirebaseIdToken(body.idToken, true);
  } catch (error) {
    if (error instanceof FirebaseIdentityError) {
      const message = error.code === "firebase_admin_credential_unavailable"
        ? "Google identity verification is temporarily unavailable."
        : "Google identity verification failed. Please try again.";
      return failure(error.status, error.stage, error.code, message);
    }
    return failure(400, "request_validation", "invalid_request", "The sign-in response was incomplete. Please try again.");
  }

  const { data, error } = await createServiceClient().rpc("bootstrap_firebase_app_user", {
    requested_firebase_uid: decoded.uid,
    requested_email: decoded.email!.trim().toLowerCase(),
  });
  const profile = Array.isArray(data) ? data[0] : null;
  if (error || !profile?.is_active || !["STAFF", "ADMIN"].includes(profile.role)) {
    await getFirebaseAdminAuth().revokeRefreshTokens(decoded.uid).catch(() => undefined);
    const conflict = error?.code === "23505";
    const code = conflict ? "profile_link_conflict" : profile && !profile.is_active ? "account_inactive" : "account_not_approved";
    const stage: BootstrapStage = conflict ? "firebase_identity_link" : "approved_profile_lookup";
    return failure(403, stage, code, "Your Google account was authenticated, but it is not approved to access this application.", true, false);
  }

  try {
    const auth = getFirebaseAdminAuth();
    const record = await auth.getUser(decoded.uid);
    const refreshRequired = record.customClaims?.role !== "authenticated";
    if (refreshRequired) await auth.setCustomUserClaims(decoded.uid, { ...(record.customClaims ?? {}), role: "authenticated" });
    diagnostic("bootstrap_complete", "bootstrap_succeeded", 200, true, true);
    const response = NextResponse.json({ stage: "bootstrap_complete", code: "bootstrap_succeeded", refreshRequired, landing: profile.role === "ADMIN" ? "/admin" : "/library" });
    response.cookies.set(FIREBASE_CSRF_COOKIE, randomBytes(32).toString("base64url"), {
      httpOnly: false, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge: 600,
    });
    response.headers.set("Cache-Control", "private, no-store");
    return response;
  } catch {
    return failure(503, "firebase_claim_assignment", "claim_assignment_failed", "Application access could not be finalized. Please try again.", true, true);
  }
}
