import "server-only";

import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextRequest, NextResponse } from "next/server";
import { getSupabasePublicConfig, secureCookieOptions } from "./config";

type CookieBatch = { name: string; value: string; options: CookieOptions }[];
const pendingCookies = new WeakMap<NextResponse, CookieBatch>();

export function createRouteClient(request: NextRequest, response: NextResponse) {
  const { url, key } = getSupabasePublicConfig();
  return createServerClient(url, key, {
    cookieOptions: secureCookieOptions,
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (items) => {
        const merged = new Map((pendingCookies.get(response) ?? []).map((item) => [item.name, item]));
        for (const item of items) merged.set(item.name, item);
        pendingCookies.set(response, [...merged.values()]);
        for (const { name, value, options } of items) {
          request.cookies.set(name, value);
          response.cookies.set(name, value, { ...options, ...secureCookieOptions });
        }
      },
    },
  });
}

export function copyResponseCookies(source: NextResponse, target: NextResponse) {
  const items = pendingCookies.get(source);
  if (items) for (const { name, value, options } of items) target.cookies.set(name, value, { ...options, ...secureCookieOptions });
  target.headers.set("Cache-Control", "private, no-store");
  target.headers.set("Pragma", "no-cache");
  return target;
}
