import "server-only";

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { getSupabasePublicConfig, secureCookieOptions } from "./config";

export async function createClient() {
  const cookieStore = await cookies();
  const { url, key } = getSupabasePublicConfig();
  return createServerClient(url, key, {
    cookieOptions: secureCookieOptions,
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (items) => {
        try {
          for (const { name, value, options } of items) cookieStore.set(name, value, { ...options, ...secureCookieOptions });
        } catch {
          // Server Components cannot mutate cookies; proxy.ts performs refresh writes.
        }
      },
    },
  });
}
