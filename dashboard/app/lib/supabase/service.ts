import "server-only";

import { createClient } from "@supabase/supabase-js";
import { getSupabasePublicConfig } from "./config";

export function createServiceClient() {
  const { url } = getSupabasePublicConfig();
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!key) throw new Error("Server authorization configuration is unavailable");
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
}
