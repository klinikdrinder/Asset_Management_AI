import "server-only";
import { createClient as createJsClient, type SupabaseClient } from "@supabase/supabase-js";
import { createClient as createSsrClient } from "./server";
import { createServiceClient } from "./service";
import { getSupabasePublicConfig } from "./config";
import { currentAdmin } from "../admin-auth/session";
import { isLocalAuthBypassActive } from "../local-auth-bypass";
import type { AppUser } from "../../auth";

// How the search request is scoped to the database. USER_* paths run every retrieval and
// telemetry statement under the caller's own RLS identity (private.current_app_user_id()),
// so the service role is NEVER in a normal user's search path (owner decision, 2026-09-11).
// SERVICE_ELEVATED is a narrow, logged exception for break-glass super-admins (custom admin
// console) and the local dev bypass — neither of which carries a Firebase/Supabase JWT.
export type SearchDbMode = "USER_FIREBASE" | "USER_SUPABASE" | "SERVICE_ELEVATED";
export type ResolvedSearchDb = { client: SupabaseClient; mode: SearchDbMode };

function bearerToken(request: Request): string | null {
  const header = request.headers.get("authorization");
  if (!header) return null;
  const match = /^Bearer\s+(.+)$/i.exec(header.trim());
  return match ? match[1].trim() : null;
}

// A Supabase client that forwards the caller's Firebase ID token so PostgREST/RPC run under
// that JWT. RLS maps securetoken.google.com issuer -> app_users.firebase_uid -> user_id.
function firebaseTokenClient(idToken: string): SupabaseClient {
  const { url, key } = getSupabasePublicConfig();
  return createJsClient(url, key, {
    global: { headers: { Authorization: `Bearer ${idToken}` } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

/**
 * Resolve the Supabase client for a search request. Returns {error} for normal users who
 * present no usable identity — the route must fail closed (401) rather than silently drop to
 * the service role, which would defeat per-user RLS.
 */
export async function resolveSearchDb(
  request: Request,
  user: AppUser,
): Promise<ResolvedSearchDb | { error: "USER_CONTEXT_REQUIRED" }> {
  // Break-glass + dev: no third-party JWT exists; run gated/elevated. currentAdmin() is only
  // truthy when the request came through the custom super-admin console, so a super_admin who
  // signed in via Firebase still gets a proper user-context client below.
  if ((await isLocalAuthBypassActive()) || (user.managementRole === "super_admin" && !!(await currentAdmin()))) {
    return { client: createServiceClient(), mode: "SERVICE_ELEVATED" };
  }
  // Normal staff (Firebase primary): browser forwards its Firebase ID token.
  const token = bearerToken(request);
  if (token) return { client: firebaseTokenClient(token), mode: "USER_FIREBASE" };
  // Supabase-OAuth rollback path: the cookie session carries a Supabase-issued JWT.
  const ssr = await createSsrClient();
  const { data } = await ssr.auth.getUser();
  if (data.user?.id) return { client: ssr, mode: "USER_SUPABASE" };
  // No identity RLS will accept -> refuse. Never downgrade a normal user to the service role.
  return { error: "USER_CONTEXT_REQUIRED" };
}
