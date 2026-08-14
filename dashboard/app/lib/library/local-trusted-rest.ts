import "server-only";
import { createClient } from "@supabase/supabase-js";
import { getSupabasePublicConfig } from "../supabase/config";

let cachedToken: { value: string; expiresAt: number } | null = null;

async function localReaderToken() {
  if (cachedToken && cachedToken.expiresAt > Date.now() + 300_000) return cachedToken.value;
  const { url, key } = getSupabasePublicConfig();
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!serviceKey) throw new Error("Local trusted database configuration unavailable");
  const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
  const anon = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
  const link = await admin.auth.admin.generateLink({ type: "magiclink", email: "kdimediaautomation@gmail.com" });
  const hash = link.data.properties?.hashed_token;
  if (link.error || !hash) throw new Error("Local reader session unavailable");
  const verified = await anon.auth.verifyOtp({ token_hash: hash, type: "email" });
  const session = verified.data.session;
  if (verified.error || !session) throw new Error("Local reader session unavailable");
  cachedToken = { value: session.access_token, expiresAt: (session.expires_at ?? Math.floor(Date.now() / 1000) + 3600) * 1000 };
  return cachedToken.value;
}

/** TEMPORARY LOCAL AUTH BYPASS server transport.
 * Never import this module into a Client Component. Restore authentication
 * before public deployment. It mints a short-lived, RLS-scoped approved reader
 * session server-side; no privileged credential is sent to browser JavaScript. */
export async function localTrustedRest(path: string, init: RequestInit = {}) {
  const { url, key } = getSupabasePublicConfig();
  const token = await localReaderToken();
  return fetch(`${url}/rest/v1/${path}`, {
    ...init,
    headers: { apikey: key, Authorization: `Bearer ${token}`, ...init.headers },
    cache: "no-store",
  });
}
