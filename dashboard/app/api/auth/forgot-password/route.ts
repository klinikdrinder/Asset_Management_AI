import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { getSupabasePublicConfig } from "../../../lib/supabase/config";
import { createServiceClient } from "../../../lib/supabase/service";
import {
  classifyInvitationDeliveryFailure,
  managementAudit,
  normalizedEmail,
  publicOrigin,
  safeProviderDiagnostic,
  sameOrigin,
  validEmail,
} from "../../../lib/user-management";

const successMessage = "We've sent password reset instructions to your email address.";
const failureMessage = "We couldn't send the reset email right now. Please try again.";
const rateLimitMessage = "Too many reset requests. Please wait a minute and try again.";
const resetAttempts = new Map<string, number>();
const RESET_COOLDOWN_MS = 60_000;

function response(message: string, status = 200) {
  return NextResponse.json({ message }, { status, headers: { "Cache-Control": "private, no-store", Pragma: "no-cache" } });
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return response(successMessage);

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const email = normalizedEmail(body.email);
  if (!validEmail(email)) return response("Enter a valid email address.", 400);

  const clientAddress = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
  const rateLimitKey = `${clientAddress}:${email}`;
  const lastAttempt = resetAttempts.get(rateLimitKey) ?? 0;
  if (Date.now() - lastAttempt < RESET_COOLDOWN_MS) return response(rateLimitMessage, 429);
  resetAttempts.set(rateLimitKey, Date.now());

  const redirectTo = `${publicOrigin(request)}/auth/callback?next=${encodeURIComponent("/reset-password")}`;
  try {
    const { url, key } = getSupabasePublicConfig();
    const auth = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
    const { error } = await auth.auth.resetPasswordForEmail(email, { redirectTo });
    if (error) {
      const diagnostic = safeProviderDiagnostic(error);
      console.warn("KDI_PASSWORD_RESET_DELIVERY", diagnostic);
      if (classifyInvitationDeliveryFailure(error) === "email_rate_limit") return response(rateLimitMessage, 429);
      return response(failureMessage, 503);
    }

    // Auditing must never turn an accepted provider delivery into a client-visible failure.
    try {
      const service = createServiceClient();
      const { data: profile } = await service.from("app_users").select("user_id,email").eq("email", email).maybeSingle();
      if (profile) await managementAudit(null, "password_reset_requested", { targetUserId: profile.user_id, targetEmail: profile.email });
    } catch (auditError) {
      console.warn("KDI_PASSWORD_RESET_AUDIT", { reason: "audit_failed" });
    }
    return response(successMessage);
  } catch (error) {
    console.warn("KDI_PASSWORD_RESET_DELIVERY", safeProviderDiagnostic(error));
    return response(failureMessage, 503);
  }
}
