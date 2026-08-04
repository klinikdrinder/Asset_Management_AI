import { NextRequest, NextResponse } from "next/server";
import { applicationOrigin, safeReturnPath } from "../../lib/supabase/config";
import { copyResponseCookies, createRouteClient } from "../../lib/supabase/route-client";
import { recordAuthDiagnostic, sanitizedAuthError } from "./diagnostics";

export const dynamic = "force-dynamic";

type CallbackReason = "oauth_provider_error" | "missing_authorization_code" | "missing_pkce_verifier" | "code_exchange_failed" | "session_not_created" | "user_lookup_failed" | "profile_not_linked" | "account_disabled" | "insufficient_role";
async function callbackFailure(origin: string, reason: CallbackReason, cookieResponse?: NextResponse, details: Record<string, string> = {}) {
  console.warn("KDI_AUTH_CALLBACK", { reason });
  const target = NextResponse.redirect(new URL(`/login?error=${reason}`, origin));
  const result = cookieResponse ? copyResponseCookies(cookieResponse, target) : target;
  await recordAuthDiagnostic({ stage: "callback_failed", reason, status: 307, cookieNames: result.cookies.getAll().map((x) => x.name), redirectPath: "/login", ...details });
  return result;
}

export async function GET(request: NextRequest) {
  const origin = applicationOrigin(request.url);
  const providerError = request.nextUrl.searchParams.get("error") || request.nextUrl.searchParams.get("error_code");
  const code = request.nextUrl.searchParams.get("code");
  const next = safeReturnPath(request.nextUrl.searchParams.get("next"), "/library");
  const requestCookieNames = request.cookies.getAll().map((x) => x.name);
  const verifierPresent = requestCookieNames.some((name) => name.endsWith("-auth-token-code-verifier"));
  await recordAuthDiagnostic({ stage: "callback_received", reason: providerError ? "provider_error" : code ? "authorization_code_present" : "authorization_code_missing", status: 200, cookieNames: requestCookieNames });
  if (providerError) return await callbackFailure(origin, "oauth_provider_error");
  if (!code) return await callbackFailure(origin, "missing_authorization_code");
  if (!verifierPresent) return await callbackFailure(origin, "missing_pkce_verifier");
  const cookieResponse = NextResponse.next();
  const supabase = createRouteClient(request, cookieResponse);
  const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
  if (exchangeError) return await callbackFailure(origin, "code_exchange_failed", cookieResponse, sanitizedAuthError(exchangeError));
  await recordAuthDiagnostic({ stage: "code_exchange", reason: "success", status: 200, cookieNames: cookieResponse.cookies.getAll().map((x) => x.name) });
  const { data: { user }, error: userError } = await supabase.auth.getUser();
  if (!user && !userError) return await callbackFailure(origin, "session_not_created", cookieResponse);
  const googleIdentity = user?.identities?.find((identity) => identity.provider === "google");
  const verified = Boolean(user?.email_confirmed_at) && googleIdentity?.identity_data?.email_verified === true;
  if (userError || !user?.email || !verified) {
    console.warn("KDI_AUTH_CALLBACK", { reason: "user_lookup_failed" });
    await supabase.auth.signOut({ scope: "local" });
    return await callbackFailure(origin, "user_lookup_failed", cookieResponse, sanitizedAuthError(userError));
  }
  const { error: linkError } = await supabase.rpc("link_current_app_user");
  const { data: profile } = await supabase.from("app_users").select("role,is_active").eq("user_id", user.id).maybeSingle();
  if (linkError || !profile) {
    await supabase.auth.signOut({ scope: "local" });
    return await callbackFailure(origin, "profile_not_linked", cookieResponse, sanitizedAuthError(linkError));
  }
  if (!profile.is_active) {
    await supabase.auth.signOut({ scope: "local" });
    return await callbackFailure(origin, "account_disabled", cookieResponse);
  }
  if (profile.role !== "STAFF" && profile.role !== "ADMIN") {
    await supabase.auth.signOut({ scope: "local" });
    return await callbackFailure(origin, "insufficient_role", cookieResponse);
  }
  const requested = next.startsWith("/admin") && profile.role !== "ADMIN" ? "/library" : next;
  const landing = requested === "/library" && profile.role === "ADMIN" ? "/admin" : requested;
  console.info("KDI_AUTH_CALLBACK", { reason: "success", role: profile.role });
  const result = copyResponseCookies(cookieResponse, NextResponse.redirect(new URL(landing, origin)));
  await recordAuthDiagnostic({ stage: "authorization", reason: "success_admin_or_staff", status: 307, cookieNames: result.cookies.getAll().map((x) => x.name), redirectPath: landing });
  return result;
}
